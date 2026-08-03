#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <ssh-host> <identity-file> <image@sha256:digest> [...]" >&2
  exit 2
fi

ssh_host="$1"
identity_file="$2"
shift 2
ssh_opts=(-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes
  -i "$identity_file")

command -v skopeo >/dev/null
[ -f "$identity_file" ]

for image_ref in "$@"; do
  if [[ ! "$image_ref" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "image must be an immutable GHCR digest reference: $image_ref" >&2
    exit 2
  fi

  repository="${image_ref%@sha256:*}"
  digest="${image_ref##*@}"
  digest_hex="${digest#sha256:}"
  relay_dir="$(mktemp -d "${TMPDIR:-/tmp}/w2-oci-relay.XXXXXX")"
  [ -n "$relay_dir" ]
  case "$relay_dir" in
    "${TMPDIR:-/tmp}"/w2-oci-relay.*) ;;
    *) exit 1 ;;
  esac
  archive="$relay_dir/image.oci.tar"
  remote_archive="/tmp/w2-oci-relay-${digest_hex}.tar"

  cleanup() {
    if [ -d "$relay_dir" ] && [ ! -L "$relay_dir" ]; then
      rm -rf -- "$relay_dir"
    fi
    ssh "${ssh_opts[@]}" "$ssh_host" \
      "if [ -f '$remote_archive' ] && [ ! -L '$remote_archive' ]; then rm -f -- '$remote_archive'; fi" \
      >/dev/null 2>&1 || true
  }
  trap cleanup EXIT

  started="$(date +%s)"
  skopeo copy --all "docker://$image_ref" "oci-archive:$archive" >/dev/null
  pulled="$(date +%s)"
  archive_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"

  ssh "${ssh_opts[@]}" "$ssh_host" "test ! -e '$remote_archive'"
  scp "${ssh_opts[@]}" "$archive" "$ssh_host:$remote_archive"
  transferred="$(date +%s)"

  remote_sha="$(
    ssh "${ssh_opts[@]}" "$ssh_host" \
      "test -f '$remote_archive' && test ! -L '$remote_archive' && sha256sum '$remote_archive'" |
      awk '{print $1}'
  )"
  [ "$remote_sha" = "$archive_sha" ]

  ssh "${ssh_opts[@]}" "$ssh_host" \
    sudo ctr -n moby images import --all-platforms --digests \
    --base-name "$repository" "$remote_archive" >/dev/null
  ssh "${ssh_opts[@]}" "$ssh_host" \
    sudo docker image inspect "$image_ref" >/dev/null
  imported="$(date +%s)"

  printf 'IMAGE=%s\n' "$image_ref"
  printf 'LOCAL_GHCR_SECONDS=%s\n' "$((pulled-started))"
  printf 'LOCAL_TO_VPS_SECONDS=%s\n' "$((transferred-pulled))"
  printf 'VPS_IMPORT_SECONDS=%s\n' "$((imported-transferred))"
  printf 'TOTAL_SECONDS=%s\n' "$((imported-started))"
  printf 'ARCHIVE_BYTES=%s\n' "$(wc -c <"$archive" | tr -d ' ')"
  printf 'DIGEST_VERIFIED=true\n'

  cleanup
  trap - EXIT
done

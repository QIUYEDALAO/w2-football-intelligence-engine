from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from w2.domain.time import require_utc
from w2.historical.dataset import FEATURE_RESULT_FIELDS, AsOfSample


@dataclass(frozen=True)
class LeakageFinding:
    rule: str
    fixture_id: str
    message: str


class LeakageGuard:
    def check(
        self, samples: list[AsOfSample], split_by_sample_id: dict[str, str] | None = None
    ) -> list[LeakageFinding]:
        findings: list[LeakageFinding] = []
        for sample in samples:
            if sample.label_reference.confirmed_at <= sample.as_of_time:
                findings.append(
                    LeakageFinding(
                        "future_result", sample.fixture_id, "result label visible before as_of_time"
                    )
                )
            feature_keys = set(sample.feature_payload())
            nested_keys = (
                set(sample.odds_snapshot)
                | set(sample.lineup_status)
                | set(sample.injury_status)
                | set(sample.team_rating_features)
            )
            if FEATURE_RESULT_FIELDS & (feature_keys | nested_keys):
                findings.append(
                    LeakageFinding(
                        "label_fields_in_features",
                        sample.fixture_id,
                        "result field in feature payload",
                    )
                )
            for payload_name, payload in [
                ("odds", sample.odds_snapshot),
                ("lineup", sample.lineup_status),
                ("injury", sample.injury_status),
                ("team_rating", sample.team_rating_features),
            ]:
                timestamp = (
                    payload.get("provider_updated_at")
                    or payload.get("updated_at")
                    or payload.get("as_of_time")
                )
                if (
                    timestamp
                    and require_utc(
                        datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")), payload_name
                    )
                    > sample.as_of_time
                ):
                    findings.append(
                        LeakageFinding(
                            f"future_{payload_name}",
                            sample.fixture_id,
                            f"{payload_name} update after as_of_time",
                        )
                    )
            if (
                sample.odds_snapshot.get("snapshot_type") == "closing"
                and sample.prediction_phase != "closing"
            ):
                findings.append(
                    LeakageFinding(
                        "closing_odds_used_before_closing",
                        sample.fixture_id,
                        "closing odds in pre-closing phase",
                    )
                )
            if sample.data_cutoff > sample.as_of_time:
                findings.append(
                    LeakageFinding(
                        "ingested_as_of_conflict", sample.fixture_id, "data cutoff after as_of_time"
                    )
                )
        if split_by_sample_id:
            fixture_splits: dict[str, set[str]] = defaultdict(set)
            for sample in samples:
                split = split_by_sample_id.get(str(sample.sample_id))
                if split:
                    fixture_splits[sample.fixture_id].add(split)
            for fixture_id, splits in fixture_splits.items():
                if len(splits) > 1:
                    findings.append(
                        LeakageFinding(
                            "fixture_cross_split", fixture_id, "same fixture crosses train/val/test"
                        )
                    )
        return findings


def assert_no_random_time_split(splitter_name: str) -> None:
    if splitter_name == "random":
        raise ValueError("random split is forbidden for historical as-of datasets")

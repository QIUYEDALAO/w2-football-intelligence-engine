# W2 Stage7H Runtime Blocker

```text
=== compose ps json ===
{"Command":"\"uv run uvicorn apps…\"","CreatedAt":"2026-06-22 16:01:40 +0800 CST","ExitCode":0,"Health":"healthy","ID":"5af98407c0a1","Image":"w2-staging-api","Labels":"com.docker.compose.config-hash=fb89337b08c02a1726f00310ff83beef22765584c620badea4c933c60b05d3d9,com.docker.compose.container-number=1,com.docker.compose.image=sha256:97fd6a1277a31e0b3a10861ab4206f79fd0b8a58027e005169d850291b78065e,com.docker.compose.project.environment_file=/opt/w2/shared/.env,com.docker.compose.service=api,com.docker.compose.depends_on=redis:service_healthy:false,postgres:service_healthy:false,com.docker.compose.oneoff=False,com.docker.compose.project=w2-staging,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.version=5.1.4","LocalVolumes":"0","Mounts":"/opt/w2/releas…,/opt/w2/releas…","Name":"w2-staging-api-1","Names":"w2-staging-api-1","Networks":"w2-staging_w2-staging","Ports":"127.0.0.1:18000-\u003e8000/tcp","Project":"w2-staging","Publishers":[{"URL":"127.0.0.1","TargetPort":8000,"PublishedPort":18000,"Protocol":"tcp"}],"RunningFor":"10 minutes ago","Service":"api","Size":"0B","State":"running","Status":"Up 9 minutes (healthy)"}
{"Command":"\"docker-entrypoint.s…\"","CreatedAt":"2026-06-22 16:01:39 +0800 CST","ExitCode":0,"Health":"healthy","ID":"6e0132a2a2bb","Image":"postgres:16-alpine","Labels":"com.docker.compose.image=sha256:e013e867e712fec275706a6c51c966f0bb0c93cfa8f51000f85a15f9865a28cb,com.docker.compose.oneoff=False,com.docker.compose.project=w2-staging,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.config-hash=7177ec9c4a8957b054bb16edf4807c05c2324a761a52e577c9ea6b59b5d0063f,com.docker.compose.depends_on=,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml,com.docker.compose.project.environment_file=/opt/w2/shared/.env,com.docker.compose.service=postgres,com.docker.compose.version=5.1.4,com.docker.compose.container-number=1","LocalVolumes":"1","Mounts":"w2-staging_pos…","Name":"w2-staging-postgres-1","Names":"w2-staging-postgres-1","Networks":"w2-staging_w2-staging","Ports":"5432/tcp","Project":"w2-staging","Publishers":[{"URL":"","TargetPort":5432,"PublishedPort":0,"Protocol":"tcp"}],"RunningFor":"10 minutes ago","Service":"postgres","Size":"0B","State":"running","Status":"Up 10 minutes (healthy)"}
{"Command":"\"docker-entrypoint.s…\"","CreatedAt":"2026-06-22 16:01:39 +0800 CST","ExitCode":0,"Health":"healthy","ID":"312ddecd4f92","Image":"redis:7-alpine","Labels":"com.docker.compose.config-hash=40ded091a9e96836db32b809c1dc31a8d943b51ea9919b04af71e301f4180146,com.docker.compose.container-number=1,com.docker.compose.project=w2-staging,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml,com.docker.compose.project.environment_file=/opt/w2/shared/.env,com.docker.compose.depends_on=,com.docker.compose.image=sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99,com.docker.compose.oneoff=False,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.service=redis,com.docker.compose.version=5.1.4","LocalVolumes":"1","Mounts":"w2-staging_red…","Name":"w2-staging-redis-1","Names":"w2-staging-redis-1","Networks":"w2-staging_w2-staging","Ports":"6379/tcp","Project":"w2-staging","Publishers":[{"URL":"","TargetPort":6379,"PublishedPort":0,"Protocol":"tcp"}],"RunningFor":"10 minutes ago","Service":"redis","Size":"0B","State":"running","Status":"Up 10 minutes (healthy)"}
{"Command":"\"uv run python -m ap…\"","CreatedAt":"2026-06-22 16:01:40 +0800 CST","ExitCode":0,"Health":"","ID":"601cd4ac69da","Image":"w2-staging-scheduler","Labels":"com.docker.compose.config-hash=5b436b6007239a75dbdae8c4484c4a405f9d9930198d484e51e776b28d21153a,com.docker.compose.container-number=1,com.docker.compose.depends_on=redis:service_healthy:false,com.docker.compose.project.environment_file=/opt/w2/shared/.env,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.service=scheduler,com.docker.compose.version=5.1.4,com.docker.compose.image=sha256:9302fceb98f07b7fcf33a79445ad2d103aa8062cbcc5f0ca00abfef880c72a81,com.docker.compose.oneoff=False,com.docker.compose.project=w2-staging,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml","LocalVolumes":"0","Mounts":"/opt/w2/releas…,/opt/w2/releas…","Name":"w2-staging-scheduler-1","Names":"w2-staging-scheduler-1","Networks":"w2-staging_w2-staging","Ports":"","Project":"w2-staging","Publishers":[],"RunningFor":"10 minutes ago","Service":"scheduler","Size":"0B","State":"restarting","Status":"Restarting (0) 8 seconds ago"}
{"Command":"\"/docker-entrypoint.…\"","CreatedAt":"2026-06-22 16:01:40 +0800 CST","ExitCode":0,"Health":"healthy","ID":"899da1ae8830","Image":"w2-staging-web","Labels":"com.docker.compose.config-hash=3110332e8dac4e34a2a39be81f067dca8c97948d9b408e71f7f7083e0b167796,com.docker.compose.container-number=1,com.docker.compose.depends_on=api:service_healthy:false,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.service=web,org.opencontainers.image.title=docker-nginx-unprivileged,com.docker.compose.project.environment_file=/opt/w2/shared/.env,org.opencontainers.image.created=2025-06-23T02:05:23.879Z,org.opencontainers.image.licenses=Apache-2.0,org.opencontainers.image.source=https://github.com/nginx/docker-nginx-unprivileged,org.opencontainers.image.version=1.27.5-alpine,com.docker.compose.version=5.1.4,maintainer=NGINX Docker Maintainers \u003cdocker-maint@nginx.com\u003e,org.opencontainers.image.description=Unprivileged NGINX Dockerfiles,org.opencontainers.image.url=https://github.com/nginx/docker-nginx-unprivileged,com.docker.compose.image=sha256:186bf423ef51df576a91ffa7d58f583f7c1f51572f2fc6e7fee337a77467554a,com.docker.compose.oneoff=False,com.docker.compose.project=w2-staging,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml,org.opencontainers.image.revision=d5fb0119cf5c6a94cba03474ccc841bbe037fa87","LocalVolumes":"0","Mounts":"","Name":"w2-staging-web-1","Names":"w2-staging-web-1","Networks":"w2-staging_w2-staging","Ports":"127.0.0.1:18080-\u003e8080/tcp","Project":"w2-staging","Publishers":[{"URL":"127.0.0.1","TargetPort":8080,"PublishedPort":18080,"Protocol":"tcp"}],"RunningFor":"10 minutes ago","Service":"web","Size":"0B","State":"running","Status":"Up 9 minutes (healthy)"}
{"Command":"\"uv run celery -A ap…\"","CreatedAt":"2026-06-22 16:01:40 +0800 CST","ExitCode":0,"Health":"unhealthy","ID":"b6efe147e715","Image":"w2-staging-worker","Labels":"com.docker.compose.depends_on=redis:service_healthy:false,com.docker.compose.image=sha256:e8c9fd84b0eb8af37b764feb741365fa159e037319ed8f9aa9ef068416c01c11,com.docker.compose.oneoff=False,com.docker.compose.project=w2-staging,com.docker.compose.project.config_files=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose/compose.staging.yml,com.docker.compose.project.working_dir=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85/infra/compose,com.docker.compose.service=worker,com.docker.compose.version=5.1.4,com.docker.compose.config-hash=5845d5fbc348ef7aa9f2b1e52b4e31877df85796933468ba6a79279eb63e21f0,com.docker.compose.container-number=1,com.docker.compose.project.environment_file=/opt/w2/shared/.env","LocalVolumes":"0","Mounts":"/opt/w2/releas…,/opt/w2/releas…","Name":"w2-staging-worker-1","Names":"w2-staging-worker-1","Networks":"w2-staging_w2-staging","Ports":"","Project":"w2-staging","Publishers":[],"RunningFor":"10 minutes ago","Service":"worker","Size":"0B","State":"running","Status":"Up 9 minutes (unhealthy)"}
=== worker scheduler logs ===
scheduler-1  |    Building w2-football-intelligence-engine @ file:///app
scheduler-1  | Downloading ruff (11.0MiB)
scheduler-1  | Downloading pygments (1.2MiB)
scheduler-1  | Downloading virtualenv (4.3MiB)
scheduler-1  | Downloading mypy (14.1MiB)
scheduler-1  |  Downloaded pygments
scheduler-1  |  Downloaded virtualenv
scheduler-1  |       Built w2-football-intelligence-engine @ file:///app
scheduler-1  |  Downloaded ruff
scheduler-1  |  Downloaded mypy
scheduler-1  | Uninstalled 1 package in 7ms
scheduler-1  | Installed 24 packages in 60ms
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
scheduler-1  | INFO:w2.scheduler:w2 scheduler heartbeat
worker-1     |    Building w2-football-intelligence-engine @ file:///app
worker-1     | Downloading virtualenv (4.3MiB)
worker-1     | Downloading ruff (11.0MiB)
worker-1     | Downloading mypy (14.1MiB)
worker-1     | Downloading pygments (1.2MiB)
worker-1     |  Downloaded pygments
worker-1     |  Downloaded virtualenv
worker-1     |       Built w2-football-intelligence-engine @ file:///app
worker-1     |  Downloaded ruff
worker-1     |  Downloaded mypy
worker-1     | Uninstalled 1 package in 5ms
worker-1     | Installed 24 packages in 41ms
worker-1     |  
worker-1     |  -------------- celery@b6efe147e715 v5.6.3 (recovery)
worker-1     | --- ***** ----- 
worker-1     | -- ******* ---- Linux-6.8.0-117-generic-x86_64-with-glibc2.41 2026-06-22 08:01:57
worker-1     | - *** --- * --- 
worker-1     | - ** ---------- [config]
worker-1     | - ** ---------- .> app:         w2:0x71e251476ab0
worker-1     | - ** ---------- .> transport:   redis://redis:6379/1
worker-1     | - ** ---------- .> results:     redis://redis:6379/2
worker-1     | - *** --- * --- .> concurrency: 1 (prefork)
worker-1     | -- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
worker-1     | --- ***** ----- 
worker-1     |  -------------- [queues]
worker-1     |                 .> celery           exchange=celery(direct) key=celery
worker-1     |                 
worker-1     | 
worker-1     | [tasks]
worker-1     |   . w2.ping
worker-1     | 
worker-1     | [2026-06-22 08:01:57,856: INFO/MainProcess] Connected to redis://redis:6379/1
worker-1     | [2026-06-22 08:01:57,859: INFO/MainProcess] mingle: searching for neighbors
worker-1     | [2026-06-22 08:01:58,866: INFO/MainProcess] mingle: all alone
worker-1     | [2026-06-22 08:01:58,877: INFO/MainProcess] celery@b6efe147e715 ready.
=== systemd journal ===
Jun 22 15:54:49 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:55:19 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 254.
Jun 22 15:55:19 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:55:19 VM-0-16-ubuntu docker[243638]: unable to get image 'w2-web': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:55:19 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:55:19 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:55:19 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:55:49 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 255.
Jun 22 15:55:49 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:55:50 VM-0-16-ubuntu docker[244105]: unable to get image 'w2-scheduler': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:55:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:55:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:55:50 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:56:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 256.
Jun 22 15:56:20 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:56:20 VM-0-16-ubuntu docker[244435]: unable to get image 'w2-web': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:56:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:56:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:56:20 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:56:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 257.
Jun 22 15:56:50 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:56:50 VM-0-16-ubuntu docker[244904]: unable to get image 'w2-worker': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:56:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:56:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:56:50 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:57:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 258.
Jun 22 15:57:20 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:57:20 VM-0-16-ubuntu docker[245228]: unable to get image 'w2-worker': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:57:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:57:20 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:57:20 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:57:50 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 259.
Jun 22 15:57:50 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:57:51 VM-0-16-ubuntu docker[245694]: unable to get image 'w2-web': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:57:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:57:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:57:51 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:58:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 260.
Jun 22 15:58:21 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:58:21 VM-0-16-ubuntu docker[246019]: unable to get image 'w2-migration': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:58:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:58:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:58:21 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:58:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 261.
Jun 22 15:58:51 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:58:51 VM-0-16-ubuntu docker[246719]: unable to get image 'w2-web': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:58:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:58:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:58:51 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:59:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 262.
Jun 22 15:59:21 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:59:21 VM-0-16-ubuntu docker[248696]: unable to get image 'w2-migration': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:59:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:59:21 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:59:21 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 15:59:51 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 263.
Jun 22 15:59:51 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 15:59:52 VM-0-16-ubuntu docker[249610]: unable to get image 'w2-worker': permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
Jun 22 15:59:52 VM-0-16-ubuntu systemd[1]: w2-staging.service: Main process exited, code=exited, status=1/FAILURE
Jun 22 15:59:52 VM-0-16-ubuntu systemd[1]: w2-staging.service: Failed with result 'exit-code'.
Jun 22 15:59:52 VM-0-16-ubuntu systemd[1]: Failed to start w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 16:00:22 VM-0-16-ubuntu systemd[1]: w2-staging.service: Scheduled restart job, restart counter is at 264.
Jun 22 16:00:22 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250610]:   ubuntu : PWD=/opt/w2/releases/a766f3af40af7b71b33ca7145b014f43fb8a10b5 ; USER=root ; COMMAND=/usr/bin/docker compose -f infra/compose/compose.staging.yml --env-file /opt/w2/shared/.env up -d --remove-orphans
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250610]: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=1000)
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Running
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-postgres-1 Running
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-api-1 Running
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-worker-1 Running
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-web-1 Running
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-postgres-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-postgres-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Healthy
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-postgres-1 Healthy
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-migration-1 Starting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Healthy
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-redis-1 Healthy
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-scheduler-1 Starting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-postgres-1 Healthy
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-api-1 Waiting
Jun 22 16:00:22 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-scheduler-1 Started
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-migration-1 Started
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250627]:  Container w2-staging-api-1 Healthy
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250610]: pam_unix(sudo:session): session closed for user root
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250761]:   ubuntu : PWD=/opt/w2/releases/a766f3af40af7b71b33ca7145b014f43fb8a10b5 ; USER=root ; COMMAND=/usr/bin/docker compose -f infra/compose/compose.staging.yml --env-file /opt/w2/shared/.env ps
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250761]: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=1000)
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: NAME                     IMAGE                  COMMAND                  SERVICE     CREATED              STATUS                                     PORTS
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-api-1         w2-staging-api         "uv run uvicorn apps…"   api         About a minute ago   Up About a minute (healthy)                127.0.0.1:18000->8000/tcp
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-migration-1   w2-staging-migration   "uv run alembic upgr…"   migration   About a minute ago   Up Less than a second (health: starting)
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-postgres-1    postgres:16-alpine     "docker-entrypoint.s…"   postgres    About a minute ago   Up About a minute (healthy)                5432/tcp
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-redis-1       redis:7-alpine         "docker-entrypoint.s…"   redis       About a minute ago   Up About a minute (healthy)                6379/tcp
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-scheduler-1   w2-staging-scheduler   "uv run python -m ap…"   scheduler   About a minute ago   Restarting (0) 13 seconds ago
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-web-1         w2-staging-web         "/docker-entrypoint.…"   web         About a minute ago   Up 59 seconds (healthy)                    127.0.0.1:18080->8080/tcp
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250777]: w2-staging-worker-1      w2-staging-worker      "uv run celery -A ap…"   worker      About a minute ago   Up About a minute (health: starting)
Jun 22 16:00:23 VM-0-16-ubuntu sudo[250761]: pam_unix(sudo:session): session closed for user root
Jun 22 16:00:23 VM-0-16-ubuntu systemd[1]: Finished w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 16:01:36 VM-0-16-ubuntu systemd[1]: Stopping w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 16:01:36 VM-0-16-ubuntu sudo[251914]:   ubuntu : PWD=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85 ; USER=root ; COMMAND=/usr/bin/docker compose -f infra/compose/compose.staging.yml down
Jun 22 16:01:36 VM-0-16-ubuntu sudo[251914]: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=1000)
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"W2_API_FOOTBALL_API_KEY\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"W2_API_FOOTBALL_API_KEY\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"W2_API_FOOTBALL_API_KEY\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]: time="2026-06-22T16:01:37+08:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-migration-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-worker-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-scheduler-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-web-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-migration-1 Stopped
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-migration-1 Removing
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-scheduler-1 Stopped
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-scheduler-1 Removing
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-migration-1 Removed
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-web-1 Stopped
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-web-1 Removing
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-scheduler-1 Removed
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-web-1 Removed
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-api-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-api-1 Stopped
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-api-1 Removing
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-api-1 Removed
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-postgres-1 Stopping
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-postgres-1 Stopped
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-postgres-1 Removing
Jun 22 16:01:37 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-postgres-1 Removed
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-worker-1 Stopped
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-worker-1 Removing
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-worker-1 Removed
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-redis-1 Stopping
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-redis-1 Stopped
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-redis-1 Removing
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Container w2-staging-redis-1 Removed
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Network w2-staging_w2-staging Removing
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251930]:  Network w2-staging_w2-staging Removed
Jun 22 16:01:39 VM-0-16-ubuntu sudo[251914]: pam_unix(sudo:session): session closed for user root
Jun 22 16:01:39 VM-0-16-ubuntu systemd[1]: w2-staging.service: Deactivated successfully.
Jun 22 16:01:39 VM-0-16-ubuntu systemd[1]: Stopped w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
Jun 22 16:01:39 VM-0-16-ubuntu systemd[1]: Starting w2-staging.service - W2 Football Intelligence Engine — Staging Stack...
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252182]:   ubuntu : PWD=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85 ; USER=root ; COMMAND=/usr/bin/docker compose -f infra/compose/compose.staging.yml --env-file /opt/w2/shared/.env up -d --remove-orphans
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252182]: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=1000)
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Network w2-staging_w2-staging Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Network w2-staging_w2-staging Created
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Created
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-worker-1 Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-scheduler-1 Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Created
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Creating
Jun 22 16:01:39 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-migration-1 Creating
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-scheduler-1 Created
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-worker-1 Created
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-migration-1 Created
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Created
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-web-1 Creating
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-web-1 Created
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Starting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Starting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Started
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Waiting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Waiting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Started
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Waiting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Waiting
Jun 22 16:01:40 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Waiting
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Healthy
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Healthy
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-scheduler-1 Starting
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-worker-1 Starting
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Healthy
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-migration-1 Starting
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-redis-1 Healthy
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-postgres-1 Healthy
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Starting
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-scheduler-1 Started
Jun 22 16:01:50 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-worker-1 Started
Jun 22 16:01:51 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-migration-1 Started
Jun 22 16:01:51 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Started
Jun 22 16:01:51 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Waiting
Jun 22 16:02:02 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-api-1 Healthy
Jun 22 16:02:02 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-web-1 Starting
Jun 22 16:02:02 VM-0-16-ubuntu sudo[252198]:  Container w2-staging-web-1 Started
Jun 22 16:02:02 VM-0-16-ubuntu sudo[252182]: pam_unix(sudo:session): session closed for user root
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253727]:   ubuntu : PWD=/opt/w2/releases/2f85408c2936be6a62b8d6cc7491cc3f4819dd85 ; USER=root ; COMMAND=/usr/bin/docker compose -f infra/compose/compose.staging.yml --env-file /opt/w2/shared/.env ps
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253727]: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=1000)
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: NAME                     IMAGE                  COMMAND                  SERVICE     CREATED          STATUS                                     PORTS
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-api-1         w2-staging-api         "uv run uvicorn apps…"   api         22 seconds ago   Up 11 seconds (healthy)                    127.0.0.1:18000->8000/tcp
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-postgres-1    postgres:16-alpine     "docker-entrypoint.s…"   postgres    23 seconds ago   Up 22 seconds (healthy)                    5432/tcp
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-redis-1       redis:7-alpine         "docker-entrypoint.s…"   redis       23 seconds ago   Up 22 seconds (healthy)                    6379/tcp
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-scheduler-1   w2-staging-scheduler   "uv run python -m ap…"   scheduler   22 seconds ago   Restarting (0) 3 seconds ago
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-web-1         w2-staging-web         "/docker-entrypoint.…"   web         22 seconds ago   Up Less than a second (health: starting)   127.0.0.1:18080->8080/tcp
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253761]: w2-staging-worker-1      w2-staging-worker      "uv run celery -A ap…"   worker      22 seconds ago   Up 11 seconds (health: starting)
Jun 22 16:02:02 VM-0-16-ubuntu sudo[253727]: pam_unix(sudo:session): session closed for user root
Jun 22 16:02:02 VM-0-16-ubuntu systemd[1]: Finished w2-staging.service - W2 Football Intelligence Engine — Staging Stack.
=== inspect worker scheduler ===
=== worker cid=b6efe147e715e3b0f46446cbf01c1e4704326b53c475dc0b059599d3eda5ea6b ===
Name=/w2-staging-worker-1
State={"Status":"running","Running":true,"Paused":false,"Restarting":false,"OOMKilled":false,"Dead":false,"Pid":252607,"ExitCode":0,"Error":"","StartedAt":"2026-06-22T08:01:50.811288711Z","FinishedAt":"0001-01-01T00:00:00Z","Health":{"Status":"unhealthy","FailingStreak":18,"Log":[{"Start":"2026-06-22T16:09:22.429994017+08:00","End":"2026-06-22T16:09:22.484451787+08:00","ExitCode":1,"Output":"Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n  File \"/app/apps/worker/celery_app.py\", line 3, in <module>\n    from celery import Celery\nModuleNotFoundError: No module named 'celery'\n"},{"Start":"2026-06-22T16:09:52.485376338+08:00","End":"2026-06-22T16:09:52.544111403+08:00","ExitCode":1,"Output":"Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n  File \"/app/apps/worker/celery_app.py\", line 3, in <module>\n    from celery import Celery\nModuleNotFoundError: No module named 'celery'\n"},{"Start":"2026-06-22T16:10:22.544965252+08:00","End":"2026-06-22T16:10:22.601475012+08:00","ExitCode":1,"Output":"Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n  File \"/app/apps/worker/celery_app.py\", line 3, in <module>\n    from celery import Celery\nModuleNotFoundError: No module named 'celery'\n"},{"Start":"2026-06-22T16:10:52.602087008+08:00","End":"2026-06-22T16:10:52.659497614+08:00","ExitCode":1,"Output":"Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n  File \"/app/apps/worker/celery_app.py\", line 3, in <module>\n    from celery import Celery\nModuleNotFoundError: No module named 'celery'\n"},{"Start":"2026-06-22T16:11:22.660802652+08:00","End":"2026-06-22T16:11:22.723799045+08:00","ExitCode":1,"Output":"Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\n  File \"/app/apps/worker/celery_app.py\", line 3, in <module>\n    from celery import Celery\nModuleNotFoundError: No module named 'celery'\n"}]}}
Entrypoint=null
Cmd=["uv","run","celery","-A","apps.worker.celery_app","worker","--loglevel=INFO","--concurrency=1"]
Healthcheck={"Test":["CMD","python","-c","from apps.worker.celery_app import ping; assert ping.run() == 'pong'"],"Interval":30000000000,"Timeout":10000000000,"StartPeriod":60000000000,"Retries":5}
=== scheduler cid=601cd4ac69da2f5826acbda22c825a49de8dc5632de71db5f86c0df314fde515 ===
Name=/w2-staging-scheduler-1
State={"Status":"restarting","Running":true,"Paused":false,"Restarting":true,"OOMKilled":false,"Dead":false,"Pid":0,"ExitCode":0,"Error":"","StartedAt":"2026-06-22T08:11:40.720991852Z","FinishedAt":"2026-06-22T08:11:40.886443019Z","Health":{"Status":"unhealthy","FailingStreak":0,"Log":[]}}
Entrypoint=null
Cmd=["uv","run","python","-m","apps.scheduler.main"]
Healthcheck={"Test":["CMD","python","-c","from apps.scheduler.main import heartbeat; assert 'heartbeat' in heartbeat()"],"Interval":30000000000,"Timeout":10000000000,"StartPeriod":30000000000,"Retries":3}

```


## Diagnosis Summary (2026-06-22T08:14:33.055636+00:00)

- Worker category: `WORKER_HEALTHCHECK_INVALID`
- Worker evidence: Celery worker process is running and ready, but Docker healthcheck used system `python`; dependency import failed with `ModuleNotFoundError: No module named 'celery'`.
- Scheduler category: `SCHEDULER_COMMAND_ERROR`
- Scheduler evidence: `apps.scheduler.main` emitted heartbeat and exited normally; with `restart: unless-stopped`, Docker kept restarting the container.
- Public port audit: business ports remain bound to `127.0.0.1`; public listener is SSH 22 only.
- Secret handling: logs were collected through redaction filters; no API key, database password, or full database URL is recorded intentionally.

## Local Fix

- `apps/scheduler/main.py`: keep scheduler process alive with a heartbeat loop while preserving callable `heartbeat()` for smoke checks.
- `infra/compose/compose.staging.yml`: worker/scheduler healthchecks now use `uv run python` so they run inside the project dependency environment.
- `infra/compose/staging-lite.override.yml`: same healthcheck fix for the staging-lite compose variant.

## Local Verification

- `make verify`: PASS
- `git diff --check`: PASS
- `secret scan`: PASS; placeholder variable names are allowed, no secret values found.

## Pending High-Risk Server Step

Publishing a new release, switching `/opt/w2/current`, running migration no-op, and restarting `w2-staging.service` are pending explicit approval.

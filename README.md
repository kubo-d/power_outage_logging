Overview
--------
Docker Compose stack for remote logging, storage, dashboards, and monitoring:

- `nginx-auth` — auth proxy that checks `Authorization: Bearer <API_KEY>` and proxies to Vector
- `vector` — log ingestion (HTTP source) that forwards logs to Loki
- `loki` — Grafana Loki for log storage backed by MinIO (S3)
- `minio` — S3-compatible object storage used by Loki
- `grafana` — Grafana with a pre-provisioned Loki datasource
- `heartbeat-monitor` — queries Loki for device heartbeats and sends Pushover alerts

Quick deployment (local Docker on Hetzner VM)
---------------------------------------------
1. Copy the directory to your Hetzner server (e.g., `/opt/pow-logs`).
2. Create a small `.env` with a secure API key:

   REMOTE_LOG_API_KEY=supersecret_api_key_here

  Optionally, set `PUSHOVER_API_TOKEN` to enable heartbeat alerts.

3. Run:

   docker compose up -d

Configuration
-------------
- REMOTE_LOG_API_KEY: required; checked by the `nginx-auth` proxy for POSTs to `/api/logs`.
- PUSHOVER_API_TOKEN: optional; enables alerts from `heartbeat-monitor`.
- HEARTBEAT_THRESHOLD_MIN: optional; minutes without heartbeat before a device is marked offline (default 15).

You can set these via a `.env` file (used by `docker-compose`) or directly in your deployment platform (e.g., Coolify app settings).

Optional heartbeat monitor tuning
---------------------------------
- LOKI_URL: Loki endpoint (default `http://loki:3100`).
- POLL_INTERVAL_SEC: Polling interval in seconds (default 60).
- QUERY_WINDOW_HOURS: Hours to look back for heartbeats (default 24).
- LOKI_QUERY_LIMIT: Max entries per query (default 5000; must be ≤ Loki `max_entries_limit`).
- LOKI_TIMEOUT_SEC: HTTP timeout for Loki requests (default 20).
- DEFAULT_PUSHOVER_RETRY_SEC: Fallback retry seconds for emergency notifications (default 60).
- DEFAULT_PUSHOVER_EXPIRE_SEC: Fallback expire seconds for emergency notifications (default 3600).
- LOG_LEVEL: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO`).

Using Coolify
-------------
- You can deploy either the entire Docker Compose stack directly on the VM or deploy `nginx-auth` as a Coolify app and keep the other services private on the same host.
- If you use Coolify to expose `nginx-auth`, set the domain (e.g., `logs.example.com`) and enable HTTPS via Coolify. Set the environment variable `API_KEY` in the app settings to the same value you put in your device config.

Verify the ingestion endpoint
----------------------------
Example (replace with your domain):

  curl -v -X POST https://logs.example.com/api/logs \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer supersecret_api_key_here' \
    -d '{"device_id":"d1mini-01","timestamp":1670000000,"level":"info","logger":"test","msg":"hello"}'

You should see `200 OK` and the log should appear in Grafana Explore (Data source: Loki).

Notes
-----
- Loki stores logs in MinIO (S3) with a default retention of 7 days.
- The `minio-init` helper creates the `loki` bucket automatically.

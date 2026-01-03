Overview
--------
This directory contains a small Docker Compose stack for testing remote logging from devices:

- `nginx-auth` — minimal auth proxy that checks `Authorization: Bearer <API_KEY>` and proxies to Vector
- `vector` — Vector ingestion (HTTP source) that forwards logs to Loki
- `loki` — Grafana Loki for log storage (local filesystem)
- `grafana` — Grafana with a pre-provisioned Loki datasource

Quick deployment (local Docker on Hetzner VM)
---------------------------------------------
1. Copy the directory to your Hetzner server (e.g., `/opt/pow-logs`).
2. Create a small `.env` with a secure API key:

   REMOTE_LOG_API_KEY=supersecret_api_key_here

3. Run:

   docker compose up -d

Using Coolify
-------------
- You can deploy either the entire Docker Compose stack directly on the VM or deploy `nginx-auth` as a Coolify app and keep the other services private on the same host.
- If you use Coolify to expose `nginx-auth`, set the domain (e.g., `logs.example.com`) and enable HTTPS via Coolify. Set the environment variable `API_KEY` in the app settings to the same value you put in your device config.

Test the ingestion endpoint
---------------------------
Example (replace with your domain):

  curl -v -X POST https://logs.example.com/api/logs \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer supersecret_api_key_here' \
    -d '{"device_id":"d1mini-01","timestamp":1670000000,"level":"info","logger":"test","msg":"hello"}'

You should see `200 OK` and the log should appear in Grafana Explore (Data source: Loki).

Notes & security
----------------
- This setup is minimal and intended for testing. For production consider:
  - TLS termination at Coolify (recommended)
  - Rate limiting, IP filtering or firewall rules
  - Using object storage for Loki (S3) and proper retention/compaction tuning
  - Using Vector’s disk buffer to avoid data loss on restarts

If you want, I can also:
- Provide a `systemd` service or Coolify-specific instructions for deploying the entire compose stack
- Add an example Grafana dashboard and provisioning for alerts
- Implement an alternative auth proxy (FastAPI) if you prefer a more flexible auth flow

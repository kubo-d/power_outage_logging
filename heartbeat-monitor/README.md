# Heartbeat Monitor

A lightweight service that queries Loki for device heartbeats and sends Pushover notifications when a device goes offline or back online.

## Configuration

Environment variables (configured in Coolify or docker-compose):
- `LOKI_URL`: Loki endpoint (default `http://loki:3100`).
- `PUSHOVER_API_TOKEN`: Pushover app token (required).
- `HEARTBEAT_THRESHOLD_MIN`: Minutes without heartbeat to consider offline (default 15).
- `POLL_INTERVAL_SEC`: Poll loop interval (default 60).

State is persisted at `/data/state.json` using a named volume `heartbeat_state`.

## How it works
- Queries LogQL: `{app="power-outage"} | json | type="heartbeat"` for the last 24 hours.
- Parses latest heartbeat per `device_id` and compares against the threshold.
- Sends Pushover to the device's `pushover_user_key` with a brief message and `pushover_sound`.
- Avoids duplicate alerts and sends a recovery notification when heartbeats resume.

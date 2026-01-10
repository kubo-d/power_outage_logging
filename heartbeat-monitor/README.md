# Heartbeat Monitor

A lightweight service that queries Loki for device heartbeats and sends Pushover notifications when a device goes offline or back online.

## Configuration

Environment variables (configured in Coolify or docker-compose):
- `LOKI_URL`: Loki endpoint (default `http://loki:3100`).
- `PUSHOVER_API_TOKEN`: Pushover app token (required).
- `HEARTBEAT_THRESHOLD_MIN`: Minutes without heartbeat to consider offline (default 15).
- `POLL_INTERVAL_SEC`: Poll loop interval (default 60).
 - `QUERY_WINDOW_HOURS`: How far back to search for heartbeats (default 24).
 - `LOKI_QUERY_LIMIT`: Max entries per query (default 5000; must be ≤ Loki's `max_entries_limit`).
 - `LOKI_TIMEOUT_SEC`: HTTP timeout for Loki requests (default 20).

State is persisted at `/data/state.json` using a named volume `heartbeat_state`.

## How it works
- Queries LogQL: `{app="power-outage"} |= "heartbeat"` over the window, using backward direction to get recent entries first.
- Parses the latest heartbeat per `device_id` and compares against the threshold.
- Sends Pushover to the device's `pushover_user_key` with a brief message and `pushover_sound`.
- Avoids duplicate alerts and sends a recovery notification when heartbeats resume.

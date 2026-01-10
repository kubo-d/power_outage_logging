# Heartbeat Monitor

A lightweight service that queries Loki for device heartbeats and sends Pushover notifications when a device goes offline or back online.

## Configuration

Environment variables (configured in Coolify or docker-compose):
 - `QUERY_WINDOW_HOURS`: How far back to search for heartbeats (default 24).
 - `LOKI_QUERY_LIMIT`: Max entries per query (default 5000; must be ≤ Loki's `max_entries_limit`).
 - `LOKI_TIMEOUT_SEC`: HTTP timeout for Loki requests (default 20).
 - `DEFAULT_PUSHOVER_RETRY_SEC`: Fallback retry seconds for emergency notifications if missing in logs (default 60).
 - `DEFAULT_PUSHOVER_EXPIRE_SEC`: Fallback expire seconds for emergency notifications if missing in logs (default 3600).
 - `LOG_LEVEL`: Set logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO`).

State is persisted at `/data/state.json` using a named volume `heartbeat_state`.
- Queries LogQL: `{app="power-outage"} |= "heartbeat"` over the window, using backward direction to get recent entries first.
- Parses the latest heartbeat per `device_id` and compares against the threshold.
 - Sends Pushover offline alerts with priority 2 (emergency), using `pushover_retry` and `pushover_expire` from logs (or defaults), and `pushover_sound`.
 - Sends recovery notifications with default priority (0) without retry/expire.

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
 - `DEFAULT_PUSHOVER_RETRY_SEC`: Fallback retry seconds for emergency notifications if missing in logs (default 60).
 - `DEFAULT_PUSHOVER_EXPIRE_SEC`: Fallback expire seconds for emergency notifications if missing in logs (default 3600).
 - `LOG_LEVEL`: Set logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO`).
 - `LOGQL_QUERY`: Override the LogQL used for querying heartbeats (default `{app="power-outage", type="heartbeat"}`).
 - `TIMEZONE`/`TZ`: Optional timezone for formatting timestamps in notifications (e.g., `Europe/Prague`).
 

State is persisted at `/data/state.json` using a named volume `heartbeat_state`.

## How it works
- Queries LogQL: `{app="power-outage", type="heartbeat"}` over the window, using backward direction to get recent entries first.
- Parses the latest heartbeat per `device_id` and compares against the threshold.
- Sends Pushover offline alerts with priority 2 (emergency), using `pushover_retry` and `pushover_expire` from logs (or defaults), and `pushover_sound`.
- Sends recovery notifications with default priority (0) without retry/expire.

Label filters supported (delimited by commas inside braces), for example:
- Filter by device: `{app="power-outage", type="heartbeat", device_id="aa:bb:cc:dd:ee:ff"}`
- Filter by hostname: `{app="power-outage", type="heartbeat", hostname="my-sensor"}`

Device naming: if the firmware includes `device_name` in heartbeat logs, the monitor uses it in notifications; otherwise it falls back to `device_id` (MAC).

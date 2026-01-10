#!/usr/bin/env python3
import os
import time
import json
import signal
from typing import Dict, Any
import requests
import logging

# Loki endpoint
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")
HEARTBEAT_THRESHOLD_MIN = int(os.environ.get("HEARTBEAT_THRESHOLD_MIN", "15"))
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
STATE_PATH = os.environ.get("STATE_PATH", "/data/state.json")
QUERY_WINDOW_HOURS = int(os.environ.get("QUERY_WINDOW_HOURS", "24"))
# Max entries per query; Loki often caps at 5000
LOKI_QUERY_LIMIT = int(os.environ.get("LOKI_QUERY_LIMIT", "5000"))
# Per-request timeout to Loki in seconds
LOKI_TIMEOUT_SEC = int(os.environ.get("LOKI_TIMEOUT_SEC", "20"))
# Default emergency parameters if not provided in logs
DEFAULT_PUSHOVER_RETRY_SEC = int(os.environ.get("DEFAULT_PUSHOVER_RETRY_SEC", "60"))
DEFAULT_PUSHOVER_EXPIRE_SEC = int(os.environ.get("DEFAULT_PUSHOVER_EXPIRE_SEC", "3600"))
LOGQL_QUERY = os.environ.get(
    "LOGQL_QUERY",
    '{app="power-outage"} |= "heartbeat"'
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "heartbeat-monitor/1.0"})

_running = True

# Logging setup
LOG_LEVEL_NAME = os.environ.get("LOG_LEVEL", "INFO").upper()
_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
logging.basicConfig(
    level=_LEVELS.get(LOG_LEVEL_NAME, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)

def _handle_sigterm(signum, frame):
    global _running
    _running = False

signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"devices": {}}


def save_state(state: Dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        logging.error(f"[STATE] Failed to save state: {e}")


def query_heartbeats() -> Dict[str, Dict[str, Any]]:
    """
    Query Loki for heartbeat logs in the last window and return latest per device_id.
    """
    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - QUERY_WINDOW_HOURS * 3600 * int(1e9)
    params = {
        "query": LOGQL_QUERY,
        "start": str(start_ns),
        "end": str(now_ns),
        # Get latest entries first to quickly find recent heartbeats
        "direction": "backward",
        "limit": str(LOKI_QUERY_LIMIT),
    }
    url = f"{LOKI_URL}/loki/api/v1/query_range"
    logging.debug(f"[LOKI] Querying range: start={start_ns} end={now_ns} limit={LOKI_QUERY_LIMIT} direction=backward")
    try:
        resp = SESSION.get(url, params=params, timeout=LOKI_TIMEOUT_SEC)
        if resp.status_code >= 200 and resp.status_code < 300:
            data = resp.json()
            logging.debug(f"[LOKI] Query ok: resultType={data.get('data', {}).get('resultType')} count={len(data.get('data', {}).get('result', []))}")
        else:
            logging.warning(f"[LOKI] Query failed: HTTP {resp.status_code} body={resp.text}")
            # Fallback: try a simpler query
            fallback = '{app="power-outage"} |= "heartbeat"'
            if LOGQL_QUERY != fallback:
                logging.info("[LOKI] Retrying with fallback query")
                params["query"] = fallback
                resp = SESSION.get(url, params=params, timeout=LOKI_TIMEOUT_SEC)
                if resp.status_code >= 200 and resp.status_code < 300:
                    data = resp.json()
                    logging.debug(f"[LOKI] Fallback ok: count={len(data.get('data', {}).get('result', []))}")
                else:
                    logging.error(f"[LOKI] Fallback failed: HTTP {resp.status_code} body={resp.text}")
                    return {}
            else:
                return {}
    except Exception as e:
        logging.error(f"[LOKI] Query exception: {e}")
        return {}

    latest: Dict[str, Dict[str, Any]] = {}
    results = data.get("data", {}).get("result", [])
    for stream in results:
        values = stream.get("values", [])
        for ts_str, line in values:
            try:
                ts_ns = int(ts_str)
            except Exception:
                continue
            # Parse JSON line if possible; otherwise skip
            try:
                obj = json.loads(line)
            except Exception:
                continue
            # Accept entries that look like heartbeats without relying on strict LogQL filters
            if obj.get("type") != "heartbeat":
                continue
            device_id = obj.get("device_id") or "unknown"
            entry = latest.get(device_id)
            if entry is None or ts_ns > entry["ts_ns"]:
                latest[device_id] = {
                    "ts_ns": ts_ns,
                    "hostname": obj.get("hostname"),
                    "ip": obj.get("ip"),
                    "pushover_user_key": obj.get("pushover_user_key"),
                    "pushover_sound": obj.get("pushover_sound"),
                    "pushover_retry": obj.get("pushover_retry"),
                    "pushover_expire": obj.get("pushover_expire"),
                }
    logging.info(f"[LOKI] Latest heartbeats parsed for {len(latest)} device(s)")
    return latest


def send_pushover(user_key: str, title: str, message: str, sound: str = None, priority: int = None, retry: int = None, expire: int = None) -> bool:
    if not PUSHOVER_API_TOKEN or not user_key:
        return False
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": user_key,
        "title": title,
        "message": message,
    }
    if sound:
        payload["sound"] = sound
    if priority is not None:
        payload["priority"] = int(priority)
        if int(priority) == 2:
            # Emergency requires retry and expire
            payload["retry"] = int(retry) if retry is not None else DEFAULT_PUSHOVER_RETRY_SEC
            payload["expire"] = int(expire) if expire is not None else DEFAULT_PUSHOVER_EXPIRE_SEC
    try:
        r = SESSION.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)
        ok = r.status_code >= 200 and r.status_code < 300
        if not ok:
            logging.error(f"[PUSH] Send failed: status={r.status_code} body={r.text}")
        return ok
    except Exception as e:
        logging.error(f"[PUSH] Exception: {e}")
        return False


def monitor_loop():
    logging.info("[HB] Monitor starting...")
    state = load_state()
    devices_state: Dict[str, Any] = state.setdefault("devices", {})
    threshold_sec = HEARTBEAT_THRESHOLD_MIN * 60
    while _running:
        latest = query_heartbeats()
        now_ns = int(time.time() * 1e9)
        for device_id, info in latest.items():
            last_seen_sec = info["ts_ns"] / 1e9
            offline = (time.time() - last_seen_sec) > threshold_sec
            st = devices_state.setdefault(device_id, {})
            was_alerted = bool(st.get("alerted"))
            user_key = info.get("pushover_user_key")
            sound = info.get("pushover_sound")
            hostname = info.get("hostname") or device_id
            ip = info.get("ip") or ""
            # Emergency parameters from heartbeat or defaults
            try:
                hb_retry = int(info.get("pushover_retry")) if info.get("pushover_retry") is not None else DEFAULT_PUSHOVER_RETRY_SEC
            except Exception:
                hb_retry = DEFAULT_PUSHOVER_RETRY_SEC
            try:
                hb_expire = int(info.get("pushover_expire")) if info.get("pushover_expire") is not None else DEFAULT_PUSHOVER_EXPIRE_SEC
            except Exception:
                hb_expire = DEFAULT_PUSHOVER_EXPIRE_SEC

            logging.debug(
                f"[HB] device={device_id} host={hostname} last_seen={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen_sec))} "
                f"age_sec={int(time.time()-last_seen_sec)} offline={offline} was_alerted={was_alerted} "
                f"user_key={'yes' if user_key else 'no'} retry={hb_retry} expire={hb_expire}"
            )
            if offline and not was_alerted:
                msg = f"Device offline: {hostname} ({device_id})\nLast seen: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen_sec))}\nIP: {ip}"
                if send_pushover(user_key, "Power Outage Detector Offline", msg, sound, priority=2, retry=hb_retry, expire=hb_expire):
                    st["alerted"] = True
                    st["last_offline_ts"] = int(time.time())
                    logging.info(f"[HB] Alerted offline: {device_id}")
            elif (not offline) and was_alerted:
                msg = f"Device back online: {hostname} ({device_id})\nIP: {ip}"
                # Recovery notification: default priority (0), no retry/expire
                if send_pushover(user_key, "Power Outage Detector Online", msg, sound, priority=0):
                    st["alerted"] = False
                    st["last_online_ts"] = int(time.time())
                    logging.info(f"[HB] Cleared alert: {device_id}")
                else:
                    logging.warning(f"[HB] Failed to send recovery for {device_id}")
            # always update last seen info
            st["last_seen_ts"] = int(last_seen_sec)
            st["hostname"] = hostname
            st["ip"] = ip
        save_state(state)
        # sleep
        for _ in range(POLL_INTERVAL_SEC):
            if not _running:
                break
            time.sleep(1)


if __name__ == "__main__":
    monitor_loop()

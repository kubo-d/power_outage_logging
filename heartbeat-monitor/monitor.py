#!/usr/bin/env python3
import os
import time
import json
import signal
from typing import Dict, Any
import requests

# Loki endpoint
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")
HEARTBEAT_THRESHOLD_MIN = int(os.environ.get("HEARTBEAT_THRESHOLD_MIN", "15"))
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
STATE_PATH = os.environ.get("STATE_PATH", "/data/state.json")
QUERY_WINDOW_HOURS = int(os.environ.get("QUERY_WINDOW_HOURS", "24"))
# Max entries per query; Loki often caps at 5000
LOKI_QUERY_LIMIT = int(os.environ.get("LOKI_QUERY_LIMIT", "5000"))
LOGQL_QUERY = os.environ.get(
    "LOGQL_QUERY",
    '{app="power-outage"} |= "heartbeat"'
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "heartbeat-monitor/1.0"})

_running = True

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
        print(f"[STATE] Failed to save state: {e}")


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
    try:
        resp = SESSION.get(url, params=params, timeout=10)
        if resp.status_code >= 200 and resp.status_code < 300:
            data = resp.json()
        else:
            print(f"[LOKI] Query failed: HTTP {resp.status_code} body={resp.text}")
            # Fallback: try a simpler query
            fallback = '{app="power-outage"} |= "heartbeat"'
            if LOGQL_QUERY != fallback:
                print("[LOKI] Retrying with fallback query")
                params["query"] = fallback
                resp = SESSION.get(url, params=params, timeout=10)
                if resp.status_code >= 200 and resp.status_code < 300:
                    data = resp.json()
                else:
                    print(f"[LOKI] Fallback failed: HTTP {resp.status_code} body={resp.text}")
                    return {}
            else:
                return {}
    except Exception as e:
        print(f"[LOKI] Query exception: {e}")
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
                }
    return latest


def send_pushover(user_key: str, title: str, message: str, sound: str = None) -> bool:
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
    try:
        r = SESSION.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)
        ok = r.status_code >= 200 and r.status_code < 300
        if not ok:
            print(f"[PUSH] Send failed: {r.status_code} {r.text}")
        return ok
    except Exception as e:
        print(f"[PUSH] Exception: {e}")
        return False


def monitor_loop():
    print("[HB] Monitor starting...")
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
            if offline and not was_alerted:
                msg = f"Device offline: {hostname} ({device_id})\nLast seen: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen_sec))}\nIP: {ip}"
                if send_pushover(user_key, "Power Outage Detector Offline", msg, sound):
                    st["alerted"] = True
                    st["last_offline_ts"] = int(time.time())
                    print(f"[HB] Alerted offline: {device_id}")
            elif (not offline) and was_alerted:
                msg = f"Device back online: {hostname} ({device_id})\nIP: {ip}"
                if send_pushover(user_key, "Power Outage Detector Online", msg, sound):
                    st["alerted"] = False
                    st["last_online_ts"] = int(time.time())
                    print(f"[HB] Cleared alert: {device_id}")
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

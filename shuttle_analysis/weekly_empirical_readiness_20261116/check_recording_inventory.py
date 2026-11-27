"""Read recording coverage only. Never polls transit providers or opens held-out labels."""
from pathlib import Path
import concurrent.futures
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import os
import subprocess
from urllib.parse import urlsplit

OUT = Path(__file__).resolve().parent
KST = dt.timezone(dt.timedelta(hours=9))

class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

def credentials():
    path = Path(os.environ["LOCALAPPDATA"]) / "SnuTransit/credentials/collector_backend.dpapi"
    payload = path.read_bytes()
    lib = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(payload)
    original = Blob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    fn = lib.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(original), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError("Private collector credential could not be read")
    try:
        c = json.loads(ctypes.string_at(result.pbData, result.cbData))
    finally:
        kernel.LocalFree(result.pbData)
    address = urlsplit(c["url"])
    if address.scheme != "https" or not address.hostname.endswith(".workers.dev"):
        raise RuntimeError("Unexpected collector destination; no credential transmitted")
    return c

def fetch(c, endpoint):
    config = ('url="' + c["url"].rstrip("/") + endpoint + '"\n'
              'header="Authorization: Bearer ' + c["token"] + '"\n'
              'user-agent="SNU-ReadOnly-Coverage-Review/1.0"\n')
    r = subprocess.run(["curl.exe", "--config", "-", "--silent", "--show-error",
                        "--fail", "--max-time", "25", "--connect-timeout", "10"],
                       input=config.encode(), capture_output=True, timeout=30)
    if r.returncode:
        return {"endpoint": endpoint, "error": "saved_endpoint_read_failed",
                "curl_exit": r.returncode}
    try:
        return {"endpoint": endpoint, "value": json.loads(r.stdout)}
    except (ValueError, UnicodeError):
        return {"endpoint": endpoint, "error": "non_json_saved_response"}

def main():
    c = credentials()
    end = dt.date(2026, 11, 15)
    days = [(end - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    endpoints = ["/status"] + ["/recording?day=" + day for day in days]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda endpoint: fetch(c, endpoint), endpoints))
    status = results[0].get("value", {})
    status_summary = {k: status.get(k) for k in [
        "server_time", "captured_at", "enabled", "configured", "mode",
        "position_calls_today", "position_calls_remaining", "position_app_daily_limit",
        "next_scheduled_at", "usage"]}
    status_summary["status_keys"] = list(status)
    status_summary["snapshot_route_count"] = len(status.get("routes", []))
    recording = []
    for day, item in zip(days, results[1:]):
        if "value" not in item:
            recording.append({"requested_day": day, **item})
            continue
        value = item["value"]
        recording.append({"requested_day": day, "day": value.get("day"),
                          "unit": value.get("unit"), "routes": value.get("routes", []),
                          "raw_retention_days": value.get("raw_retention_days"),
                          "aggregate_retention_days": value.get("aggregate_retention_days")})
    record = {
        "retrieved_at": dt.datetime.now(KST).isoformat(),
        "source": "Authenticated existing Cloudflare collector recording/status metadata",
        "period_kst": [days[0], days[-1]],
        "saved_endpoint_requests": len(endpoints),
        "new_transit_provider_polls": 0,
        "raw_or_aggregate_export_endpoints_opened": False,
        "new_held_out_prediction_errors_or_labels_opened": False,
        "collector_control_mutations": 0,
        "status_summary": status_summary,
        "days": recording,
        "errors": [item for item in results if "error" in item],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    target = OUT / "recording_inventory.json"
    if target.exists():
        raise RuntimeError("Preserve previous evidence; output already exists")
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [{"day": r.get("day", r["requested_day"]),
             "routes": len(r.get("routes", [])),
             "grade_observations": sum(x.get("grade_observations", 0) for x in r.get("routes", [])),
             "headway_intervals": sum(x.get("observed_stop_headways", 0) for x in r.get("routes", [])),
             "shuttle_routes": [x["route"] for x in r.get("routes", []) if x["route"].startswith("shuttle")],
             "error": r.get("error")} for r in recording]
    print(json.dumps({"coverage": rows, "errors": record["errors"],
                      "status_summary": status_summary, "saved": str(target)}, ensure_ascii=True))

if __name__ == "__main__":
    main()


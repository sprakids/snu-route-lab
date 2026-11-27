"""Capture one Seoul bus snapshot. No scheduling, embedded keys, or key logging."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


KST = timezone(timedelta(hours=9))
POSITION_URL = "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRtid"
SEARCH_URL = "http://m.bus.go.kr/mBus/bus/getBusRouteList.bms"
PATH_URL = "http://m.bus.go.kr/mBus/bus/getRouteAndPos.bms"
DEFAULT_ROUTES = ["5511", "5513", "5516", "관악02-1", "관악02-2"]
CROWD = {"0": "정보 없음", "3": "여유", "4": "보통", "5": "혼잡", "6": "매우 혼잡"}


def now():
    return datetime.now(KST)


def rows(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    raise ValueError("Expected an array or object, not an inferred empty result")


def safe_name(name):
    return re.sub(r"[^0-9A-Za-z가-힣_-]", "_", name)


def load_key(args):
    if args.key_file:
        path = Path(args.key_file)
        key = path.read_text(encoding="utf-8").strip()
        if args.consume_key_file:
            # Only consume the private temporary handoff files made for this task.
            temp = Path(os.environ["TEMP"]).resolve()
            if path.resolve().parent != temp or not path.name.startswith("seoul-bus-"):
                raise ValueError("Refusing to consume a non-task temporary key file")
            path.unlink()
    else:
        key = os.environ.get("SEOUL_BUS_SERVICE_KEY", "").strip()
        if not key:
            from credential_store import load_key as load_saved_key
            key = load_saved_key() or ""
    if not key:
        raise ValueError("No saved credential. Provide SEOUL_BUS_SERVICE_KEY or --key-file; never embed it in code")
    return urllib.parse.unquote(key)


def request_json(endpoint, params, directory, label, key, method="GET"):
    payload = urllib.parse.urlencode(params).encode("ascii")
    headers = {"User-Agent": "SNU-Transit-Research/0.1"}
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        request = urllib.request.Request(endpoint, data=payload, headers=headers)
    else:
        request = urllib.request.Request(endpoint + "?" + payload.decode(), headers=headers)
    receipt = {
        "endpoint": endpoint,
        "method": method,
        "params": {k: v for k, v in params.items() if k.lower() != "servicekey"},
        "requested_at_kst": now().isoformat(),
    }
    raw = None
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            receipt.update(http_status=response.status, content_type=response.headers.get("Content-Type"))
    except urllib.error.HTTPError as error:
        raw = error.read()
        receipt.update(http_status=error.code, error_type=type(error).__name__)
    except Exception as error:
        # An exception may contain the requested URL. Redact before writing anything.
        message = str(error)
        for token in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
            message = message.replace(token, "[REDACTED]")
        receipt.update(error_type=type(error).__name__, error=message)
    receipt["received_at_kst"] = now().isoformat()
    data = None
    if raw is not None:
        receipt["response_sha256_before_redaction"] = hashlib.sha256(raw).hexdigest()
        original = raw.decode("utf-8", errors="replace")
        text = original
        for token in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
            text = text.replace(token, "[REDACTED]")
        receipt["credential_redacted_from_response"] = original != text
        suffix = ".json" if text.lstrip().startswith(("{", "[")) else ".txt"
        filename = safe_name(label) + suffix
        (directory / filename).write_text(text, encoding="utf-8")
        receipt["response_file"] = filename
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            receipt["parse_error"] = "Response is not JSON; preserved as received, except credential redaction"
    return data, receipt


def capture_route(route, key, raw_dir):
    name, route_id = route["busRouteNm"], str(route["busRouteId"])
    path_data, path_receipt = request_json(
        PATH_URL, {"busRouteId": route_id}, raw_dir, "stops_" + name, key, "POST"
    )
    stops = []
    if path_data and path_data.get("error", {}).get("errorCode") == "0000":
        stops = rows(path_data.get("resultList"))
    stop_names = {str(s.get("station")): s.get("stationNm", "") for s in stops}

    data, receipt = request_json(
        POSITION_URL,
        {"serviceKey": key, "busRouteId": route_id, "resultType": "json"},
        raw_dir, "positions_" + name, key,
    )
    header = data.get("msgHeader", {}) if isinstance(data, dict) else {}
    receipt["api_header"] = header
    succeeded = receipt.get("http_status") == 200 and str(header.get("headerCd")) == "0"
    no_results = receipt.get("http_status") == 200 and str(header.get("headerCd")) == "4"
    vehicles = rows((data.get("msgBody") or {}).get("itemList")) if succeeded else []
    if succeeded and header.get("itemCount") is not None:
        receipt["header_item_count_matches_array"] = str(header["itemCount"]) == str(len(vehicles))
    normalized = []
    captured = datetime.fromisoformat(receipt["received_at_kst"])
    for vehicle in vehicles:
        code = str(vehicle.get("congetion", ""))
        source_time = vehicle.get("dataTm", "")
        source_iso, age = "", ""
        try:
            parsed = datetime.strptime(source_time, "%Y%m%d%H%M%S").replace(tzinfo=KST)
            source_iso = parsed.isoformat()
            age = round((captured - parsed).total_seconds(), 1)
        except (TypeError, ValueError):
            pass
        normalized.append({
            "route_name": name,
            "route_id": route_id,
            "captured_at_kst": receipt["received_at_kst"],
            "provider_time_raw": source_time,
            "provider_time_kst": source_iso,
            "data_age_seconds": age,
            "vehicle_id": vehicle.get("vehId", ""),
            "vehicle_plate": vehicle.get("plainNo", ""),
            "longitude": vehicle.get("gpsX", ""),
            "latitude": vehicle.get("gpsY", ""),
            "section_order": vehicle.get("sectOrd", ""),
            "last_stop_id": vehicle.get("lastStnId", ""),
            "last_stop_name": stop_names.get(str(vehicle.get("lastStnId")), ""),
            "congestion_raw": code,
            "congestion_label": CROWD.get(code, "정의 미확인" if code else "항목 없음"),
            "is_full_raw": vehicle.get("isFullFlag", ""),
            "is_running_raw": vehicle.get("isrunyn", ""),
            "is_last_bus_raw": vehicle.get("islastyn", ""),
        })
    summary = {
        "route_name": name,
        "route_id": route_id,
        "api_success": succeeded,
        "query_accepted": succeeded or no_results,
        "service_status": "vehicle_data" if succeeded else "no_results" if no_results else "service_error",
        "http_status": receipt.get("http_status"),
        "api_header": header,
        "stop_count": len(stops),
        "vehicle_record_count": len(normalized),
        "running_record_count": sum(v["is_running_raw"] == "1" for v in normalized),
        "congestion_counts": {label: sum(v["congestion_label"] == label for v in normalized)
                              for label in dict.fromkeys(v["congestion_label"] for v in normalized)},
        "captured_at_kst": receipt["received_at_kst"],
    }
    return normalized, summary, [path_receipt, receipt]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file")
    parser.add_argument("--consume-key-file", action="store_true")
    parser.add_argument("--routes", nargs="+", default=DEFAULT_ROUTES)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    key = load_key(args)
    started = now()
    out = args.output_root / ("snapshot_" + started.strftime("%Y%m%d_%H%M%S_%f"))
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True)
    manifest = {
        "started_at_kst": started.isoformat(),
        "mode": "one_snapshot_no_scheduler",
        "requested_routes": args.routes,
        "position_provider": "서울특별시 버스위치정보조회 OpenAPI",
        "route_and_stop_provider": "서울시 공식 모바일 버스정보 웹사이트의 조회 인터페이스",
        "interpretation": "Vehicle congestion, not stop queue size or exact passenger count. All route vehicles, not a campus-boundary filter.",
        "requests": [],
    }
    found = {}
    queries = list(dict.fromkeys("관악02" if name.startswith("관악02") else name for name in args.routes))
    for query in queries:
        # The site's JavaScript calls encodeURIComponent before jQuery serializes
        # the form, so Korean route searches require that same two-step encoding.
        data, receipt = request_json(SEARCH_URL, {"strSrch": urllib.parse.quote(query, safe="")}, raw_dir,
                                     "search_" + query, key, "POST")
        manifest["requests"].append(receipt)
        if data and data.get("error", {}).get("errorCode") == "0000":
            for route in rows(data.get("resultList")):
                name = str(route.get("busRouteNm", ""))
                if name in args.routes:
                    if name in found and found[name]["busRouteId"] != route["busRouteId"]:
                        raise ValueError("Ambiguous route identity: " + name)
                    found[name] = route
    manifest["unresolved_routes"] = [name for name in args.routes if name not in found]
    selected = [found[name] for name in args.routes if name in found]
    (out / "routes.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda r: capture_route(r, key, raw_dir), selected))
    records, summaries = [], []
    for values, summary, receipts in results:
        records.extend(values)
        summaries.append(summary)
        manifest["requests"].extend(receipts)
    (out / "vehicles.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    if records:
        with (out / "vehicles.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    manifest["route_summaries"] = summaries
    manifest["finished_at_kst"] = now().isoformat()
    manifest["complete"] = not manifest["unresolved_routes"] and all(s["query_accepted"] for s in summaries)
    manifest["vehicle_record_count"] = len(records)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_directory": str(out), "complete": manifest["complete"],
                      "unresolved_routes": manifest["unresolved_routes"],
                      "route_summaries": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

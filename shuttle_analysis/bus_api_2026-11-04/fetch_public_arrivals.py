"""One snapshot of public Seoul bus arrivals; does not require an API key."""

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


KST = timezone(timedelta(hours=9))
ENDPOINT = "http://m.bus.go.kr/mBus/bus/getArrInfoByRoute.bms"
CROWD = {"0": "정보 없음", "3": "여유", "4": "보통", "5": "혼잡"}
TARGETS = [
    ("5511", "100100250", "유회진학술정보관.제1공학관", "120000174", "66"),
    ("5513", "100100251", "자연대.행정관입구", "120000169", "39"),
    ("5516", "100100253", "유회진학술정보관.제1공학관", "120000174", "65"),
    ("관악02-1", "120900011", "유회진학술정보관.제1공학관", "120000174", "23"),
    ("관악02-2", "120900012", "행정관", "120000678", "18"),
]


def capture(target, raw_dir):
    name, route_id, stop_name, stop_id, order = target
    params = {"stId": stop_id, "busRouteId": route_id, "ord": order}
    receipt = {"route_name": name, "route_id": route_id, "station_name": stop_name,
               "station_id": stop_id, "stop_order": order, "endpoint": ENDPOINT,
               "params": params, "requested_at_kst": datetime.now(KST).isoformat()}
    observations = []
    try:
        request = urllib.request.Request(
            ENDPOINT, data=urllib.parse.urlencode(params).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            receipt["http_status"] = response.status
        receipt["captured_at_kst"] = datetime.now(KST).isoformat()
        filename = "arrivals_" + name + ".json"
        (raw_dir / filename).write_bytes(raw)
        receipt["response_file"] = "raw/" + filename
        receipt["response_sha256"] = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        receipt["api_error"] = data.get("error")
        items = data.get("resultList") or []
        receipt["record_count"] = len(items)
        if str(data.get("error", {}).get("errorCode")) != "0000":
            receipt["status"] = "service_error"
            return observations, receipt
        receipt["status"] = "ok" if items else "no_results"
        for item in items:
            if str(item.get("busRouteId")) != route_id or str(item.get("stId")) != stop_id or str(item.get("staOrd")) != order:
                raise ValueError("Returned route/station/sequence differs from the requested identity")
            source_time = item.get("mkTm", "")
            source_iso, age = "", ""
            try:
                source = datetime.fromisoformat(source_time).replace(tzinfo=KST)
                source_iso = source.isoformat()
                age = round((datetime.fromisoformat(receipt["captured_at_kst"]) - source).total_seconds(), 1)
            except (TypeError, ValueError):
                pass
            for rank in (1, 2):
                suffix = str(rank)
                vehicle_id = str(item.get("vehId" + suffix, ""))
                assigned = vehicle_id not in ("", "0", "None")
                value = str(item.get("reride_Num" + suffix, ""))
                kind = str(item.get("rerdie_Div" + suffix, ""))
                if not assigned:
                    label, meaning = "차량 미배정", "no_assigned_vehicle"
                elif kind == "4":
                    label, meaning = CROWD.get(value, "정의 미확인"), "congestion_category"
                elif kind == "2":
                    label, meaning = "재차인원 항목 제공(혼잡 등급 아님)", "onboard_count_or_seat_field"
                elif kind == "0":
                    label, meaning = "정보 없음", "no_data"
                else:
                    label, meaning = "혼잡도 구분 미확인", "unknown"
                observations.append({
                    "route_name": name, "route_id": route_id,
                    "target_stop_name": item.get("stNm", stop_name), "target_stop_id": stop_id,
                    "target_stop_order": order, "arrival_rank": rank,
                    "arrival_message": item.get("arrmsg" + suffix, ""),
                    "eta_seconds": item.get("traTime" + suffix, ""),
                    "vehicle_assigned": assigned, "vehicle_id": vehicle_id,
                    "vehicle_plate": item.get("plainNo" + suffix, ""),
                    "vehicle_reference_stop": item.get("stationNm" + suffix, ""),
                    "reride_division_raw": kind, "reride_value_raw": value,
                    "value_meaning": meaning, "congestion_label": label,
                    "is_full_raw": item.get("full" + suffix, ""),
                    "captured_at_kst": receipt["captured_at_kst"],
                    "provider_time_raw": source_time, "provider_time_kst": source_iso,
                    "data_age_seconds": age,
                })
    except Exception as error:
        receipt["status"] = "request_or_validation_error"
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
    return observations, receipt


def main():
    started = datetime.now(KST)
    root = Path(__file__).resolve().parent
    out = root / ("public_arrivals_" + started.strftime("%Y%m%d_%H%M%S_%f"))
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda target: capture(target, raw_dir), TARGETS))
    observations = [record for records, _ in results for record in records]
    receipts = [receipt for _, receipt in results]
    (out / "arrivals.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
    if observations:
        with (out / "arrivals.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(observations[0]))
            writer.writeheader()
            writer.writerows(observations)
    summary = []
    for name, route_id, stop_name, _, _ in TARGETS:
        values = [v for v in observations if v["route_id"] == route_id]
        summary.append({"route_name": name, "target_stop_name": stop_name,
                        "incoming": [{"rank": v["arrival_rank"], "assigned": v["vehicle_assigned"],
                                      "congestion": v["congestion_label"], "arrival": v["arrival_message"],
                                      "division_raw": v["reride_division_raw"], "value_raw": v["reride_value_raw"]}
                                     for v in values]})
    manifest = {
        "started_at_kst": started.isoformat(), "finished_at_kst": datetime.now(KST).isoformat(),
        "provider": "서울시 공식 모바일 버스정보 웹사이트 조회 인터페이스",
        "authentication": "No API key or portal login used",
        "scope": "First and second arrivals at one explicitly identified campus stop/sequence per route. Not all vehicles on each route.",
        "not_same_sampling_scope_as_0032_position_snapshot": True,
        "requests": receipts, "route_summaries": summary,
        "checks": {
            "all_five_queries_answered": len(receipts) == 5 and all(r.get("status") in ("ok", "no_results") for r in receipts),
            "record_count": len(observations),
            "unique_route_stop_rank_keys": len({(v['route_id'],v['target_stop_id'],v['target_stop_order'],v['arrival_rank']) for v in observations}),
            "assigned_vehicle_records": sum(v["vehicle_assigned"] for v in observations),
            "confirmed_congestion_category_records": sum(v["vehicle_assigned"] and v["value_meaning"] == "congestion_category" for v in observations),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_directory": str(out), "checks": manifest["checks"], "route_summaries": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

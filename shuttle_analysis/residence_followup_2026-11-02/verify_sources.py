"""Verify saved public questionnaires without contacting or submitting to any service."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"


def verify_form(stem, expected_items, expected_types):
    html = (SOURCES / f"{stem}.html").read_text(encoding="utf-8")
    marker = "FB_PUBLIC_LOAD_DATA_"
    remainder = html.split(marker, 1)[1].lstrip()
    assert remainder.startswith("="), "Expected a public form data assignment"
    payload, _ = json.JSONDecoder().raw_decode(remainder[1:].lstrip())
    saved_payload = json.loads((SOURCES / f"{stem}_공개문항정의.json").read_text(encoding="utf-8"))
    assert payload == saved_payload
    raw_items = payload[1][1]
    derived = json.loads((SOURCES / f"{stem}_문항목록.json").read_text(encoding="utf-8"))
    assert len(raw_items) == len(derived) == expected_items
    assert len({q[0] for q in raw_items}) == expected_items
    for original, extracted in zip(raw_items, derived):
        assert original[0:4] == [extracted[k] for k in ("id", "title", "description", "type_code")]
        options = []
        if len(original) > 4 and isinstance(original[4], list):
            for entry in original[4]:
                if len(entry) > 1 and isinstance(entry[1], list):
                    options.extend(o[0] for o in entry[1] if isinstance(o, list))
        assert options == extracted["options"]
    assert dict(Counter(q[3] for q in raw_items)) == expected_types
    return derived, {
        "public_payload_matches_html": True,
        "derived_items_match_public_payload": True,
        "item_ids_unique": True,
        "all_items_including_sections_and_images": expected_items,
        "types": expected_types,
    }


def by_prefix(items, prefix):
    return next(q for q in items if (q["title"] or "").startswith(prefix))


def main():
    q24, v24 = verify_form("F06_2024설문현재상태", 133, {0: 3, 2: 29, 8: 51, 4: 42, 1: 7, 11: 1})
    q23, v23 = verify_form("F07_2023설문현재상태", 110, {0: 3, 3: 1, 8: 35, 4: 38, 2: 19, 1: 10, 11: 4})
    q26, v26 = verify_form("F09_2026대학원설문", 49, {8: 9, 2: 18, 4: 16, 11: 1, 5: 1, 1: 1, 0: 3})
    assert {"공과대학-아랫공대", "공과대학-윗공대"} <= set(by_prefix(q24, "2.")["options"])
    assert all(by_prefix(q24, p)["type_code"] == 4 for p in ("11.", "12.", "13."))
    assert "24년 봄학기" in by_prefix(q24, "11.")["title"]
    assert "서울대입구역" in by_prefix(q24, "12.")["options"]
    assert "관악산역 (대학동 포함)" in by_prefix(q24, "12.")["options"]
    assert "행정관 셔틀 (대학동)" in by_prefix(q24, "13.")["options"]
    assert "셔틀버스 제외" in by_prefix(q24, "15.")["title"]
    assert "신설" in by_prefix(q24, "30.")["title"]
    assert "22년 가을학기" in next(q for q in q23 if "평소 하교" in (q["title"] or ""))["title"]
    assert len(by_prefix(q26, "Q6.")["options"]) == 5
    assert "F (신공학관 권역)" in by_prefix(q26, "Q17.")["options"]
    assert any("행정관 ↔ 대학동" in x for x in by_prefix(q26, "Q25.")["options"])
    assert "가장 늦은 퇴교" in by_prefix(q26, "Q11.")["title"]
    waf = list(SOURCES.glob("F0[2345]_*.json"))
    assert len(waf) == 4
    assert all("waf/error.html" in p.read_text(encoding="utf-8") for p in waf)

    source_files = [
        ("F01", "총학생회 교통총조사 공개 검색", "https://we.snu.ac.kr/?s=%EA%B5%90%ED%86%B5%EC%B4%9D%EC%A1%B0%EC%82%AC", "총학생회검색_교통총조사.html"),
        ("F07_notice", "2023 교통 총조사 공지를 포함한 공개 검색", "https://we.snu.ac.kr/?s=%EA%B5%90%ED%86%B5%20%EC%B4%9D%EC%A1%B0%EC%82%AC", "총학생회검색_교통_총조사.html"),
        ("F06", "2024 교통총조사 공개 설문", "https://docs.google.com/forms/d/e/1FAIpQLSdafiG0k6MP2CfAFOQEMFnKSfKKqVWXydFew2jcpEEMvPUMQg/viewform", "F06_2024설문현재상태.html"),
        ("F07", "2023 교통총조사 공개 설문", "https://docs.google.com/forms/d/e/1FAIpQLSdsEY0f-8qQJ_7pJj9brs0lEYHK5Yg5_UMF6vZnUUwuaflJ4w/viewform", "F07_2023설문현재상태.html"),
        ("F08", "김고은(2019) 국토계획 발행기관 논문 원문", "https://kpaj.or.kr/_PR/view/?aidx=21519&bidx=1740", "F08_거주동_학술논문.html"),
        ("F09", "2026 대학원생 교통총조사 공개 설문", "https://docs.google.com/forms/d/e/1FAIpQLSfvEou01TcRN17aLAAgoAa_PIK0ax3tm8i4ndkWvekPr-YJZg/viewform", "F09_2026대학원설문.html"),
    ]
    register = []
    for sid, title, url, name in source_files:
        p = SOURCES / name
        register.append({
            "id": sid, "title": title, "url": url,
            "local_file": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
            "file_saved_at_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
        })
    notice = ROOT.parent / "residence_commuting_2026-11-01/sources/R02_2026대학원생_교통총조사.html"
    assert notice.is_file()
    register.append({
        "id": "F09_notice", "title": "2026 대학원생 교통총조사 공식 공지",
        "url": "https://sgc.snu.ac.kr/bbs/board.php?bo_table=s3_3&wr_id=2",
        "verification": "Opened again via web tool on 2026-11-02; form link and announced dates checked; source saved in preceding collection.",
        "local_file": "../residence_commuting_2026-11-01/sources/R02_2026대학원생_교통총조사.html",
        "sha256": hashlib.sha256(notice.read_bytes()).hexdigest(),
        "announced_period": ["2026-09-02", "2026-12-14"],
    })
    (ROOT / "source_register.json").write_text(json.dumps(register, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "forms": {"2024": v24, "2023": v23, "2026_graduate": v26},
        "key_variables_checked": True,
        "response_records_acquired": False,
        "response_counts_acquired": False,
        "survey_submitted": False,
        "external_messages_sent": False,
        "waf_error_files_are_not_json_datasets": [str(p.relative_to(ROOT)) for p in waf],
        "unavailable_source": {"url": "https://bit.ly/광역셔틀_부활_", "status": "TLS certificate verification failed; no content acquired"},
        "interpretation_limits": [
            "Survey items and observed choices do not establish response frequencies.",
            "2024 access/transfer node is not a geographic residence variable.",
            "Multiple response selections do not establish trip-level linked time-destination-mode observations.",
            "2023 commute questions refer to fall 2022; 2024 questions to spring 2024.",
            "2026 graduate respondents must not be pooled with undergraduates without a justified design.",
            "Current public form versions have no verified historical change log.",
        ],
    }
    (ROOT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "forms": result["forms"], "responses_acquired": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

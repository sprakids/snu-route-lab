"""Reconcile the saved primary sources; never submit a form or infer missing responses."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources"


def form_items(stem):
    html = (SOURCE / f"{stem}.html").read_text(encoding="utf-8")
    remainder = html.split("FB_PUBLIC_LOAD_DATA_", 1)[1].lstrip()
    assert remainder.startswith("=")
    payload, _ = json.JSONDecoder().raw_decode(remainder[1:].lstrip())
    original = payload[1][1]
    saved = json.loads((SOURCE / f"{stem}_文項.json").read_text(encoding="utf-8"))
    assert len(original) == len(saved)
    for a, b in zip(original, saved):
        assert a[:4] == [b[k] for k in ("id", "title", "description", "type_code")]
        options = []
        if len(a) > 4 and isinstance(a[4], list):
            for entry in a[4]:
                if len(entry) > 1 and isinstance(entry[1], list):
                    options.extend(o[0] for o in entry[1] if isinstance(o, list))
        assert options == b["options"]
    return saved


def q(items, prefix):
    return next(x for x in items if (x["title"] or "").startswith(prefix))


def main():
    pdf = SOURCE / "C02_2025서울대통계연보.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    page = (SOURCE / "C02_page_203.txt").read_text(encoding="utf-8")
    assert re.search(r"2025\s+29,613\s+3,419\s+6,713\s+5,502\s+1,009\s+19\s+22\.7", page)
    assert "연건학부생활관" in page and "계약학과 제외" in page
    assert (SOURCE / "C02_page_203.png").is_file()
    degree_residents = 5502 + 1009
    assert degree_residents == 6511
    capacity_rate = 6713 / 29613 * 100
    reference_rate = degree_residents / 29613 * 100
    assert round(capacity_rate, 1) == 22.7
    assert round(reference_rate, 1) == 22.0
    dorm = (SOURCE / "C04_관악생활관_현황.txt").read_text(encoding="utf-8")
    assert all(x in dorm for x in ("3,122", "2,650", "5,772", "생활관 학생비율"))
    assert 3122 + 2650 == 5772
    q24 = form_items("C08_2024교통총조사_설문")
    q26 = form_items("C09_2026대학원교통조사_설문")
    assert len(q24) == 133 and len(q26) == 49
    assert "24년 봄학기" in q(q24, "11.")["title"]
    assert "관악산역 (대학동 포함)" in q(q24, "12.")["options"]
    assert all(q(q24, s)["type_code"] == 4 for s in ("11.", "12.", "13."))
    assert {"서울대입구역", "낙성대역", "기숙사"} <= set(q(q24, "12.")["options"])
    assert "공과대학-윗공대" in q(q24, "2.")["options"]
    assert "교내 기숙사 / On-campus dorm" in q(q26, "Q6.")["options"]
    assert "관악캠퍼스 / Gwanak Campus" in q(q26, "Q7.")["options"]
    assert "F (신공학관 권역)" in q(q26, "Q17.")["options"]
    assert "2026. 9. 2. ~ 2026. 12. 14." in (SOURCE / "C05_2026대학원조사_공지.txt").read_text(encoding="utf-8")
    rows = json.loads((ROOT / "capture.json").read_text(encoding="utf-8"))
    rows += json.loads((ROOT / "capture_additional.json").read_text(encoding="utf-8"))
    assert len(rows) == 9
    for row in rows:
        assert row.get("status") == 200
        p = ROOT / row["file"]
        assert len(p.read_bytes()) == row["bytes"]
        row["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT / "source_register.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "status": "PASS", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "pdf_page_visually_reviewed": 203,
        "requested_scope": {"term": "2026-2", "campus": "Gwanak", "population": "unique students taking Gwanak courses"},
        "requested_current_ratios": {"dorm_residence": None, "homeward_snu_station": None, "homeward_nakseongdae": None, "homeward_daehak_dong": None},
        "reference_only_2025_university_wide": {
            "source_date": "2025-04-01", "enrolled_students_A": 29613,
            "capacity_B": 6713, "actual_degree_residents": degree_residents,
            "actual_nondegree_foreign_residents_excluded_from_degree_total": 19,
            "official_capacity_percent": 22.7, "recomputed_capacity_percent": capacity_rate,
            "calculated_degree_residents_over_A_percent": reference_rate,
            "population_subset_consistency_not_verified": True,
        },
        "dorm_website": {"undergraduate": 3122, "graduate": 2650, "total": 5772, "statistical_reference_date": None, "interpretation": "composition within the dormitory table, not residence rate among Gwanak course takers"},
        "public_questionnaire_items_including_sections_and_images": {"2024": len(q24), "2026_graduate": len(q26)},
        "questionnaire_definition_verified": True,
        "daehak_dong_merged_with_gwanaksan_in_2024_destination_question": True,
        "multiple_response_destination_question": True,
        "response_results_acquired": False, "survey_submitted": False, "external_messages_sent": False,
    }
    (ROOT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    leads = [{
        "title": "서울대학교 관악캠퍼스 교통체계 마스터플랜 수립",
        "url": "https://www.scribd.com/document/881211763/",
        "discovery": "Public web search surfaced an external repost referring to historical April 2022 travel-card analysis.",
        "status": "Official issuing-body original not acquired; numerical values not adopted as verified findings.",
    }]
    (ROOT / "unverified_leads.json").write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "reference_2025_capacity_percent": round(capacity_rate, 1), "reference_2025_calculated_residence_percent": round(reference_rate, 1), "requested_current_ratios": result["requested_current_ratios"], "response_results_acquired": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

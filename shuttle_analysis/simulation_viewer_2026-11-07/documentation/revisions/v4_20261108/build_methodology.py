"""Publish one source document as readable HTML, Markdown, and evidence JSON.

The renderer intentionally supports only the small Markdown subset used by
methodology_source.md. It uses the standard library and never runs a simulation.
"""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import hashlib
import json
import math
import re

HERE = Path(__file__).resolve().parent
VIEWER = HERE.parent
ANALYSIS = VIEWER.parent
PUBLIC = VIEWER / "public"


def read(relative):
    return json.loads((ANALYSIS / relative).read_text(encoding="utf-8"))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def evidence():
    endings = read("scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json")
    endings = [r for r in endings if r["included_main"] and r["weekday"] in ("월", "화", "수", "목", "금") and r["end_minute"] <= 1390]
    counts = {"events": len(endings), "buildings": len({r["building"] for r in endings}), "enrollment_sum": sum(r["enrollment"] for r in endings)}
    assert counts == {"events": 6201, "buildings": 88, "enrollment_sum": 156338}
    quality = read("course_demand_2026-11-06/outputs/course_quality.json")
    assert quality["data_rows"] == 8654
    source_paths = [
        "course_demand_2026-11-06/sources/courses_2026-2_20261106.xls",
        "scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json",
        "course_demand_2026-11-06/sources/residence_user_reference.json",
        "scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/historical_reported_shares.json",
        "operation_plans_2026-11-01/sources/O11_2.pdf",
        "scenario_comparison_2026-11-07/scenario_specs.json",
        "simulation_viewer_2026-11-07/adaptive_model/route_verification.json",
        "simulation_viewer_2026-11-07/capacity_model.py",
        "simulation_viewer_2026-11-07/speed_capacity_model.py",
        "simulation_viewer_2026-11-07/adaptive_capacity_model.py",
        "simulation_viewer_2026-11-07/adaptive_model/independent_verification.json",
        "adaptive_comparison_2026-11-07/reviewed_results.json",
        "adaptive_comparison_2026-11-07/verification.json",
        "adaptive_comparison_2026-11-07/independent_check.json",
        "app/routing.py", "app/adaptive.py", "app/gate_service.py", "app/historical_forecast.py",
        "app/automatic_queue.py", "app/prepare_auto_queue.py", "app/data/auto_queue_inputs.json",
        "app/data/weekday_history.json", "app/data/travel_history.json",
    ]
    files = [{"path": name, "bytes": (ANALYSIS / name).stat().st_size,
              "sha256": hashlib.sha256((ANALYSIS / name).read_bytes()).hexdigest()} for name in source_paths]
    checks = read("adaptive_comparison_2026-11-07/verification.json")
    assert checks["status"] == "PASS"
    raw = read("adaptive_comparison_2026-11-07/reviewed_results.json")
    summaries = []
    for origin, scope, label in (
        ("all", "snu_all", "서울대입구행 전체"),
        ("all", "snu_initial_shuttle", "서울대입구행 · 최초 셔틀 집단"),
        ("301_302", "snu_all", "301·302동 출발 · 서울대입구행"),
    ):
        for scenario in ("peak", "regular"):
            rows = [r for r in raw["daily"] if r["origin"] == origin and r["scope"] == scope and r["period"] == "all" and r["scenario"] == scenario]
            assert len(rows) == 5
            weight = math.fsum(r["weight"] for r in rows)
            common = math.fsum(r["common_complete_weight"] for r in rows)
            summary = {"origin": origin, "scope": scope, "label": label, "scenario": scenario,
                       "weight": weight, "common_complete_weight": common,
                       "common_complete_share_pct": common / weight * 100}
            for phase in ("before", "after"):
                summary["wait_" + phase] = math.fsum(r["wait_all_min_" + phase] * r["weight"] for r in rows) / weight
                summary["total_" + phase] = math.fsum(r["total_common_min_" + phase] * r["common_complete_weight"] for r in rows) / common
                summary["unserved_" + phase] = math.fsum(r["unserved_weight_" + phase] for r in rows)
            summaries.append(summary)
    first = summaries[0]
    assert abs(first["wait_before"] - 5.124274073220033) < 1e-9
    assert abs(first["total_after"] - 19.712365420906732) < 1e-9
    result = {
        "document_date_kst": "2026-11-08", "simulation_version": "capacity_v4",
        "simulation_recomputed": False, "counts": counts,
        "raw_course_rows": quality["data_rows"], "immediate_trip_share_assumption": 0.5,
        "dorm_share_assumption": 5772 / 29613,
        "dorm_share_is_observed_gwanak_rate": False,
        "historical_destination_percentages": [55.7, 27.2, 17.0],
        "historical_destination_source_is_student_council_survey": False,
        "class_end_comparison_window": "11:20-23:10",
        "wait_denominator": "all original weighted particles in the fixed class-end cohort",
        "total_denominator": "same original whole particles completed under both policies",
        "summaries": summaries, "files": files,
    }
    return result


TOKEN = re.compile(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*")


def inline(text):
    result = []; previous = 0
    for m in TOKEN.finditer(text):
        result.append(escape(text[previous:m.start()]))
        if m.group(1) is not None:
            result.append("<code>" + escape(m.group(1)) + "</code>")
        elif m.group(2) is not None:
            href = m.group(3)
            assert not re.match(r"(?:javascript|data|file):", href, re.I)
            extra = ' target="_blank" rel="noopener noreferrer"' if href.startswith("https://") else ""
            if href == "methodology.md": extra += ' download="서울대_하교길_가정_자료_출처_2026-11-08.md"'
            result.append('<a href="' + escape(href, quote=True) + '"' + extra + ">" + escape(m.group(2)) + "</a>")
        else:
            result.append("<strong>" + escape(m.group(4)) + "</strong>")
        previous = m.end()
    result.append(escape(text[previous:]))
    return "".join(result)


def render(markdown):
    lines = markdown.splitlines(); body = []; toc = []; i = 0; sub = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        if line.startswith("# "): i += 1; continue
        if line.startswith("## "):
            label = line[3:]; identity = "section-" + str(len(toc) + 1)
            toc.append((identity, label)); body.append(f'<h2 id="{identity}">{inline(label)}</h2>'); i += 1; continue
        if line.startswith("### "):
            label = line[4:]; source = re.match(r"S(\d+) ·", label)
            sub += 1; identity = "source-s" + source.group(1) if source else "subsection-" + str(sub)
            body.append(f'<h3 id="{identity}">{inline(label)}</h3>'); i += 1; continue
        if line.startswith("```"):
            code = []; i += 1
            while i < len(lines) and not lines[i].startswith("```"): code.append(lines[i]); i += 1
            assert i < len(lines), "Unclosed code block"
            body.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>"); i += 1; continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")]); i += 1
            assert len(rows) >= 2 and all(re.fullmatch(r":?-+:?", cell) for cell in rows[1])
            assert all(len(row) == len(rows[0]) for row in rows)
            body.append('<div class="table-wrap" role="region" aria-label="' + escape(rows[0][0], quote=True) + ' 표" tabindex="0"><table><thead><tr>' + "".join("<th scope=\"col\">" + inline(cell) + "</th>" for cell in rows[0]) + "</tr></thead><tbody>")
            for row in rows[2:]: body.append("<tr>" + "".join("<td>" + inline(cell) + "</td>" for cell in row) + "</tr>")
            body.append("</tbody></table></div>"); continue
        if line.startswith("- "):
            body.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                body.append("<li>" + inline(lines[i][2:]) + "</li>"); i += 1
            body.append("</ul>"); continue
        paragraph = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "- ", "```")):
            paragraph.append(lines[i]); i += 1
        assert paragraph, line
        body.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    assert len(toc) == 12
    return "\n".join(body), toc


class Audit(HTMLParser):
    def __init__(self): super().__init__(); self.ids = []; self.internal = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs: self.ids.append(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"): self.internal.append(attrs["href"][1:])


def build():
    result = evidence()
    markdown = (HERE / "methodology_source.md").read_text(encoding="utf-8")
    markdown = markdown.replace("{{course_table}}", table(["단계", "규모", "단위"], [
        ["2026-11-06 강좌검색 보존본", "8,654", "강좌 행"],
        ["지도 입력", "6,201 / 88", "평일 종료 사건 / 강의동"],
        ["종료 사건별 수강신청인원 합계", "156,338", "중복 가능한 수강인원 합"],
        ["직후 이동 50% 적용", "78,169.0", "가중 이동 사건"],
    ]))
    markdown = markdown.replace("{{results_table}}", table(["고정 집단", "배차", "누적 대기 전 → 후 (분)", "총시간 전 → 후 (분)"], [
        [s["label"], "피크 최소 간격" if s["scenario"] == "peak" else "기준",
         f'{s["wait_before"]:.2f} → {s["wait_after"]:.2f}', f'{s["total_before"]:.2f} → {s["total_after"]:.2f}'] for s in result["summaries"]
    ]))
    first = result["summaries"][0]
    markdown = markdown.replace("{{completeness}}", f'서울대입구행 전체 집단은 가중치 {first["weight"]:,.4f}이며, 양쪽 공통 완주 비중은 {first["common_complete_share_pct"]:.4f}%입니다. 변경 전 미도착 가중치 {first["unserved_before"]:.4f}, 변경 후 {first["unserved_after"]:.4f}를 별도로 남겼습니다. 미도착을 삭제하거나 0분으로 바꾸어 총시간 개선을 부풀리지 않았습니다.')
    markdown = markdown.replace("{{provenance_table}}", table(["확인 항목", "보존 근거"], [
        ["문서의 선택 입력·코드 파일", f'{len(result["files"])}개 파일의 SHA-256을 근거 JSON에 기록'],
        ["종료 사건·수강인원·강의동", "보존 입력에서 6,201 / 156,338 / 88 재계수"],
        ["전후 결과", "요일별 원수치에서 집단 가중치·공통 완주 분모로 재집계"],
        ["기존 시뮬레이션의 정원·승하차·대기열", "독립 검산 PASS 기록을 근거 파일로 연결"],
        ["공개 배포", "v3·v4 JSON 24개의 원본 해시 일치 및 PC·모바일 기능 검사"],
        ["이번 문서 작성", "시뮬레이션 재실행 없음. 설명서·연결 UI만 갱신"],
    ]))
    assert "{{" not in markdown and "C:/Users" not in markdown and "C:\\Users" not in markdown
    body, toc = render(markdown)
    nav = "".join(f'<a href="#{identity}">{escape(label)}</a>' for identity, label in toc)
    page = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#173c39"><meta name="description" content="서울대 하교길 시뮬레이션과 경로 추천의 가정, 실제 사용 자료, 출처, 전후 비교 분모와 한계를 정리한 설명서"><title>가정·자료·출처 설명서 · 하교길 실험실</title><link rel="icon" href="data:,"><link rel="stylesheet" href="methodology.css"><link rel="stylesheet" href="campus-theme.css"><script src="campus-theme.js"></script></head>
<body class="campus-methodology"><a class="skip-link" href="#document">본문으로 이동</a><header class="doc-header"><a class="doc-brand" href="./">하교길 실험실</a><nav aria-label="사이트 이동"><a href="./">시뮬레이션 지도</a><a href="https://snu-route-lab.vercel.app/" target="_blank" rel="noopener noreferrer">경로 추천 ↗</a><button type="button" class="theme-toggle" role="switch" aria-checked="false" aria-label="다크 모드" data-theme-toggle title="다크 모드로 전환"><span class="theme-label" aria-hidden="true">다크 모드</span><span class="theme-track" aria-hidden="true"><span class="theme-knob"></span></span></button></nav></header>
<div class="doc-layout"><aside class="toc"><p>설명서 목차</p><nav aria-label="설명서 목차">{nav}</nav><a class="download" href="methodology.md" download="서울대_하교길_가정_자료_출처_2026-11-08.md">Markdown 내려받기 ↓</a><a class="evidence" href="methodology-evidence.json">근거·해시 JSON ↗</a></aside>
<main id="document"><div class="hero"><span class="eyebrow">METHODS & SOURCES · 2026.11.08</span><h1>가정·자료·출처<br>하교길을 계산한 방법</h1><p>무엇을 확인했고, 무엇을 가정했는지.<br>지도와 경로 추천을 읽기 위한 통합 설명서입니다.</p><div class="badges"><span>수업 종료 사건 6,201개</span><span>가중 통행 시뮬레이션</span><span>실측 대기열과 구분</span></div></div>
<article>{body}</article><footer><a href="#document">맨 위로 ↑</a><p>서울대 하교길 프로젝트 · 문서 기준 2026-11-08 · 지도 © OpenStreetMap 기여자</p></footer></main></div></body></html>'''
    audit = Audit(); audit.feed(page)
    assert len(audit.ids) == len(set(audit.ids))
    assert set(audit.internal) <= set(audit.ids)
    result["source_document_sha256"] = hashlib.sha256((HERE / "methodology_source.md").read_bytes()).hexdigest()
    result["document_checks"] = {"status": "PASS", "sections": len(toc), "internal_links_valid": True, "duplicate_ids": False, "unresolved_placeholders": False}
    (PUBLIC / "methodology.md").write_text(markdown + "\n", encoding="utf-8")
    (PUBLIC / "methodology.html").write_text(page, encoding="utf-8")
    (PUBLIC / "methodology-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "sections": len(toc), "source_files": len(result["files"]), "result_rows": len(result["summaries"]), "html_bytes": len(page.encode("utf-8"))}))


if __name__ == "__main__": build()

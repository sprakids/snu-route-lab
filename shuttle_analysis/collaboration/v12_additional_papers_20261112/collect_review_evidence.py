"""Record read-only review provenance; never import or run the simulation."""
from pathlib import Path
import datetime
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
MODEL = ROOT.parent.parent / "261112132736"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(name, value):
    path = ROOT / name
    assert not path.exists(), f"Preserve existing evidence: {path}"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


papers = [
    {
        "id": "Liu_Miller_2020",
        "role": "core_information_age_and_arrival_risk",
        "doi": "10.1016/j.tra.2020.09.014",
        "url": "https://luyuliu.github.io/files/pdfs/Smart_App.pdf",
        "file": "Liu_Miller_2020.private.pdf",
        "evidence_type": "observed_vehicle_records_with_hypothetical_user_strategies_not_observed_strategy_shares",
        "reviewed_pdf_pages": list(range(5, 14)) + [21, 22],
        "reviewed_sections": ["3.1-3.3", "4.1", "5"],
    },
    {
        "id": "Arriagada_Prato_Munizaga_2025",
        "role": "core_day_to_day_route_inertia",
        "doi": "10.1016/j.tra.2025.104467",
        "url": "https://eprints.whiterose.ac.uk/id/eprint/235367/2/1-s2.0-S0965856425000953-main.pdf",
        "file": "Arriagada_Prato_Munizaga_2025.private.pdf",
        "evidence_type": "AFC_AVL_revealed_preference_with_inferred_trip_endpoints_and_wait_proxy",
        "reviewed_pdf_pages": [3, 6, 7, 8, 9, 13, 14],
        "reviewed_sections": ["2.1", "3", "4.1-4.2", "5-6"],
    },
    {
        "id": "Berggren_etal_2022",
        "role": "core_access_egress_walk_and_wait_choice",
        "doi": "10.1080/23249935.2021.1973146",
        "url": "https://backend.orbit.dtu.dk/ws/portalfiles/portal/302513153/Public_transport_path_choice_estimation_based_on_trip_data_from_dedicated_smartphone_app_survey.pdf",
        "file": "Berggren_etal_2022.private.pdf",
        "evidence_type": "smartphone_revealed_paths_matched_to_generated_choice_sets_with_attrition_and_wait_proxies",
        "reviewed_pdf_pages": [8, 9, 16, 17, 20, 23, 30, 31, 32],
        "reviewed_sections": ["3", "4.2-4.3.1", "5.2 introduction", "6-7"],
        "additional_publisher_html_sections": ["3.1", "5.1", "5.2"],
        "table_coefficients_reestimated": False,
    },
    {
        "id": "Drabicki_etal_2023",
        "role": "followup_board_wait_crowding_consistency",
        "doi": "10.1016/j.rtbm.2023.100963",
        "url": "https://pure.tudelft.nl/ws/portalfiles/portal/151662216/1_s2.0_S2210539523000196_main_1.pdf",
        "file": "stay_board_2023.private.pdf",
        "evidence_type": "stated_preference_377_respondents_and_illustrative_flow_example_not_observed_boarding_refusal_rates",
        "reviewed_pdf_pages": [4, 5, 6, 10],
        "reviewed_sections": ["2.1-2.2", "3.1", "3.4"],
    },
]

for paper in papers:
    pdf = ROOT / paper["file"]
    txt = pdf.with_suffix(".txt")
    assert pdf.read_bytes().startswith(b"%PDF")
    assert txt.exists()
    pages = re.findall(r"=== PDF PAGE (\d+) ===", txt.read_text(encoding="utf-8"))
    assert set(paper["reviewed_pdf_pages"]).issubset({int(n) for n in pages})
    paper.update(bytes=pdf.stat().st_size, sha256=digest(pdf), extracted_text_sha256=digest(txt), pdf_page_count=len(pages))

expected = {
    "policy.py": "d68eba13865d01cd6c90ca0250159c0ed35ffb72a16318638683017af9487334",
    "config.json": "d6f0f35bc9bad4ea5d6b6b91457e8e7913e0f89c559570f11c3533c5e5e106f1",
    "engine.py": "9d5f694762ea2c8b5cd3a424d9896c7e7428586580ceb4db042e17157833de0c",
    "experiment_lock.json": "82b61dd22c0a2fac2bb7d6c35b622cf1dd5481971f357277011149e31792512b",
    "RESULTS_FINAL.md": "4c9e2b316f7c683df526e8f5242f42894ec825b9c4af5fb6c4d5bb8dbd4c50af",
}
actual = {name: digest(MODEL / name) for name in expected}
assert actual == expected, "Review scope source changed; inspect before claiming unchanged"

links = []
for name in ["REVIEW_KO.md", "CROWDING_READ_ONLY.md", "README.md"]:
    path = ROOT / name
    assert path.exists()
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        if "://" not in target and not target.startswith("#"):
            resolved = (ROOT / target).resolve()
            pending_output = resolved.parent == ROOT and resolved.name in {"source_manifest.json", "scope_verification.json"}
            assert resolved.exists() or pending_output, str(resolved)
            links.append({"document": name, "target": target})

now = datetime.datetime.now().astimezone().isoformat()
save_new("source_manifest.json", {
    "created_at": now,
    "papers": papers,
    "core_paper_count": 3,
    "followup_paper_count": 1,
    "private_copies_for_research_not_published": True,
    "screened_but_not_used_as_fulltext_basis": [
        {"doi": "10.1016/j.tra.2013.06.005", "reason": "Public Sydney manuscript download returned HTTP403; abstract-level screening only"},
        {"doi": "10.1016/j.tbs.2021.01.001", "reason": "Napier fulltext landing returned HTTP403; excluded from core fulltext review"},
        {"doi": "10.1007/s13676-014-0070-4", "reason": "Metadata and abstract screened, full manuscript not acquired or used for detailed recommendations"},
    ],
    "download_access_notes": [
        "Berggren public orbit.dtu.dk/files and publisher download returned403; official backend.orbit.dtu.dk public file succeeded",
        "Some browser fetches timed out; acquired PDFs were parsed locally instead",
    ],
})
save_new("scope_verification.json", {
    "checked_at": now,
    "candidate": "261112132736",
    "candidate_hashes_unchanged": actual == expected,
    "protected_hashes": actual,
    "new_date_raw_outcomes_read": False,
    "simulator_imported": False,
    "simulations_started": False,
    "model_code_or_inputs_modified": False,
    "production_writes": False,
    "changes_confined_to_review_directory": True,
    "calibration_or_independent_accuracy_claimed": False,
    "checked_local_links": links,
    "document_sha256": {name: digest(ROOT / name) for name in ["REVIEW_KO.md", "CROWDING_READ_ONLY.md", "README.md"]},
})
assert all((ROOT / item["target"]).resolve().exists() for item in links)
print(json.dumps({"status": "PASS_READ_ONLY_REVIEW_PROVENANCE", "papers": len(papers), "protected_files": len(actual), "checked_local_links": len(links)}, ensure_ascii=False))

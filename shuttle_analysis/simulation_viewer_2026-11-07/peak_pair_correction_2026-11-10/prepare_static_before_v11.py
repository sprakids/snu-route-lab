"""Prepare the city-capacity v5 replay for the existing static deployment.

Only the replay UI, Leaflet, and the verified v3/v4/v5 compressed datasets are
published. Model inputs, local servers, launchers, and credentials stay local.
"""
from pathlib import Path
import gzip
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public"
STAGE = Path(__file__).resolve().parent / "static_site"
PUBLIC = STAGE / "public"
ASSETS = (
    "index.html", "adaptive.html", "viewer-v2.css", "viewer-v4.js",
    "graphs-v4.js", "bus-motion.js",
    "methodology.html", "methodology.md", "methodology.css", "methodology-evidence.json",
    "campus-theme.css", "campus-theme.js",
    "city.html", "viewer-v5.js", "graphs-v5.js", "viewer-v5.css", "snapshot-query.js", "initial-clock.js", "json-loader.js",
    "empirical-methodology.html", "empirical-methodology.md", "empirical-speed-reference.png",
    "gate-access-methodology.html", "gate-access-methodology.md", "gate-access-summary.json",
)
DATASETS = ("capacity_v3", "capacity_v4", "capacity_v5", "capacity_v6", "capacity_v7")
DATA_FILES = ("common", "charts") + tuple(
    f"{scenario}-{day}"
    for scenario in ("regular", "peak")
    for day in ("mon", "tue", "wed", "thu", "fri")
)


def prepare():
    # v9 exceeds the single-project upload limit when added to the preserved
    # archive. Use the split-data publisher instead of silently dropping v9.
    source_config = json.loads((Path(__file__).parent / "queue_source.json").read_text(encoding="utf-8"))
    if source_config.get("simulation_version") == "capacity_v9":
        import sys
        sys.path.insert(0, str(ROOT))
        from build_walk_choice_deployment import ui_stage
        assert (Path(__file__).parent / "walk_choice_data_host.json").exists(), "Deploy the verified data stage before preparing the v9 UI"
        return ui_stage()
    from publish_queue_model import publish
    queue_release=publish()
    files = [SOURCE / name for name in ASSETS]
    for model_file in sorted((SOURCE/'routing-model').rglob('*.json')):
        raw=model_file.read_bytes()
        assert not re.search(rb"C:[\\/]|(?:api|service)[_-]?key=|BEGIN [A-Z ]*PRIVATE KEY",raw,re.I),str(model_file)
        json.loads(raw)
        files.append(model_file)
    files.extend(sorted((SOURCE / "vendor").rglob("*")))
    files.extend(sorted((SOURCE / "assets/fonts").rglob("*")))
    files = [p for p in files if p.is_file()]
    datasets = []
    groups=[(dataset,DATA_FILES) for dataset in DATASETS]+[("half_hour_v1",DATASETS),("chart_reference_v1",("legacy",))]
    for dataset,names in groups:
        for name in names:
            compressed = SOURCE / "data" / dataset / f"{name}.json.gz"
            original = compressed.with_suffix("")
            raw = original.read_bytes()
            assert gzip.decompress(compressed.read_bytes()) == raw, str(compressed)
            assert not re.search(rb"C:[\\/]|(?:api|service)[_-]?key=|BEGIN [A-Z ]*PRIVATE KEY", raw, re.I), str(original)
            json.loads(raw)
            files.append(compressed)
            datasets.append({
                "path": compressed.relative_to(SOURCE).as_posix(),
                "uncompressed_bytes": len(raw),
                "compressed_bytes": compressed.stat().st_size,
                "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            })
    expected = {p.relative_to(SOURCE).as_posix() for p in files}
    if PUBLIC.exists():
        extra = {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob("*") if p.is_file()} - expected
        assert not extra, f"Unexpected staged files: {sorted(extra)}"
    manifest = []
    for source in files:
        relative = source.relative_to(SOURCE)
        target = PUBLIC / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        manifest.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": digest})
    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": None,
        "installCommand": "",
        "buildCommand": "",
        "outputDirectory": "public",
        "headers": [
            {"source": "/(.*)", "headers": [
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"},
            ]},
            {"source": "/data/:dataset/:file.json", "headers": [
                {"key": "Content-Type", "value": "application/json; charset=utf-8"},
                {"key": "Content-Encoding", "value": "gzip"},
                {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"},
            ]},
        ],
        "rewrites": [{
            "source": "/data/:dataset/:file.json",
            "destination": "/data/:dataset/:file.json.gz",
        }],
    }
    (STAGE / "vercel.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (STAGE / ".vercelignore").write_text(".vercel\n.env*\n.git\n", encoding="utf-8")
    result = {
        "status": "PASS", "project_name": "snu-shuttle-simulation",
        "dataset_count": len(datasets), "public_file_count": len(manifest),
        "upload_bytes": sum(row["bytes"] for row in manifest),
        "dataset_uncompressed_bytes": sum(row["uncompressed_bytes"] for row in datasets),
        "dataset_compressed_bytes": sum(row["compressed_bytes"] for row in datasets),
        "simulation_version": "capacity_v7", "simulation_recomputed": True,
        "queue_release":queue_release,
        "previous_v3_v4_preserved": True,
        "files": manifest, "datasets": datasets,
    }
    (Path(__file__).resolve().parent / "source_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key not in ("files", "datasets")}))


if __name__ == "__main__":
    prepare()

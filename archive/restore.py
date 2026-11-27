"""Restore original project paths from GitHub Release assets using only Python 3.11+."""
from argparse import ArgumentParser
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/"archive"

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("parts_folder",type=Path,help="Folder containing downloaded work-*.zip files")
    parser.add_argument("--prefix",action="append",default=[],help="Only restore paths starting with this project-relative prefix")
    parser.add_argument("--inputs",choices=[s+"-"+d for s in ("peak","regular") for d in ("mon","tue","wed","thu","fri")],help="Restore only files read to calculate this V13 weekday and timetable")
    parser.add_argument("--list",action="store_true",help="List required archive parts without writing files")
    args=parser.parse_args()
    needed=None
    if args.inputs:
        log=ROOT/"shuttle_analysis/261127183058/runs/V13"/args.inputs/"input_files.json"
        needed=set(json.loads(log.read_bytes()))
    meta={p["name"]:p for p in json.loads((INDEX/"parts.json").read_bytes())}
    files=defaultdict(list)
    with gzip.open(INDEX/"files.csv.gz","rt",encoding="utf8",newline="") as f:
        for row in csv.DictReader(f):
            if needed is not None and row["path"] not in needed:continue
            if row["storage"]=="git" or (args.prefix and not any(row["path"].startswith(p) for p in args.prefix)):continue
            dest=(ROOT/PurePosixPath(row["path"])).resolve()
            if not dest.is_relative_to(ROOT) or not row["storage"] in meta:raise ValueError("Unexpected archive path")
            files[row["storage"]].append((dest,row))
    if args.list:
        for n in sorted(files):print(n,meta[n]["bytes"],len(files[n]))
        return
    for n,entries in sorted(files.items()):
        part=args.parts_folder/n
        if not part.is_file():raise SystemExit(f"Please download {n} into {args.parts_folder}")
        if part.stat().st_size!=meta[n]["bytes"] or digest(part)!=meta[n]["sha256"]:raise ValueError(f"Archive integrity error: {n}")
        with ZipFile(part) as z:
            for dest,row in entries:
                if dest.exists():
                    if digest(dest)==row["sha256"]:continue
                    raise FileExistsError(f"Different file already exists: {dest}")
                dest.parent.mkdir(parents=True,exist_ok=True)
                fd,name=tempfile.mkstemp(dir=dest.parent);os.close(fd);pending=Path(name)
                try:
                    with z.open(row["sha256"]) as src,pending.open("wb") as out:shutil.copyfileobj(src,out,1024*1024)
                    if pending.stat().st_size!=int(row["bytes"]) or digest(pending)!=row["sha256"]:raise ValueError(row["path"])
                    pending.replace(dest)
                finally:
                    pending.unlink(missing_ok=True)
        print(f"Ready: {n}",flush=True)

if __name__=="__main__":main()

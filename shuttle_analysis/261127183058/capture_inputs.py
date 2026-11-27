"""Record which in-project files the released engine actually reads for one replay."""
from pathlib import Path
import json
import os
import runpy
import sys

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
sources=set()
prefix=os.path.normcase(str(PROJECT))+os.sep
def collect(event,args):
    if event!="open" or not isinstance(args[0],(str,bytes)):return
    mode=args[1]
    if isinstance(mode,str) and any(c in mode for c in "wax+"):return
    filename=os.path.abspath(os.fsdecode(args[0]))
    if os.path.normcase(filename).startswith(prefix) and "__pycache__" not in filename:
        rel=Path(filename).relative_to(PROJECT)
        if tuple(rel.parts[:3])!=("shuttle_analysis",HERE.name,"runs"):
            sources.add(rel.as_posix())

if __name__=="__main__":
    day,service,mode=sys.argv[1:]
    sys.addaudithook(collect)
    runpy.run_path(str(HERE/"v13.py"),run_name="__main__")
    files=sorted(s for s in sources if (PROJECT/s).is_file())
    (HERE/"runs"/mode/f"{service}-{day}"/"input_files.json").write_text(json.dumps(files,ensure_ascii=False,indent=1),encoding="utf8")

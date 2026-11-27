from pathlib import Path
import shutil
TASK=Path(__file__).resolve().parent
ORIGINAL=Path('C:/Users/김예준/.codex/visualizations/2026/11/03/01a1a1e8-54cf-7243-9ad9-0a31e6f31a06/mobile-lab-261110165808')
s=(ORIGINAL/'qa.cjs').read_text(encoding='utf8')
a="const BASE='http://127.0.0.1:8864/',OUT=__dirname;";assert a in s
s=s.replace(a,"const BASE=process.argv[2]||'http://127.0.0.1:8799/',OUT=process.argv[3]||__dirname;\nconst baselineReport=require('./peer-qa-baseline.json');",1)
s=s.replace("assert.match(page.url(),/127\\.0\\.0\\.1:8864/);","assert(page.url().startsWith(BASE));",1)
s=s.replace("[['small',{width:360,height:740}]","[['tiny',{width:320,height:568}],['small',{width:360,height:740}]",1)
a="await open(page,true);const before=await metrics(page);await screen(page,name+'-before');";assert a in s
s=s.replace(a,"const before=baselineReport.results.find(r=>r.name===name).before;",1)
s=s.replace("actual_local_v11_data:true","actual_public_or_local_v11_data:true",1)
s=s.replace("production_modified:false","model_unchanged:true,anonymous_public_test:BASE.startsWith('https:')",1)
(TASK/'root-mobile-qa.cjs').write_text(s,encoding='utf8');shutil.copy2(ORIGINAL/'qa.json',TASK/'peer-qa-baseline.json')
out=TASK/'root-public-qa';out.mkdir(exist_ok=False)
print(out)

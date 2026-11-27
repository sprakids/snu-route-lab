"""Make an isolated successor; preserve every prior receipt and physical input."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'261116010854'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S')
    work=ROOT.parent/stamp;work.mkdir()
    old=read(PARENT/'repair_manifest.json')
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for n in names:shutil.copy2(PARENT/n,work/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(PARENT/n)==h,n
        p=work/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/n,p)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-same-stop-reconsideration',
        same_stop_flexible_pool_choice=True,
        same_stop_interpretation='After the existing personal/denial gate releases, compare an expanded legal same-platform pool with stay and walking choices. No forced boarding-policy expansion, reset of wait/denial/FIFO, physical return, route-change count or new service.',
        diagnostic_uids=[1519408,132432,438832,2271312,3381728,3900544,3695872,1795089,4625936,2644624])
    save(work/'config.json',cfg)
    days=[('月','월','mon'),('火','화','tue'),('水','수','wed'),('木','목','thu'),('金','금','fri')]
    cases=[{'case':f'poolfix-combined-{scenario}-{eng}','mode':'combined','day':day,'scenario':scenario,'seed':0,'operations':'v12_empirical'} for scenario in ['regular','peak'] for _,day,eng in days]
    cases.append({'case':'ablation-no-same-stop-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'v12_empirical','config_overrides':{'same_stop_flexible_pool_choice':False}})
    lock={'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'implementation_parent':str(PARENT),'comparison_parent':PARENT.name,
          'pilot_cases':cases,'selection_rule':'First main Monday/Tuesday regular and Monday disabled-mechanism diagnostic, once each. Only if physical/user-rule audits pass, no unserved, combined reused observation error and over20 weight do not worsen and at least one improves, extend remaining8main weekday/scenario cases. Retain all failed and worsening results. No numeric wait/queue caps, demand additions, capacity/clock/patience/taste fitting or new-date outcome reads.',
          'new_day_outcomes_opened':False,'production_replacement_allowed':False,
          'retained_user_behavior':read(PARENT/'experiment_lock.json')['retained_user_behavior']}
    save(work/'experiment_lock.json',lock)
    protect=old['protected'].copy()
    for p in PARENT.iterdir():
        if p.is_file():protect[str(p)]=sha(p)
    save(work/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protect,'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(work/'config.json'),'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(work),'comparison_parent':PARENT.name})
    print(work,flush=True)
if __name__=='__main__':main()

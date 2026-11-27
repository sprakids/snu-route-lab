"""Correct only the initial expected-clock anchor; preserve all consumed cases."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;P=A/'261116160639';OUT=A/'v12_nominal_anchor_20261116'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    OUT.mkdir();stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=A/stamp;w.mkdir()
    old=read(P/'repair_manifest.json')
    for p in P.glob('*.py'):shutil.copy2(p,w/p.name)
    for n in ['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']:shutil.copy2(P/n,w/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(P/n)==h
        dst=w/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,dst)
    for p in P.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    cfg=read(P/'config.json');cfg.update(release_id=stamp,version_family='V12-nominal-transfer-consistent-initial-clock',
        consistent_initial_headway_anchor=True,
        initial_anchor_interpretation='Only initial choice passes now+frequency-adjusted first-boarding score to later nominal-hour lookup. Removes the discarded first exact phase from downstream hour selection. Queue reviews retain their current known first-board clock. No coefficient or physical timing changes.')
    save(w/'config.json',cfg)
    p=w/'nominal_transfer.py';t=p.read_text(encoding='utf8')
    t=t.replace('def intervals(self,pred,stages):','def intervals(self,pred,stages,first_boarding_time=None):')
    needle='        chain=list(stages);old_removed=0.;nominal_added=0.;intervals=[];details=[]\n';assert t.count(needle)==1
    t=t.replace(needle,needle+"        initial_shift=0. if first_boarding_time is None else float(first_boarding_time)-timeline[0]['time']\n        if not math.isfinite(initial_shift):raise ValueError('Initial expected boarding anchor must be finite')\n")
    t=t.replace("arrival=row['arrival']-old_removed+nominal_added","arrival=row['arrival']+initial_shift-old_removed+nominal_added")
    t=t.replace('def primary_extension(self,pred,stages,primary_node,physical_prefix):','def primary_extension(self,pred,stages,primary_node,physical_prefix,first_boarding_time=None):')
    needle='        intervals,details=self.intervals(pred,stages);target=indices[-1]';assert t.count(needle)==1
    t=t.replace(needle,'        intervals,details=self.intervals(pred,stages,first_boarding_time);target=indices[-1]')
    p.write_text(t,encoding='utf8')
    p=w/'behavioral_policy.py';t=p.read_text(encoding='utf8')
    needle="                    extension,nominal_details=nominal_transfers.primary_extension(pred,chain,source['primary_node'],extension)";assert t.count(needle)==1
    t=t.replace(needle,"                    anchor=at+score if config.get('consistent_initial_headway_anchor') else None\n                    extension,nominal_details=nominal_transfers.primary_extension(pred,chain,source['primary_node'],extension,anchor)")
    p.write_text(t,encoding='utf8')
    cases=[]
    for c in read(P/'experiment_lock.json')['pilot_cases']:
        if c['case'].startswith('ablation'):continue
        cases.append({**c,'case':c['case'].replace('headway-combined','anchor-combined')})
    cases.append({'case':'ablation-old-initial-anchor-tue','mode':'combined','day':'화','scenario':'regular','seed':0,'operations':'v12_empirical',
        'config_overrides':{'consistent_initial_headway_anchor':False}})
    lock=read(P/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(P),comparison_parent='261116153200',
        diagnostic_parent=P.name,pilot_cases=cases,
        selection_rule='MainMon/Tue regular compared to G153200; anchorOFFTue must reproduce I160639. Physical/user/data invariants, no unserved, nonworsening all-recorded over20 sum/maxwait/each mean/reused field sum/gate error/afternoon lawmax, strict over20 and SNU priorbus law arrivals decrease. Only then remaining8 once. No coefficient fit/new-date outcomes.')
    save(w/'experiment_lock.json',lock)
    protect=old['protected'].copy()
    # Parent analysis is still finishing: protect immutable runtime and input
    # artifacts, never bind an actively appended analysis log as an old source.
    for p in [*P.glob('*.py'),*P.glob('physical_paths_*.json.gz'),*[P/n for n in ['config.json','experiment_lock.json','input_manifest.json','repair_manifest.json','future_evaluation_plan.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']]]:
        protect[str(p)]=sha(p)
    save(w/'repair_manifest.json',{'parent':str(P),'comparison_parent':'261116153200','diagnostic_parent':P.name,'release_id':stamp,'protected':protect,
        'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(OUT/'candidate.json',{'release_id':stamp,'path':str(w),'parent':P.name,'comparison_parent':'261116153200'})
    for p in ROOT.glob('*.py'):
        if p.name in ['build_anchor_candidate.py','analyze_blocked_pilot.py','check_units.py']:continue
        shutil.copy2(p,OUT/p.name)
    for n in ['run_cases.py','advance_workflow.py','check_units.py']:shutil.copy2(ROOT/n,OUT/n)
    p=OUT/'check_pilot.py';t=p.read_text(encoding='utf8')
    needle="    par=next(r for r in old if r['case']['day']=='화')";assert t.count(needle)==1
    t=t.replace(needle,"    diag_parent=read(w.parent/'261116160639'/'pilot-validation.json')['results']\n    par=next(r for r in diag_parent if r['case']['day']=='화' and not r['case']['case'].startswith('ablation'))")
    p.write_text(t,encoding='utf8')
    print(w,flush=True)
if __name__=='__main__':main()

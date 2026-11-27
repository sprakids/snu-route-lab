"""Exclude a confirmed opposite-direction terminal ride without changing schedules."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261115154738'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir();m=read(PARENT/'repair_manifest.json')
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    for name,digest in m['frozen_payloads'].items():
        assert sha(PARENT/name)==digest
        target=w/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/name,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    c=read(PARENT/'config.json');c.update(release_id=stamp,version_family='V12-student-terminal-direction',terminal_direction_requirements={'daehak':{'100100253':['대학동고시촌입구']}})
    save(w/'config.json',c);lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT),status='REGISTERED_BEFORE_EXECUTION');lock.pop('reused_completed_runs',None)
    lock['pilot_cases']=[{**r,'case':r['case'].replace('student-','direction-')} for r in lock['pilot_cases']]
    lock['refinement_reason']='Confirmed Tuesday135.6min trip boarded5516 at law stop toward Noryangjin and rode82.29min to Daehak. Frozen official stop direction distinguishes branches. Require Daehak-bound branch for a terminal5516 ride to Daehak; preserve valid intermediate transfers and other destinations/routes.'
    lock['selection_rule']='No numerical fitting or demand/supply edits. New runtime requires10fresh cases once each; no reuse of changed-code outcomes. Keep20min,40-person reference, whole-journey and reused-field misfits visible; no active publication.'
    save(w/'experiment_lock.json',lock)
    protected={**m['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','experiment_lock.json','future_evaluation_plan.json','grid-validation.json','tuesday-longest-journey-trace.json']}}
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':m['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    p=w/'behavioral_policy.py';s=p.read_text(encoding='utf8')
    needle='def boarding_score(pred,access):return access+pred.first_wait'
    add='''def terminal_direction_allowed(dest,service,config,routes):
    allowed=config.get('terminal_direction_requirements',{}).get(dest,{}).get(service['rid'])
    if allowed is None:return True
    stops=routes.get(service['rid'],{}).get('stops',[])
    board=service['board']
    return 0<=board<len(stops) and stops[board].get('direction') in allowed

'''
    assert needle in s;s=s.replace(needle,add+needle)
    needle="                if not future and not terminal_allowed(state['dest'],paths[source['next_walk'][0]]['meters'],config):continue"
    assert needle in s;s=s.replace(needle,needle+"\n                if not future and not terminal_direction_allowed(state['dest'],source,config,bundle['prepared']['routes']):continue")
    p.write_text(s,encoding='utf8')
    p=w/'test_student_strategy.py';s=p.read_text(encoding='utf8');needle="    def test_patience_is_fixed_per_person_with_heterogeneity(self):"
    tests='''    def test_opposite_terminal_direction_is_removed_from_pool(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'away'}]
        bad={**leg('A'),'test_node':1};good={**leg('B'),'test_node':2};result=p.student_filter_stages(s,[{**bad,'pool':[bad,good]}],False)
        self.assertEqual([x['rid'] for x in result[0]['pool']],['B'])
    def test_correct_terminal_direction_remains_available(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'home'}]
        self.assertIsNotNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1}],False))
    def test_opposite_branch_can_still_make_a_valid_intermediate_transfer(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'away'}]
        chain=[{**leg('A'),'test_node':1},{**leg('B'),'test_node':2}]
        self.assertIsNotNone(p.student_filter_stages(s,chain,False))
    def test_unknown_required_terminal_direction_is_not_assumed_correct(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{}]
        self.assertIsNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1}],False))
'''
    assert needle in s;s=s.replace(needle,tests+needle);p.write_text(s,encoding='utf8')
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'implementation_parent':str(PARENT),'comparison_parent':'261112220847'})
    print(w,flush=True)
if __name__=='__main__':main()

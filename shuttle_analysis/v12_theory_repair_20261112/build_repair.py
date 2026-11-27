"""Build one immutable private candidate from the completed V12; no publisher."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
ANALYSIS=ROOT.parent
PARENT=ANALYSIS/'261112111627'
KST=timezone(timedelta(hours=9))
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def replace(path,old,new):
    text=path.read_text(encoding='utf8');assert text.count(old)==1,(path,old[:80],text.count(old))
    path.write_text(text.replace(old,new),encoding='utf8')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--joint',action='store_true');parser.add_argument('--iid',action='store_true');parser.add_argument('--initial-prior',action='store_true');args=parser.parse_args()
    stamp=datetime.now(KST).strftime('%y%m%d%H%M%S');work=ANALYSIS/stamp;work.mkdir()
    names=['artifacts.py','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py',
      'metrics.py','engine.py','operations.py','empirical_v12.py','time_profiles.py','run_case.py','fixtures.py',
      'test_prototype.py','test_prediction_integration.py','test_empirical_v12.py','dwell.py','analyze_followup.py',
      'validation_metrics.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','v12_supply.py']
    for name in names:shutil.copy2(PARENT/name,work/name)
    manifest=read(PARENT/'input_manifest.json');frozen=list(manifest['frozen'])
    for file in ('capacity44_amendment.json','pair_amendment.json'):frozen+=read(PARENT/file).get('additional_frozen',[])
    for row in {x['path']:x for x in frozen}.values():
        source=PARENT/row['path'];target=work/row['path'];assert sha(source)==row['sha256']
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-repair',
      persistent_strategy_utility=True,waiting_burden_scope='whole_journey',
      wait_discomfort_interpretation='Prospective increment G(A+W)-G(A) of cumulative journey waiting. Completed wait A affects marginal discomfort, never physical ETA. Same polynomial scales as V12; uncalibrated alternative hypothesis. No reset by walking to another queue.',
      random_utility_interpretation='One trip-strategy residual per agent, reused at every reconsideration. Full temporal persistence is an unestimated sensitivity boundary, not an empirical estimate.')
    if args.joint:cfg['joint_board_wait_walk_choice']=True
    if args.iid:
        cfg['persistent_strategy_utility']=False
        cfg['random_utility_interpretation']='Retain V12 fixed individual coefficients plus event-specific iid errors. rho=1 sensitivity was inferior in Tuesday pilot; no empirical serial correlation estimate.'
        cfg['skip_duplicate_service_review_after_joint_wait']=True
    if args.initial_prior:
        cfg['initial_assignment_policy']='preserve_source_mixture'
        cfg['initial_assignment_interpretation']='Preserve the inherited scenario mode/first-stop mixture. No uncalibrated re-optimization of every departure. Dynamic queue/boarding/walking choices remain enabled; source mixture is not an observed modal split.'
    save(work/'config.json',cfg)
    replace(work/'preferences.py',"noise=-math.log(-math.log(max(1e-15,uniform(config['seed'],identity,event_key,key))))", "noise_key=('trip-strategy',candidate.get('taste_key',key)) if config.get('persistent_strategy_utility') else (event_key,key)\n        noise=-math.log(-math.log(max(1e-15,uniform(config['seed'],identity,*noise_key))))")
    replace(work/'policy.py',"def signature(stages):",'''def cumulative_wait_discomfort(completed,future,config):
    """G(A+W)-G(A); invariant to splitting a fixed wait over stops."""
    a=max(0.,completed);w=max(0.,future)
    quad=config.get('predicted_queue_curvature_coefficient',0.)*(2*a*w+w*w)/config.get('predicted_queue_curvature_scale_seconds',600.)
    cube=(a*a*w+a*w*w+w**3/3)/config.get('waiting_discomfort_age_scale_seconds',600.)**2 if config.get('integrate_future_wait_discomfort') else 0.
    return quad+cube


def strategy_taste_key(stages,dest=None):
    # Access geometry and execution labels never manufacture new independent tastes.
    return (dest,signature(stages))


def signature(stages):''')
    replace(work/'policy.py',"            base+=state['traits'].wait*config.get('predicted_queue_curvature_coefficient',0.)*pred.wait_squared/(60*config.get('predicted_queue_curvature_scale_seconds',600.))",'''            if config.get('waiting_burden_scope')=='whole_journey':
                clock=pred.eta-(pred.walk+pred.wait+pred.ride+pred.prep)
                age=max(0.,clock-state['stop_entry'])
                completed=state.get('completed_wait_seconds',0.)+age
                future=pred.wait+pred.prep
                base+=state['traits'].wait*cumulative_wait_discomfort(completed,future,config)/60
                # Failure experience applies to further waiting in this queue.
                if not changing:base+=state['traits'].wait*config.get('waiting_discomfort_full_sensitivity',0.)*state['full_passes']*pred.first_wait/60
                return base
            base+=state['traits'].wait*config.get('predicted_queue_curvature_coefficient',0.)*pred.wait_squared/(60*config.get('predicted_queue_curvature_scale_seconds',600.))''')
    replace(work/'policy.py',"'prediction':current,'option':None}","'prediction':current,'option':None,'taste_key':strategy_taste_key(state['stages'][state['stage']:],state.get('dest'))}")
    replace(work/'policy.py',"'prediction':pred,'option':option,'prior':prior}","'prediction':pred,'option':option,'prior':prior,'taste_key':strategy_taste_key(chain,state.get('dest'))}")
    replace(work/'policy.py',"'option':option,'prediction':pred,'prior':prior}","'option':option,'prediction':pred,'prior':prior,'taste_key':strategy_taste_key(option['stages'],state.get('dest'))}")
    replace(work/'policy.py',"options=[{'key':'board','cost':self.generalized(ride,state)}, {'key':'wait','cost':self.generalized(future,state)}]", "options=[{'key':'board','cost':self.generalized(ride,state),'taste_key':strategy_taste_key(chain,state.get('dest'))}, {'key':'wait','cost':self.generalized(future,state),'taste_key':strategy_taste_key(state['stages'][state['stage']:],state.get('dest'))}]")
    replace(work/'engine.py',"    def record_wait(state,t,outcome):\n        stage=current_stage(state);node=state['node']", "    def record_wait(state,t,outcome):\n        state['completed_wait_seconds']=state.get('completed_wait_seconds',0.)+max(0.,t-state['arrival'])\n        stage=current_stage(state);node=state['node']")
    replace(work/'engine.py',"'review_ordinal':0,'hazard_clock':None}","'review_ordinal':0,'hazard_clock':None,'completed_wait_seconds':0.}")
    replace(work/'engine.py',"'fare_paid':s.get('fare_paid',0.),'parent_id'", "'completed_wait_seconds':s.get('completed_wait_seconds',0.),'fare_paid':s.get('fare_paid',0.),'parent_id'")
    replace(work/'run_case.py',"config['operations']=case.get('operations','baseline')", "config['operations']=case.get('operations','baseline');config.update(case.get('config_overrides',{}))")
    if args.initial_prior:
        replace(work/'run_case.py',"    if case['mode']=='fare_scenario':config['fare_in_choice']=True", "    if case['mode']=='fare_scenario':config['fare_in_choice']=True\n    if config.get('initial_assignment_policy')=='preserve_source_mixture':config['origin_choice']=False")
    # Original tests explicitly retain their legacy-cost scope; new tests check the new hypothesis.
    replace(work/'test_prototype.py',"def setUp(self):self.config=read(ROOT/'config.json')", "def setUp(self):self.config=read(ROOT/'config.json');self.config['waiting_burden_scope']='per_stop'")
    replace(work/'test_prediction_integration.py',"cfg=read(ROOT/'config.json');cfg['integrate_future_wait_discomfort']=flag", "cfg=read(ROOT/'config.json');cfg['integrate_future_wait_discomfort']=flag;cfg['waiting_burden_scope']='per_stop'")
    shutil.copy2(ROOT/'test_theory_repair.py',work/'test_theory_repair.py')
    if args.joint:
        from joint_choice_patch import apply
        apply(work)
        if args.iid:
            replace(work/'engine.py',"                    if policy.apply_boarding_walk(state,t):continue\n                    if state.get('service_review_pending_clock')!=t:","                    if policy.apply_boarding_walk(state,t):continue\n                    # This event already compared wait and every walking alternative.\n                    # Keep the continuous review clock, rather than draw again at t+1ms.\n                    if config.get('skip_duplicate_service_review_after_joint_wait'):\n                        reschedule(state,t);continue\n                    if state.get('service_review_pending_clock')!=t:")
        shutil.copy2(ROOT/'test_joint_choice.py',work/'test_joint_choice.py')
    cases=[]
    for source in read(PARENT/'experiment_lock.json')['pilot_cases']:
        case={**source,'case':source['case'].replace('v12_empirical','repair')};cases.append(case)
    ablations=[('persistent_only',{'waiting_burden_scope':'per_stop'}),('burden_only',{'persistent_strategy_utility':False})] if not args.iid else []
    for label,overrides in ablations:
        case=next(x for x in cases if x['day']=='화' and x['scenario']=='regular')
        cases.append({**case,'case':'ablation-'+label+'-regular-tue','config_overrides':overrides})
    if args.initial_prior:
        case=next(x for x in cases if x['day']=='월' and x['scenario']=='regular')
        cases.append({**case,'case':'ablation-free_origin-regular-mon','config_overrides':{'initial_assignment_policy':'free_choice'}})
    save(work/'experiment_lock.json',{'status':'FROZEN_BEFORE_EXECUTION','release_id':stamp,'version_family':'V12-repair',
      'pilot_cases':cases,'selection_rule':('Preserved initial-mixture weekday grid, plus Monday free-origin contrast; Tuesday free-origin control is reused from the preceding frozen candidate. No fitting to four known queue reports.' if args.initial_prior else 'Repair full grid plus prespecified mechanism comparisons. No fitting to four known queue reports.'),
      'gates':['same parent demand and fixed supply','capacity/FIFO/time conservation','every continuous wait <=20min; failures preserved',
               'report total/walk/cumulative-wait tails and repeated changes','report all four historical queues; not independent holdout'],
      'production_replacement_allowed':False,'new_observation_outcomes_read':False})
    protected={str(PARENT/name):sha(PARENT/name) for name in names+['config.json','review_final.json']}
    protected[str(ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json')]=sha(ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json')
    save(work/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,
      'frozen_payloads':{r['path']:r['sha256'] for r in frozen},'config_sha256':sha(work/'config.json'),
      'changes':([] if args.iid else ['Persistent strategy errors across events'])+['Whole-journey prospective waiting burden instead of queue-reset polynomial']+(['Joint board/wait/walk choice, including the last service'] if args.joint else [])+(['No duplicate 1ms reconsideration after an already joint wait decision'] if args.iid else [])+(['Preserve inherited initial scenario mixture; free-origin Monday comparison registered'] if args.initial_prior else []),
      'unfitted_assumptions':True,'no_capacity_increase_no_demand_deletion_no_forced_exit':True})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(work)})
    print(str(work),flush=True)
if __name__=='__main__':main()

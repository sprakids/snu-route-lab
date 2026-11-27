"""Create one isolated, timestamped follow-up; preserve the nine original pilots."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import copy,json,hashlib,shutil

OLD=Path(__file__).resolve().parent;SIM=OLD.parent/'simulation_viewer_2026-11-07'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    pointer=OLD/'followup_experiment.json';assert not pointer.exists(),'Inspect the existing follow-up; do not duplicate it'
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=OLD.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json']
    for name in names:shutil.copy2(OLD/name,work/name)
    shutil.copytree(OLD/'frozen',work/'frozen')
    for p in OLD.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    sources={'distribution_v8':SIM/'weekday_operations_2026-11-10/city_operations.json',
             'gate_reference':SIM/'gate_clock_repair_2026-11-10/city_operations.json'}
    source_manifest=[]
    for name,p in sources.items():
        target=work/'frozen'/('operations_'+name+'.json');shutil.copy2(p,target)
        source_manifest.append({'name':name,'source':str(p),'frozen':target.relative_to(work).as_posix(),'sha256':sha(p)})
    for name in ('clock_alignment.json','preparation_verification.json'):
        shutil.copy2(SIM/'gate_clock_repair_2026-11-10'/name,work/'frozen'/('gate_'+name))
    directive=OLD.parent/'prototype_design_2026-11-10/user_directive_20261110165013_iterate_and_require_approval.md'
    shutil.copy2(directive,work/'USER_DIRECTIVE.md')
    lock=copy.deepcopy(read(OLD/'experiment_lock.json'))
    lock.update(status='PREREGISTERED_FOLLOWUP_BEFORE_RUN',experiment_id=stamp,parent_nine_pilots=str(OLD),
        operator_approval_required_for_any_production_replacement=True,production_model_must_remain='261110162302',
        physical_times_fixed_in_all_cells='same4.8km/h plus path-local slope/stairs scenario',
        behavior_correction='Complete same-stop compatible strategies, including feasible onward transfers; changing an eligibility set is not a walking reroute or a new queue clock',
        operations_sources=source_manifest,source_demand_seed_and44_pair_supply_fixed=True,
        comparison_is_not_independent_empirical_accuracy=True)
    lock['promotion']['automatic_promotion_authorized']=False
    lock['promotion']['requires_new_explicit_user_approval']=True
    lock['pilot_cases']=[{'case':f'{op}-{mode}-regular-mon','mode':mode,'day':'월','scenario':'regular','seed':0,'operations':op}
        for op in ('baseline','distribution_v8','gate_reference') for mode in ('physics','combined')]
    save(work/'experiment_lock.json',lock)
    cfg=read(work/'config.json');cfg.update(complete_same_stop_pool=True,operations='baseline');save(work/'config.json',cfg)
    operations='''"""Versioned supply clocks: distribution scenarios and docking-reference replay stay distinct."""
import bisect
from capacity import batch_size_at_clock
from artifacts import DAYS

def segment_seconds(route,at,day_index):
    profiles=route['segment_profiles'][str(day_index)]
    i=bisect.bisect_right([p[0] for p in profiles],at)-1
    return profiles[max(0,min(len(profiles)-1,i))][2]

def stop_times(route,start,day_index):
    times=[float(start)]
    for k in range(len(route['stops'])-1):times.append(times[-1]+segment_seconds(route,times[-1],day_index)[k])
    return times

def journeys(bundle,rid,info,scenario,day):
    index=list(DAYS).index(day);kind=bundle['prototype_config'].get('operations','baseline')
    if info.get('city') and kind!='baseline':
        route=bundle['operations']['routes'][rid]
        for start in route['departures'][str(index)]:
            yield start,stop_times(route,start,index)
    else:
        for clock in bundle['supply'][scenario][rid]:
            for _ in range(batch_size_at_clock(info,clock)):
                t0=clock+info.get('origin_to_modeled_first_stop_seconds',0)-info['offsets'][info['anchor']]
                yield clock,[t0+x for x in info['offsets']]
'''
    (work/'operations.py').write_text(operations,encoding='utf8')
    def patch(name,old,new,count=1):
        p=work/name;text=p.read_text(encoding='utf8');assert text.count(old)>=count,(name,old[:100]);p.write_text(text.replace(old,new,count),encoding='utf8')
    patch('run_case.py',"config['seed']=case['seed']","config['seed']=case['seed'];config['operations']=case.get('operations','baseline')")
    patch('run_case.py',"'engine.py','run_case.py')","'engine.py','operations.py','run_case.py')")
    patch('prepare.py',"bundle['prototype_config']=config","bundle['prototype_config']=config\n    if config.get('operations','baseline')!='baseline':\n        bundle['operations']=read(ROOT/('frozen/operations_'+config['operations']+'.json'))\n        common['city_operations']=bundle['operations'];common['city_speed_revision']=bundle['operations']['revision']")
    patch('engine.py',"from policy import attach_policy","from policy import attach_policy\nfrom operations import journeys")
    a="""        clocks=bundle['supply'][scenario][rid]
        prefix=info.get('origin_to_modeled_first_stop_seconds',0.)
        clocks=[clock for clock in clocks for _ in range(batch_size_at_clock(info,clock))]
        for clock in clocks:
            t0=clock+prefix-info['offsets'][info['anchor']]"""
    patch('engine.py',a,"        for clock,times in journeys(bundle,rid,info,scenario,day):\n            t0=times[0]")
    patch('engine.py',"t0+info['offsets'][-1]<0","times[-1]<0")
    patch('engine.py',"'t0':t0,'onboard':[]","'t0':t0,'times':times,'onboard':[]")
    patch('engine.py',"for k,offset in enumerate(info['offsets']):\n                when=t0+offset;push", "for k,when in enumerate(times):\n                push")
    patch('engine.py',"t=dep+info['offsets'][end]-info['offsets'][k]+chosen['next_walk'][1]*factor", "t=vehicles[vid]['times'][end]+chosen['next_walk'][1]*factor")
    patch('engine.py',"end=vehicle['t0']+info['offsets'][end_index]", "end=vehicle['times'][end_index]")
    patch('engine.py',"vehicle['t0']+info['offsets'][k+1]", "vehicle['times'][k+1]")
    patch('engine.py',"'t0':v['t0'],'legs':v['legs']", "'t0':v['t0'],'times':v['times'],'legs':v['legs']")
    patch('policy.py',"duration=info['offsets'][target]-info['offsets'][k]", "duration=vehicle['times'][target]-when")
    patch('engine.py',"        same_stop=state.get('node')==node", "        if config.get('complete_same_stop_pool') and config['behavior']!='v9_frozen':\n            stage=policy.complete_same_stop(state,stage,node)\n            state['stages']=list(state['stages']);state['stages'][state['stage']]=stage\n        same_stop=state.get('node')==node")
    method='''        def complete_same_stop(self,state,stage,node):
            # All entries share one physical stop, one arrival/ready clock and
            # one FIFO ticket. Each boarded service carries its own continuation.
            from engine import scaled_stages
            tail=state['stages'][state['stage']+1:];pool=[];seen=set()
            for source in stage.get('pool',[stage]):
                entry=dict(source);entry.setdefault('continuation_stages',tail)
                entry.pop('pool',None);key=(entry['rid'],entry['board'])
                if key not in seen:pool.append(entry);seen.add(key)
            for entry in scaled_stages(bundle.get('compatible_route_policies',{}).get(f"{node}|{state['dest']}",[]),state['factor']):
                key=(entry['rid'],entry['board'])
                if key not in seen and key not in state['used_services']:pool.append(entry);seen.add(key)
            return {**stage,'pool':pool,'expanded_compatible_pool':True,'complete_physical_stop_policy':True}
'''
    patch('policy.py',"        def make_traits(self,uid):",method+"        def make_traits(self,uid):")
    save(work/'creation_manifest.json',{'experiment_id':stamp,'source_code':{n:sha(OLD/n) for n in names},
        'operations_sources':source_manifest,'directive_sha256':sha(directive),'production_latest_sha256':sha(SIM/'public/routing-model/latest.json'),
        'separate_workdir':str(work),'original_nine_runs_preserved':True,'operational_mutations_authorized':False})
    save(pointer,{'experiment_id':stamp,'directory':str(work),'preregistered_cases':6,'production_replacement_requires_approval':True})
    (work/'PLAN.md').write_text('''# 後속 비운영 프로토타입

사용자 지시: 20분 초과 원인을 추적하고 반복 개선한다. 운영 V11 교체는 별도 명시 승인이 있어야 한다. 기존9파일럿과 실패 증거는 보존한다.

우선 확인된 구현 누락을 수정했다. 같은 정류장의 환승 포함 호환 전략이 대기 선택에서 빠졌다. 국제대학원→낙성대 사례는 관악02-2만 기다렸으나 같은 정류장의5511→관악02-1도 실제 연결 가능한 기존 후보에 있었다. 공통 줄의 자격에 이를 포함하며, 대기 시각·FIFO·변경 횟수를 초기화하지 않는다. 임의 20분 강제 이탈·인원 삭제·공급 증대는 사용하지 않는다.

물리 보행시간4.8km/h, 원래 수요·목적지·seed0·44명/피크2대 공급을 모두 고정한다. 월요일 regular에서 기존행동/후속프로토타입×기존시계/V8분포시계/별도정문도킹참조시계를6개 유한 파일럿으로 비교한다. V8 분포와 실제 절대 도착시각은 같지 않다. 도킹참조시계도 정문 근방 탐지일 뿐 승차 시작 실측은 아니다. 월요일 원천을 다른 요일에 전이한 가정은 유지하되 이번 파일럿은 월요일부터 확인한다.

구간시간은 진입시각별로 선택하고 이미 포함된 정차를 다시 더하지 않는다. 시내 운행 보정을 셔틀에 복사하지 않는다. 새 차량시각을 예상·실제 승차·하차·후속 환승에 동일하게 사용하고 정원·적격FIFO·전체가중수요·준비 전 취소·검열·대기/도보/총시간을 독립 검산한다.

초과 사례는 정류장/시간/목적지/개인 이력/만차/대안별로 추적해 후속 후보를 만든다. 개선 근거가 부족하면 계속 NOT_EVALUABLE이며 통과로 꾸미지 않는다. 독립실측과 사용자 승인이 없으므로 이 디렉터리는 운영에 게시하지 않는다.
''',encoding='utf8')
    print(str(work),flush=True)

if __name__=='__main__':main()

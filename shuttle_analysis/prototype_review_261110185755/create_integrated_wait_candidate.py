"""Anticipate future growth of an existing age-frustration term, with no ETA change."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'prototype_followup_261110185755'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'integrated_wait_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py']
    for n in names:shutil.copy2(PARENT/n,work/n)
    shutil.copytree(PARENT/'frozen',work/'frozen')
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg.update(integrate_future_wait_discomfort=True,
        wait_discomfort_interpretation='Anticipate the integral of existing squared age discomfort during future waiting. Existing prospective queue-length curvature is a separate uncalibrated preference; possible overlapping interpretation is not empirically identified. Never added to physical ETA.')
    save(work/'config.json',cfg)
    lock=read(PARENT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(PARENT),
        hypothesis='R9 seed1 waits21.744min after multiple still-active reviews. Current age-squared discomfort evaluates only the current rate times future waiting. Integrate growth over future waiting, using existing600-second age scale, and anticipate age0 growth at new/continuation queues. No hazard, count, physical ETA or supply tuning.',
        pilot_cases=[{'case':'distribution_v8-combined-regular-mon-seed1','mode':'combined','day':'월','scenario':'regular','seed':1,'operations':'distribution_v8'},
                     {'case':'baseline-combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'baseline'},
                     {'case':'gate_reference-combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'gate_reference'}])
    save(work/'experiment_lock.json',lock)
    p=work/'preferences.py';s=p.read_text(encoding='utf8');old='    wait_squared:float=0.';assert old in s
    p.write_text(s.replace(old,old+'\n    wait_cubed:float=0.',1),encoding='utf8')
    p=work/'policy.py';s=p.read_text(encoding='utf8')
    helper='''def prospective_age_discomfort(pred,age,full,config):
    """Extra seconds-equivalent before multiplying taste; never physical time."""
    scale=config['waiting_discomfort_age_scale_seconds'];w=pred.first_wait
    # Sum future age0 growth at every queue, plus only the CURRENT queue's age.
    # Expanded polynomial avoids subtracting nearly equal cubic numbers.
    return (pred.wait_cubed/3+age*w*(age+w))/(scale*scale)+config['waiting_discomfort_full_sensitivity']*full*w


'''
    marker='def signature(stages):';assert marker in s;s=s.replace(marker,helper+marker,1)
    s=s.replace('first_wait=wait_squared=0.','first_wait=wait_squared=wait_cubed=0.',1)
    old='                wait_squared+=max(0.,when-cursor)**2';assert old in s
    s=s.replace(old,old+'\n                wait_cubed+=max(0.,when-cursor)**3',1)
    old='return Prediction(cursor,walk,wait,ride,prep,transfers,fee,crowd,fatigue,first_wait,wait_squared)';assert old in s
    s=s.replace(old,old[:-1]+',wait_cubed)',1)
    old='''            if not changing and pred.wait>0:
                clock=pred.eta-(pred.walk+pred.wait+pred.ride+pred.prep)
                age=max(0.,clock-state['stop_entry'])
                extra=config.get('waiting_discomfort_full_sensitivity',0.)*state['full_passes']+(age/config.get('waiting_discomfort_age_scale_seconds',600.))**2
                base+=state['traits'].wait*pred.first_wait/60*extra'''
    assert old in s
    new='''            if config.get('integrate_future_wait_discomfort',False):
                clock=pred.eta-(pred.walk+pred.wait+pred.ride+pred.prep)
                age=0. if changing else max(0.,clock-state['stop_entry'])
                full=0 if changing else state['full_passes']
                base+=state['traits'].wait*prospective_age_discomfort(pred,age,full,config)/60
            elif not changing and pred.wait>0:
                clock=pred.eta-(pred.walk+pred.wait+pred.ride+pred.prep)
                age=max(0.,clock-state['stop_entry'])
                extra=config.get('waiting_discomfort_full_sensitivity',0.)*state['full_passes']+(age/config.get('waiting_discomfort_age_scale_seconds',600.))**2
                base+=state['traits'].wait*pred.first_wait/60*extra'''
    p.write_text(s.replace(old,new,1),encoding='utf8')
    p=work/'test_prototype.py';s=p.read_text(encoding='utf8').replace('from policy import attach_policy','from policy import attach_policy,prospective_age_discomfort',1)
    marker='    def test_duplicate_options_do_not_amplify_choice(self):';assert marker in s
    tests='''    def test_wait_growth_integral_and_partition_identity(self):
        def value(a,w):return prospective_age_discomfort(Prediction(w,wait=w,first_wait=w,wait_cubed=w**3),a,0,self.config)
        self.assertAlmostEqual(value(600,600),1400.)
        self.assertAlmostEqual(value(0,600),200.)
        self.assertAlmostEqual(value(300,700),value(300,200)+value(500,500),places=9)
        self.assertEqual(value(5000,0),0.)
    def test_future_queue_growth_uses_queue_times_not_walking_or_sunk_eta(self):
        p=Prediction(900,wait=900,first_wait=600,wait_cubed=600**3+300**3)
        self.assertAlmostEqual(prospective_age_discomfort(p,0,0,self.config),225.)
        self.assertEqual(p.eta,900)
        self.assertGreater(prospective_age_discomfort(p,600,2,self.config),225.)
'''
    p.write_text(s.replace(marker,tests+marker,1),encoding='utf8')
    (work/'PLAN.md').write_text('''# 先행 대기 불편의 미래 증가 적분

R9의고정10평일·배차조건은통과했지만Monseed1에서국제대학원21285의두가중통행이21.744분/0.118735를기다렸다.변경4회후에도재검토와승차거절/만차가있었으므로횟수소진은아니다. 기존age²×남은대기식은현재의불편율만앞으로적용한다.

이번가설은기존600초scale와제곱age율을유지하면서미래대기중증가를적분한다. ∫age..age+W (u/S)²du=(age²W+ageW²+W³/3)/S². 현재줄의age교차항은첫W에만,새정류장/후속환승의age0증가는각W_i³/3에적용한다. 기다림이0이면지난대기비용을추가하지않는다.물리ETA·정원·FIFO·수요·준비·운행시계·0.3^n위험률·무제한변경은그대로다.

기존R3의W²길이선호항은별도의미보정prospective비용으로유지한다. 두비용의중첩해석및계수미식별한계가있으며서울대에서입증한심리법칙이나확정된버그수정이라고주장하지않는다.20분강제이탈이나확률을마구올리는대체가아닌명시적가설이다.추가scale·만차·횟수계수튜닝은없다.

실패했던Monregularseed1을먼저검산하고통과하면그부모를재사용한12조건검증을한다. 기존모든실패/부분결과보존,운영V11은새사용자명시승인전교체금지,독립실측부족NOT_EVALUABLE이다.
''',encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(PARENT),'parent_source_sha256':{n:hashlib.sha256((PARENT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'actual_engine_sha256_unchanged':hashlib.sha256((work/'engine.py').read_bytes()).hexdigest()==hashlib.sha256((PARENT/'engine.py').read_bytes()).hexdigest(),
        'additional_numerical_tuning':False,'no20_clipping_or_forced_exit':True,'production_approval_required':True})
    save(pointer,{'directory':str(work),'experiment_id':stamp,'production_approval_required':True});print(work)
if __name__=='__main__':main()

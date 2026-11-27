"""Complete source/receipt checks and a candid team report from finished cases."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import csv,gzip,hashlib,importlib.util,json,math,re,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);P=A/'261116122336'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def write(p,t):
    assert not p.exists(),p
    p.write_text(t,encoding='utf8')
log=w/'finalization.log';assert not log.exists()
def say(t):
    with log.open('a',encoding='utf8') as f:f.write(t+'\n')
    print(t,flush=True)
def run(script,*args):
    out=w/(script.removesuffix('.py')+'-finalization.log');assert not out.exists()
    with out.open('x',encoding='utf8') as f:r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/script),str(w),*args],stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0,(script,r.returncode)
deadline=time.monotonic()+7200
while True:
    state=(w/'workflow.log').read_text(encoding='utf8') if (w/'workflow.log').exists() else ''
    if 'STOP_PRESERVE_PILOT_RESULTS' in state or 'GRID_ANALYSIS_TABLES_COMPLETE' in state:break
    assert not list((w/'runs').glob('*/attempt_01/failure.json')),'Inspect failure; preserve the run'
    assert time.monotonic()<deadline
    time.sleep(10)
decision=read(w/'pilot-decision.json');group='grid' if decision['status']=='PILOT_QUALIFIED' else 'pilot'
assert group=='pilot' or 'GRID_ANALYSIS_TABLES_COMPLETE' in state
run('diagnose_waits.py','--group','pilot')
# Pilot-only queue profiles use their own filenames, retaining the grid script.
src=(ROOT/'stop_queue_exposure.py').read_text(encoding='utf8')
src=src.replace('grid-stop-queue-exposure.csv','pilot-stop-queue-exposure.csv').replace('grid-validation.json','pilot-validation.json')
src=src.replace('assert len(rows)==990','assert len(rows)==297').replace("w/'prediction-information-audit.json'","w/'pilot-prediction-information-audit.json'")
write(ROOT/'pilot_stop_queue_exposure.py',src);run('pilot_stop_queue_exposure.py')
validation=read(w/f'{group}-validation.json');main=[r for r in validation['results'] if not r['case']['case'].startswith('ablation')]
assert len(main)==(10 if group=='grid' else 2)
pilot=read(w/'pilot-validation.json')['results'];parent=[r for r in read(P/'pilot-validation.json')['results'] if not r['case']['case'].startswith('ablation')]
original=read(A/'261116010854/grid-validation.json')['results']
over=lambda r:r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
maximum=lambda r:r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
quant=lambda r:r['extended_diagnostics']['finished_trip_quantiles']['total_min']

# Check immutable code, old artifacts, inputs and numerical assumptions.
manifest=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');cfg=read(w/'config.json');lock=read(w/'experiment_lock.json')
count=0
for p,digest in manifest['protected'].items():assert sha(Path(p))==digest,p;count+=1
for name,digest in manifest['frozen_payloads'].items():assert sha(w/name)==sha(P/name)==digest,name;count+=1
for name,digest in future['frozen_sha256'].items():assert sha(w/name)==digest,name;count+=1
protocol=read(w/'protocol-reference.json');assert sha(Path(protocol['path']))==protocol['sha256']
prior_cfg=read(P/'config.json');numeric={k:v for k,v in prior_cfg.items() if type(v) in (int,float)}
assert all(cfg[k]==v for k,v in numeric.items())
units={}
for name,expected in [('enabled-final.log',144),('legacy-final.log',89)]:
    t=(w/name).read_text(encoding='utf8');nums=re.findall(r'Ran (\d+) tests?',t)
    assert len(nums)==1 and int(nums[0])==expected and re.search(r'^OK\s*$',t,re.M);units[name]=expected
assert read(w/'loyalty-invariant-check.json')['status']=='PASS'
assert read(w/'preparation-catalog-audit.json')['status']=='PASS_PREPARATION_ONLY'
assert read(w/'static-scope-proof.json')['status']=='PASS_STATIC_SCOPE'
profiles=[]
folders=list((w/'runs').glob('*/attempt_01'));assert len(folders)==(11 if group=='grid' else 3)
for folder in folders:
    start=read(folder/'started.json');result=read(folder/'result.json');case=start['case']
    assert result['status']=='COMPUTED_NOT_EMPIRICALLY_VALIDATED'
    assert start['experiment_lock_sha256']==sha(w/'experiment_lock.json') and start['input_manifest_sha256']==sha(w/'input_manifest.json')
    assert len(start['code_sha256'])==18
    for name,digest in start['code_sha256'].items():assert sha(w/name)==sha(folder/'source_snapshot'/name)==digest;count+=2
    effective={**cfg,'seed':case['seed'],'operations':case['operations'],**case.get('config_overrides',{}),'physics':'path_local_4p8','behavior':'sequential','origin_choice':True,'boarding_choice':True}
    assert start['config']==effective
    ref=next(r for r in original if (r['case']['day'],r['case']['scenario'])==(case['day'],case['scenario']))
    old=read(Path(ref['source_directory'])/'result.json')['policy_report']['student_strategy'];new=result['policy_report']['student_strategy']
    assert set(old['initial_mode_weights'])==set(new['initial_mode_weights'])
    assert all(abs(value-new['initial_mode_weights'][key])<1e-6 for key,value in old['initial_mode_weights'].items())
    assert old['patience_draw_sample']==new['patience_draw_sample']
    assert new['initial_trunk_checks'].get('violation_weight',0)==0
    repair=result['policy_report'].get('catalog_repair')
    assert (repair and repair['restored_count']==5) if effective['restore_known_snu_direct_policies'] else repair is None
    profiles.append({'case':case['case'],'initial_mode_mass_unchanged':True,'exact_patience_draw_sample':len(new['patience_draw_sample'])})
assert read(w/f'{group}-behavior-validation.json')['status']=='PASS_STUDENT_BEHAVIOR_GATES'
diag=next(r for r in pilot if r['case']['case'].startswith('ablation'));ref=next(r for r in parent if r['case']['day']=='화')
values=lambda r:[over(r),maximum(r),*quant(r).values()]
errors=[abs(x-y) for x,y in zip(values(diag),values(ref))];assert max(errors)<1e-6

# Selected initial-plan diagnostics, not a new population or field sample.
def result_for(case):return read(w/'runs'/case/'attempt_01/result.json')['policy_report']['initial_policy_diagnostics']
on=next(r for r in pilot if not r['case']['case'].startswith('ablation') and r['case']['day']=='화')
on_rows={r['uid']:r for r in result_for(on['case']['case'])};off_rows={r['uid']:r for r in result_for(diag['case']['case'])}
focus=read(ROOT/'law-snu-cohort-trace.json')['latest_focus_uid_weights'];changed=[]
for uid,weight in focus.items():
    a=off_rows.get(int(uid));b=on_rows.get(int(uid))
    if a is None or b is None:continue
    selected=next((c for c in b['candidates'] if c['key']==b['selected_source_key']),None)
    changed.append({'uid':int(uid),'reference_peak_weight':weight,'old_first_node':a['selected_first_node'],'old_primary_node':a['selected_primary_node'],
        'new_first_node':b['selected_first_node'],'new_primary_node':b['selected_primary_node'],
        'new_selected_restored_direct':bool(selected and selected['restored_direct'])})
save(w/'initial-choice-comparison.json',{'scope':'Fixed parent-F Tuesday peak cohort; weighted diagnostic, not current queue stock, independent students or new observations.',
    'rows':changed,'reference_peak_weight_matched':math.fsum(r['reference_peak_weight'] for r in changed),
    'old_law_primary_new_elsewhere_weight':math.fsum(r['reference_peak_weight'] for r in changed if r['old_primary_node']==60 and r['new_primary_node']!=60)})

# Read public state; this program has no publisher or production write path.
script=A/'261112111627/verify_production_unchanged_v2.py';spec=importlib.util.spec_from_file_location('public_readback',script);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
lab='https://snu-shuttle-simulation.vercel.app/';rel=f'routing-model/releases/{mod.MODEL}.json'
jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+rel),('data_payload','https://snu-shuttle-v9-data.vercel.app/'+rel),('route_api','https://snu-route-lab.vercel.app/api/queue-model')]+[(n,lab+n) for n in ['index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css']]
with ThreadPoolExecutor(max_workers=4) as pool:public=list(pool.map(mod.fetch,jobs))
save(w/'artifact-verification.json',{'status':'PASS_RESULT_INTEGRITY','hash_checks':count,'runtime_modules':18,'fixed_payloads':len(manifest['frozen_payloads']),
    'future_source_hashes':len(future['frozen_sha256']),'actual_single_attempt_cases':len(folders),'main_cases':len(main),'diagnostic_cases':1,
    'unit_tests':units,'loyalty_guards':5,'initial_profile_checks':profiles,'disabled_parent_metric_errors':errors,
    'existing_numeric_parameters_unchanged':numeric,'public_readback':public,'public_readback_all_passed':all(r['check']=='PASS' for r in public),
    'expected_public_model':mod.MODEL,'checked_at':datetime.now(timezone.utc).isoformat(),'new_date_accuracy':'NOT_EVALUATED','production_writes':False})

# Report matched parent pilot and wider original reference separately.
law=read(w/'pilot-law-transfer-metrics.json')['cases'];oldlaw=read(w/'parent-law-reference.json')['cases']
fields=[r for r in rows(w/'pilot-field-comparison.csv') if r['model']==w.name and not r['case'].startswith('ablation')]
assert len(fields)==4
s=[f'# 법대 설입행 환승 집중:직통 선택지 복원 {w.name}','',
    f"사전 월·화 판정은 **{decision['status']}**입니다. 실행·행동 정합성과 성과 판정은 다릅니다. 공개V11과기존후보는유지했습니다. 본문 첫 비교는직전후보F122336과같은월·화기본배차이고,전요일표는원래기준010854와비교합니다.",'',
    '## 확인된 원인과 수정','',
    '법대설입행환승수요17.8368명상당은모두초기경로배정에서들어왔습니다. 그중15.6111명상당의원래첫노선은5511이었습니다. 이후줄을보고변경한행동만으로설명할수없었습니다.',
    '고정확장카탈로그는같은rid/board당하차·꼬리하나만남겼습니다. 제2공학관·제1공학관·에너지·공대입구·농생대의5511설입직통은single-stage자료에있지만full확장에는자연대하차→행정관셔틀만남았습니다. city주수단을지키는학생의새승차지비교에서직통이누락될수있는구조입니다.',
    '이미존재하는직통5개를별도1entry완전정책으로초기선택에복원했습니다. 같은자리재검토에서도같은서비스의하차·연결정책을교체한별도pool을비교합니다. 기존pool에동일rid/board를두번붙이지않습니다. 원점×기존보행×정책옵션48개가추가됐고,이는48명·48신규노선·48독립추첨권이아닙니다.',
    '수요·목적지·운행·정원·물리/보행경로·숫자계수·미예견인지·개인인내·현재줄압력·무제한변경/반복도보·재방문금지·정문최종대안은유지했습니다. 전역카탈로그와도보중승차의기존entries/walkids도같습니다.','',
    '## 같은 월·화:부모F → 복원후보','',
    '|지표|전→후|','|---|---:|',
    f"|20분초과가중대기구간합|{decision['over20_before']:.3f}→{decision['over20_after']:.3f}|",
    f"|최대연속대기(분)|{decision['max_wait_before']:.3f}→{decision['max_wait_after']:.3f}|",
    f"|재사용4관측기대절대오차합|{decision['field_error_sum_before']:.3f}→{decision['field_error_sum_after']:.3f}|",
    f"|월·화평균총시간변화(분)|{decision['mean_journey_delta_minutes'][0]:+.3f}/{decision['mean_journey_delta_minutes'][1]:+.3f}|",
    f"|15~20시법대양방향최대(명상당)|{decision['afternoon_law_max_before']:.3f}→{decision['afternoon_law_max_after']:.3f}|",
    f"|15~20시설입행이전버스하차후법대도착합|{decision['afternoon_snu_transfer_arrivals_before']:.3f}→{decision['afternoon_snu_transfer_arrivals_after']:.3f}|",'',
    '가중대기구간과누적도착은고유학생수가아닙니다. 누적유입과한시점줄크기를서로비교하지않습니다.40명은회상점검기준이며줄상한으로사용하지않았습니다.','',
    '|요일·ARS|오후최대줄전→후|40명초과누적분전→후|','|---|---:|---:|']
for b in law:
    if b['case']['case'].startswith('ablation'):continue
    a=next(x for x in oldlaw if x['case']['day']==b['case']['day'])
    for z in b['law_profiles']:
        before=next(x for x in a['law_profiles'] if x['node']==z['node']);ars=21270 if z['node']==47 else 21298
        s.append(f"|{b['case']['day']}·{ars}|{before['maximum_queue']:.3f}→{z['maximum_queue']:.3f}|{before['minutes_above40']:.3f}→{z['minutes_above40']:.3f}|")
s+=['','## 재사용관측비교','',
    '관측분안의초는미상이며균등적분한기대오차입니다. 이미여러후보에사용한4관측으로독립실측검증이아닙니다. 문화관방향·월요일날짜대응불확실성도계승했습니다.','',
    '|시각|부모F분평균→후보|기대절대오차전→후|','|---|---:|---:|']
for r in decision['observations']:s.append(f"|{r['minute']}|{r['old_mean']:.3f}→{r['new_mean']:.3f}|{r['old_error']:.3f}→{r['new_error']:.3f}|")
s+=['','## 원래010854와의넓은비교','',
    '부모F는전요일이완료되지않았습니다. 아래는카탈로그복원외의기존변경도포함한전체후보비교이며단일수정의독립효과로해석하지않습니다.','',
    '|요일·배차|평균총시간전→후(분)|최대대기전→후(분)|20분초과가중구간전→후|p99총시간전→후|','|---|---:|---:|---:|---:|']
for r in main:
    old=next(x for x in original if (x['case']['day'],x['case']['scenario'])==(r['case']['day'],r['case']['scenario']))
    s.append(f"|{r['case']['day']}·{r['case']['scenario']}|{quant(old)['mean']:.3f}→{quant(r)['mean']:.3f}|{maximum(old):.3f}→{maximum(r):.3f}|{over(old):.3f}→{over(r):.3f}|{quant(old)['p99']:.3f}→{quant(r)['p99']:.3f}|")
cause=read(w/'pilot-wait-cause-ledger.json')['cases']
s+=['','## 残여긴대기와한계','',
    '개인인내는강제이탈시계가아니라대안검토기준입니다.20분초과와개인기준초과,첫승차예측오차를별도원장에기록했습니다. 기존일반50·마을24정원과외부배경승객미포함,수업종료수요와당일마지막수업귀가의차이는남은가정입니다. 직통복원이모든이상대기를없앴다고가정하지않습니다.',
    '초기점수는접근편이용시주노선정류장도착까지이고후속대기를미예견합니다. 실제주노선승차완료시각이나최소총시간과동일하다고부르지않습니다. 그가정을몰래바꾸어수치를맞추지않았습니다.',
    '비활성화화요일은부모F수치를1e-6내로재현했습니다. 새날짜실측정답은열지않았고독립정확도는미평가입니다.','',
    '## 자료·검산','',
    '[사전계획](../v12_law_snu_followup_20261116/PROTOCOL.md),[초기선택비교](initial-choice-comparison.json),[기능OFF대조및보존검사](artifact-verification.json),[준비전후동일성](preparation-catalog-audit.json),[입력/출처](SOURCES_AND_ASSUMPTIONS.md),',
    f'[모든정류장대기]({group}-all-recorded-stops.csv),[정류장·30분대기]({group}-all-recorded-half-hour-waits.csv),[오후법대]({group}-law-transfer-metrics.json),[20분초과원인](pilot-wait-cause-ledger.json).','']
write(w/'RESULTS.md','\n'.join(s))
source='''# 자료·가정·출처

사용자료는기존동결수업표/가중계획/버스운행/물리경로와이미사용한4대기관측입니다. 새학생주소·당일마지막수업·새선호설문을수집한것은아닙니다.

- [수업종료추출](frozen/class_endings_source_20261106.json),[고정가중수요](frozen/prepared_capacity44_pair.json.gz),[고정운행](frozen/operations_v12_empirical.json),[실측맥락](frozen/empirical_evidence.json).
- [셔틀44명수정근거](capacity44_amendment.json),[기존피크편성가정](pair_amendment.json)을계승했습니다. 일반50·마을24명은노선별실제등록정원미확인이고외부배경승객은물리수요에추가되지않았습니다. 혼잡등급을인원으로바꾸지않았습니다.
- 기존월요일대응16:53행정관53명,16:55문화관5명(방향미상),17:03정문21128의33~39명,화15:23줄합류67명(본인포함)을재사용했습니다. 화189초승차/이후30초·44명두대중두번째라는기존수정도계승했습니다. 분안의초를균등적분하며사진이나운행대안을독립관측으로세지않습니다.
- 보행4.8km/h/개인배율,기존대기·환승·변경·혼잡계수,중앙값20분/로그표준편차0.1개인인내,2분선택오차,만차2회/추가2통과,출발지연1.125배는모두기존값입니다. 이값들은모두이번서울대실측으로식별한계수가아닙니다. 출발지연배율은이전에이미사용한관측에맞춘값입니다.

이번변경은single-stage카탈로그에이미있는직통5개를원점확장/동일플랫폼후속정책비교에서볼수있게하는것입니다. 전역full/single/alternatives,도보중승차entries/walkids,수요/목적지/운행/물리경로는준비전후동일합니다.48은정책항목수이며사람수나새노선수가아닙니다.

[독립카탈로그진단](../collaboration/v12_law_snu_followup_20261116/CATALOG_FOLLOWUP.md),[신규소스정적검토](../collaboration/v12_law_snu_followup_20261116/DIRECT_RESTORATION_STATIC_REVIEW_261116153200.md)를참조하십시오. 정적검토자는모델이나검사를실행하지않았고,소유자가실행한검사와정적검토를구분합니다.

문헌배경은[Dixit등(2021)원문](https://pure.tudelft.nl/ws/portalfiles/portal/104805930/Perception_of_overlap_in_multi_modal_urban_transit_route_choice.pdf)의소개와2.2절을확인했습니다. 경로중첩의확률가정문제를다루지만현재초기선택은primary_node당대표1개이므로단순중복추첨을이번원인으로주장하지않습니다. PSCL계수나암스테르담계수를서울대에이식하지않았습니다.

초기/이후후속환승대기미예견은기존사용자행동가정입니다. 인지ETA와실제운영예측은분리되며실제줄·정원·시간은원래물리모형으로계산합니다. 단순선형효용으로바꾸거나숫자를새로맞추지않았습니다. 새날짜원본정답은열지않았으며독립검증/운영채택은미완료입니다.
'''
write(w/'SOURCES_AND_ASSUMPTIONS.md',source)
intro=f'''# 법대 설입행 환승 집중:팀 전달 {w.name}

현재판정은 **{decision['status']}**입니다. 기존공개모델을유지하며별도후보를비교했습니다. 확인된원인은같은5511서비스의직통과셔틀접근을하나로축약해확장직통5개가빠지는문제입니다. 이미있는직통을별도정책으로복원했고,수요·배차·정원·행동숫자는바꾸지않았습니다.

|월·화부모F비교|전→후|
|---|---:|
|20분초과가중구간|{decision['over20_before']:.3f}→{decision['over20_after']:.3f}|
|최대대기(분)|{decision['max_wait_before']:.3f}→{decision['max_wait_after']:.3f}|
|재사용4관측기대절대오차합|{decision['field_error_sum_before']:.3f}→{decision['field_error_sum_after']:.3f}|
|15~20시설입행환승후법대유입합|{decision['afternoon_snu_transfer_arrivals_before']:.3f}→{decision['afternoon_snu_transfer_arrivals_after']:.3f}|

본실행은{len(main)}조건,비활성화진단1조건입니다. 관측을재사용한모의비교이며독립날짜실측검증은아닙니다. 추가조건미실행/실행여부와악화항목은판정및상세표를보십시오.

- [원인·요일별결과·정문/법대·남은긴대기](RESULTS.md)
- [자료·가정·출처](SOURCES_AND_ASSUMPTIONS.md)
- [직접부모와의사전판정](pilot-decision.json)
- [동일원점초기선택의대조](initial-choice-comparison.json)
- [코드·고정입력·모드/인내·대조재현·공개모델검사](artifact-verification.json)
- [모든정류장대기]({group}-all-recorded-stops.csv)
- [정류장·30분진입집단대기]({group}-all-recorded-half-hour-waits.csv)

목적지별단일시점줄·누적유입·최대대기·평균총시간은다른지표입니다.40명상한/20분강제이탈이나누락승객추가로결과를맞추지않았습니다.
'''
write(w/'START_HERE.md',intro)
local_links=0
for name in ['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md']:
    for href in re.findall(r'\]\(([^)]+)\)',(w/name).read_text(encoding='utf8')):
        if href.startswith(('http://','https://','#')):continue
        assert (w/href).resolve().exists(),(name,href);local_links+=1
names=['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md','artifact-verification.json','pilot-decision.json','initial-choice-comparison.json']
save(w/'TEAM_PACKAGE.json',{'created_at':datetime.now(timezone.utc).isoformat(),'release_id':w.name,'entry_point':'START_HERE.md',
    'document_sha256':{n:sha(w/n) for n in names},'local_links_checked':local_links,'main_cases':len(main),'diagnostic_cases':1,
    'pilot_status':decision['status'],'new_date_accuracy':'NOT_EVALUATED','operating_adoption_recommended':False,'production_writes':False})
say('FINAL_REPORT_AND_VERIFICATION_COMPLETE')

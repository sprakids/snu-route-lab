"""Read frozen V12 data/functions only; never run or modify a simulation."""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ANALYSIS=HERE.parents[2]
WORK=ANALYSIS/'261112111627'
BUILD=ANALYSIS/'v12_build_2026-11-12'
sys.dont_write_bytecode=True
sys.path.insert(0,str(WORK))
from time_profiles import values_at,assert_fifo_profiles
from empirical_v12 import Evidence,api_grade,ordinal_grade
from operations import stop_times as runtime_times
sys.path.insert(0,str(BUILD))
from v12_supply import invert_passage

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def independent_duration(route,at,day,k):
    profiles=route['segment_profiles'][str(day)]
    if at<=profiles[0][0]:return profiles[0][2][k]
    for left,right in zip(profiles,profiles[1:]):
        if at<right[0]:
            ratio=(at-left[0])/(right[0]-left[0])
            return left[2][k]*(1-ratio)+right[2][k]*ratio
    return profiles[-1][2][k]
def independent_times(route,start,day):
    out=[start]
    for k in range(len(route['stops'])-1):out.append(out[-1]+independent_duration(route,out[-1],day,k))
    return out

def main():
    watched=[WORK/x for x in ['operations.py','analyze_followup.py','empirical_v12.py','time_profiles.py','policy.py','frozen/operations_v12_empirical.json','frozen/empirical_evidence.json']]
    watched += [BUILD/x for x in ['time_profiles.py','v12_supply.py','empirical_v12.py','prepare_v12.py']]
    before={str(p.relative_to(ANALYSIS)):sha(p) for p in watched}
    ops=load(WORK/'frozen/operations_v12_empirical.json');evidence=load(WORK/'frozen/empirical_evidence.json')
    findings=[];min_slope=1.;max_value_difference=0.;knot_checks=0;inversions=[];boundary_pairs=[];min_gap={};same_days={}
    for rid,route in ops['routes'].items():
        same_days[rid]=all(p==route['segment_profiles']['0'] for p in route['segment_profiles'].values())
        assert same_days[rid],'Supply inversion currently assumes identical day profiles; future day-varying profiles need a day arg'
        min_slope=min(min_slope,assert_fifo_profiles(route))
        for day,profiles in route['segment_profiles'].items():
            assert all(len(p[2])==len(route['stops'])-1 for p in profiles)
            assert all(math.isfinite(v) and v>0 for p in profiles for v in p[2])
            for point in profiles:
                for at in [point[0]-.0001,point[0],point[0]+.0001]:
                    actual=values_at(route,at,int(day))
                    expected=[independent_duration(route,at,day,k) for k in range(len(actual))]
                    diff=max(abs(a-b) for a,b in zip(actual,expected));max_value_difference=max(max_value_difference,diff)
                    assert diff<1e-8;knot_checks+=len(actual)
        reference=next(i for i,s in enumerate(route['stops']) if s['seq']==route['reference_seq'])
        for target in [40800.,54000.-.01,54000.,61200.,68400.,83399.99]:
            start,error,actual=invert_passage(route,target,reference)
            independently=independent_times(route,start,0)[reference]
            inversions.append({'route':rid,'target':target,'error':independently-target})
            assert abs(independently-target)<2e-5
        source_starts=load(WORK/'frozen/operations_observed_train_v1.json')['routes'][rid]['departures']
        minimum=float('inf')
        for day,starts in route['departures'].items():
            times=[runtime_times(route,s,int(day))[reference] for s in starts]
            assert all(b>a for a,b in zip(times,times[1:]))
            for a,b,ta,tb in zip(starts,starts[1:],times,times[1:]):
                minimum=min(minimum,tb-ta)
                if tb-ta<15:
                    boundary_pairs.append({'route':rid,'day':int(day),'start_a':a,'start_b':b,'reference_a':ta,'reference_b':tb,
                         'reference_gap':tb-ta,'gap_inside_collection_window':40800<=ta<83400 and 40800<=tb<83400,
                         'a_was_original_start':any(abs(a-s)<1e-5 for s in source_starts[day]),
                         'b_was_original_start':any(abs(b-s)<1e-5 for s in source_starts[day])})
        min_gap[rid]=minimum
    # Execute only the auditor's city-clock reconstruction, extracted as a pure function.
    source=(WORK/'analyze_followup.py').read_text(encoding='utf-8');tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='expected_roster')
    scope={'ROOT':WORK,'read':load,'base':SimpleNamespace(DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'},END=83400.)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<frozen auditor city clocks>','exec'),scope)
    days=list(scope['base'].DAYS)
    bundle={'prepared':{'common':{'route_info':{rid:{'city':True,'capacity':60} for rid in ops['routes']}}}}
    roster_checks=0;max_clock_difference=0.
    for index,day in enumerate(days):
        actual=scope['expected_roster'](bundle,{'operations':'v12_empirical','day':day,'scenario':'regular'})
        expected=[]
        for rid,route in ops['routes'].items():
            for start in route['departures'][str(index)]:
                times=runtime_times(route,start,index)
                if times[0]>83400. or times[-1]<0:continue
                expected.append((rid,times))
        assert len(actual)==len(expected)
        for row,(rid,times) in zip(actual,expected):
            assert row[0]==rid
            diff=max(abs(a-b) for a,b in zip(row[4],times));max_clock_difference=max(max_clock_difference,diff)
            assert diff<1e-8;roster_checks+=1
    assert api_grade(0) is None and api_grade('0') is None and api_grade(3)==0 and ordinal_grade(0)==0
    assert all(api_grade(x) is None for x in [None,'',1,2,7,'0.0'])
    for c in evidence['grades'].values():assert len(c['counts'])==4 and all(isinstance(n,int) and n>=0 for n in c['counts'])
    for c in evidence['transitions'].values():assert len(c['counts'])==4 and all(len(a)==4 and all(isinstance(n,int) and n>=0 for n in a) for a in c['counts'])
    ev=Evidence(evidence);exposure_tests=[]
    for rid,seqs in evidence['route_sequences'].items():
        for i,seq in enumerate(seqs[:-1]):
            hour=17
            if rid not in evidence['missing_crowd_routes'] and not evidence['grades'].get(f'{rid}|{seq}|{hour}'):continue
            end=min(i+4,len(seqs)-1);times=[61200.+k*60 for k in range(len(seqs))]
            exposure,context=ev.context(rid,i,end,61200.,times)
            if rid in evidence['missing_crowd_routes']:assert exposure is None and context['initial_grade_n']==0
            else:assert exposure is not None and -1e-8<=exposure<=times[end]-times[i]+1e-8
            exposure_tests.append({'route':rid,'board_index':i,'missing':exposure is None})
    for rid in evidence['missing_crowd_routes']:assert not any(k.startswith(rid+'|') for k in evidence['grades'])
    unchanged=all(sha(ANALYSIS/k)==v for k,v in before.items());assert unchanged
    result={'review_scope':'frozen code/time/ordinal semantics only; no simulation run, tuning, promotion or new outcome-day read',
      'reviewed_at':__import__('datetime').datetime.now(__import__('datetime').timezone(__import__('datetime').timedelta(hours=9))).isoformat(),
      'code_and_input_sha256':before,'unchanged':unchanged,'same_weekday_profiles_guard':same_days,
      'minimum_link_arrival_slope':min_slope,'profile_knot_scalar_checks':knot_checks,
      'max_independent_value_difference_seconds':max_value_difference,'extra_inverse_cases':inversions,
      'auditor_runtime_city_roster_matches':roster_checks,'max_auditor_runtime_clock_difference_seconds':max_clock_difference,
      'minimum_reference_passage_gaps':min_gap,'boundary_under15s_pairs':boundary_pairs,
      'api_zero_unknown_and_normalized_zero_spare_distinct':True,'probability_mass_exposure_tests':exposure_tests,
      'not_established':['actual passenger/seat counts','empirical queue or journey accuracy','weekday effects from one training day','independent untouched holdout performance']}
    (HERE/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['code_and_input_sha256','extra_inverse_cases','probability_mass_exposure_tests','boundary_under15s_pairs']},ensure_ascii=False))
    print('under15s_reference_gap_pairs',len(boundary_pairs),'inside_collection',sum(x['gap_inside_collection_window'] for x in boundary_pairs))
    print(json.dumps(boundary_pairs[:12],ensure_ascii=False))

if __name__=='__main__':main()

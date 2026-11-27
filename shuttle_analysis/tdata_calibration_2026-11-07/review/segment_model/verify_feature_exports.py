"""Independent CSV-level reconstruction after READY; no engine or API use."""
from pathlib import Path
from collections import defaultdict
import csv,json,gzip,hashlib,math,argparse

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out',default='outputs');args=parser.parse_args()
OUT=ROOT/args.out
assert json.loads((OUT/'READY.json').read_text(encoding='utf-8'))['status']=='READY_CONDITIONAL_FEATURES'
prov=json.loads((OUT/'provenance.json').read_text(encoding='utf-8'))
assert hashlib.sha256((ROOT/'run_segment_features.py').read_bytes()).hexdigest()==prov['runner_sha256']
REPS=prov['replications'];assert REPS==10
groups=('dorm','snu','nak','daehak')
rho=5772/29613
weights={'dorm':rho*.5,**{g:(1-rho)/3*.5 for g in groups[1:]}}
assert abs(sum(weights.values())-.5)<1e-12
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def ck(r):return (r['clock'],r['weekday'],r['destination_group'],r['route_id'],int(r['current_link_index0']),int(r['day_offset']),int(r['hour']))
mean={};metadata={}
for r in read(OUT/'conditional_segment_hour.csv'):
    key=ck(r);assert key not in mean
    value=float(r['conditional_trip_events']);assert value>0 and math.isfinite(value)
    assert 0<=key[-1]<24 and key[0] in ('segment_entry','boarding_hour') and key[2] in groups
    mean[key]=value;metadata[(r['route_id'],int(r['current_link_index0']))]=r
reconstructed=defaultdict(float);replicates=set();repkeys=set();repcount=0
with gzip.open(OUT/'conditional_segment_hour_by_rep.csv.gz','rt',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        rep=int(r['replicate']);key=ck(r);assert (rep,key) not in repkeys
        repkeys.add((rep,key));replicates.add(rep)
        reconstructed[key]+=float(r['conditional_trip_events'])/REPS;repcount+=1
assert replicates==set(range(1,REPS+1)) and set(reconstructed)==set(mean)
mean_error=max(abs(mean[k]-reconstructed[k]) for k in mean);assert mean_error<1e-9
expected_base=defaultdict(float);clocktotals=defaultdict(float);bysegment=defaultdict(lambda:defaultdict(float))
for (clock,day,g,rid,k,offset,hour),v in mean.items():
    expected_base[(clock,day,rid,k,offset,hour)]+=v*weights[g]
    clocktotals[clock]+=v
    bysegment[(day,g,rid,k)][clock]+=v
persegment_clock_error=max(abs(v.get('segment_entry',0)-v.get('boarding_hour',0)) for v in bysegment.values())
assert persegment_clock_error<1e-8
baseline={}
for r in read(OUT/'baseline_segment_hour.csv'):
    key=(r['clock'],r['weekday'],r['route_id'],int(r['current_link_index0']),int(r['day_offset']),int(r['hour']))
    assert key not in baseline;baseline[key]=float(r['expected_trip_events'])
assert set(baseline)==set(expected_base)
baseline_error=max(abs(baseline[k]-expected_base[k]) for k in baseline);assert baseline_error<1e-9
index=list(read(OUT/'segment_index.csv'));assert len(index)==259
indexmap={(r['route_id'],int(r['current_link_index0'])):r for r in index}
assert len(indexmap)==259 and set(metadata)<=set(indexmap)
for key,m in metadata.items():
    for col in ('current_from_seq','current_to_seq','from_stop_id','to_stop_id','observed_sta_sn'):
        assert m[col]==indexmap[key][col]
rounding=list(read(OUT/'rounding_diagnostics.csv'))
round_error=max(abs(float(r['prefix_rounding_error_seconds'])) for r in rounding)
assert round_error<=.500000001
paired=list(read(OUT/'replication_replay_checks.csv'));assert len(paired)==10
assert all(float(r['stop_bin_max_difference'])==0 and float(r['mode_max_difference'])==0 for r in paired)
assert all(float(r['board_index0'])<float(r['alight_index0']) for r in rounding)
result={'status':'PASS_INDEPENDENT_EXPORT_RECONSTRUCTION','replications':REPS,'conditional_rows':len(mean),
    'replicate_rows':repcount,'baseline_rows':len(baseline),'mean_of_all_10_reps_max_difference':mean_error,
    'baseline_probability_reconstruction_max_difference':baseline_error,
    'clock_total_conservation_max_difference_per_origin_destination_segment':persegment_clock_error,
    'conditional_clock_totals':dict(clocktotals),'segments_in_preserved_network':len(index),
    'segments_with_positive_model_features':len(metadata),'day_offsets':sorted({k[-2] for k in mean}),
    'largest_prefix_rounding_error_seconds':round_error,
    'calendar_or_provider_semantics_validated':False,'empirical_calibration_performed':False}
(OUT/'export_reconstruction_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

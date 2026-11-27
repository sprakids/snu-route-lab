"""Run and validate an isolated release-time and early boarding experiment."""
from pathlib import Path
import argparse
import contextlib
import os
import shutil
from timing_inputs import HERE, REFERENCE, MODEL, ref, inputs, metadata
import dwell_engine as engine
from case_audit import audit_case

DATA=HERE/'viewer-data'


def prepare():
    common=metadata(ref.load(REFERENCE/'viewer-data/common.json.gz'))
    DATA.mkdir(exist_ok=True)
    ref.previous.PACK(DATA/'common.json.gz',common)


def run(day,service,recheck):
    key=f'{service}-{ref.DAYS[day]}'
    out=HERE/'runs'/key/'attempt-01'
    out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():
        assert ref.load(out/'result.json')['model']==MODEL
        return
    b,patch,donors,timing=inputs(day,service)
    ref.previous.SAVE(out/'timing.json',timing)
    engine.WORK=engine.OUT=engine.base.OUT=out
    if not recheck:
        if (out/f'audit-{key}.json.gz').exists():
            raise ValueError('Use --verify-existing for this completed simulation.')
        with (out/'run.log').open('a',encoding='utf8') as log,contextlib.redirect_stdout(log):
            engine.simulate(b,day,service)
    result=audit_case(b,day,service,out,patch,donors,True)
    result['timing']=timing
    old=ref.load(REFERENCE/'runs'/key/'attempt-01/result.json')
    assert old['weekday_demand']==result['weekday_demand']
    assert old['initial']==result['initial']
    staged=DATA/f'{key}.tmp'
    shutil.copyfile(out/f'{key}.json.gz',staged)
    os.replace(staged,DATA/f'{key}.json.gz')
    ref.previous.SAVE(out/'result.tmp',result)
    os.replace(out/'result.tmp',out/'result.json')
    print(key,result['weekday_demand'],result['max_continuous_wait'],result['unserved'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--day',choices=ref.DAYS)
    parser.add_argument('--service',choices=('peak','regular'))
    parser.add_argument('--verify-existing',action='store_true')
    args=parser.parse_args()
    if args.prepare:prepare()
    else:run(args.day,args.service,args.verify_existing)

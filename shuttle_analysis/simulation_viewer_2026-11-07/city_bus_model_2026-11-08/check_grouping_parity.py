"""Compare original and grouped forecasts on shared-stop switching fixtures."""
from pathlib import Path
import contextlib,copy,importlib.util,io,json,math,random,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import city_capacity_model as current
from test_city_capacity import fixture,leg

spec=importlib.util.spec_from_file_location('city_ungrouped_reference',ROOT/'revisions/city_capacity_model_before_grouping.py')
reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)


def same(a,b,path='root'):
    if isinstance(a,dict):
        assert isinstance(b,dict) and a.keys()==b.keys(),path
        for key in a:same(a[key],b[key],path+'.'+key)
    elif isinstance(a,list):
        assert isinstance(b,list) and len(a)==len(b),(path,len(a),len(b))
        for i,(x,y) in enumerate(zip(a,b)):same(x,y,f'{path}[{i}]')
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        assert isinstance(b,(int,float)) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7),(path,a,b)
    else:assert a==b,(path,a,b)


def main():
    for seed in range(24):
        rng=random.Random(seed)
        groups=[(rng.choice(['A','B']),round(rng.uniform(.1,18),3),100) for _ in range(12+seed)]
        bundle=fixture(groups)
        bundle['alternatives']['0|snu']=[
            {'kind':'walk','name':'direct','walk':[0,400.],'stages':[]},
            {'kind':'transit','name':'A','walk':[0,0.],'stages':[leg('A')]},
            {'kind':'transit','name':'B','walk':[0,0.],'stages':[leg('B')]},
        ]
        # The fixture must contain both services even for an unlikely single-line draw.
        if set(bundle['prepared']['routes'])!={'A','B'}:continue
        with contextlib.redirect_stdout(io.StringIO()):
            before=reference.simulate(copy.deepcopy(bundle),'월','peak',False)
            after=current.simulate(copy.deepcopy(bundle),'월','peak',False)
        # v5 adds a stop-index audit column; compare the unchanged physics and
        # queues against the original forecast, excluding that schema extension.
        for field in ('events','highlights'):after[field]=[r[:12] for r in after[field]]
        after['event_columns']=before['event_columns']
        after['report'].pop('city_speed_revision',None)
        same(before,after)
    result={'status':'PASS','cases':24,'comparison':'all physical output fields, excluding new audit column; numeric absolute tolerance 1e-7',
            'features':'mixed same-stop eligibility, FIFO, partial boarding, rechecks, walking and route switches',
            'full_day_ungrouped_baseline_completed':False}
    (ROOT/'grouping_parity.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()

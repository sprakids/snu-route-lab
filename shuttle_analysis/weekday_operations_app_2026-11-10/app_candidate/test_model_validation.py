import gzip,json,tempfile,sys,unittest
from pathlib import Path
from datetime import datetime,timedelta
from shuttle import KST
from crowd_model import CrowdModel
sys.path.insert(0,str(Path(__file__).parent.parent/'collector'))
from train_model import train,load

class ModelValidationTests(unittest.TestCase):
    def fixture(self,path,days,flip_test=False):
        records=[]
        for day in range(days):
            start=(datetime(2026,11,9,17,0,tzinfo=KST)+timedelta(days=day)).timestamp()
            for section in (1,2,3):
                at=start+(section-1)*60
                records.append({'at':at,'vehicles':[{'route_id':'100100250','id':str(v),'section_order':str(section),
                    'provided_at':at,'crowd_code':'5' if flip_test and day>=21 else '4'} for v in range(25)]})
        path.write_bytes(gzip.compress(('\n'.join(json.dumps(r) for r in records)+'\n').encode()))

    def test_insufficient_dates_never_activate_model(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'one.jsonl.gz';self.fixture(p,1);r=train([p])
            self.assertFalse(r['validation']['eligible'])

    def test_test_dates_do_not_change_training_or_tuned_decay(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.gz';b=Path(folder)/'b.gz';self.fixture(a,28);self.fixture(b,28,True)
            x,y=train([a]),train([b])
            self.assertEqual(x['cells'],y['cells']);self.assertEqual(x['pooled'],y['pooled'])
            self.assertEqual(x['features'],y['features']);self.assertEqual(x['tau_seconds'],y['tau_seconds'])
            self.assertEqual(len(x['validation']['test_dates']),7)
            self.assertFalse(x['validation']['eligible']) # A perfect persistence baseline must not be replaced.

    def test_unknown_grade_and_passenger_sums_are_not_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'unknown.gz'
            r={'at':datetime(2026,11,9,17,0,tzinfo=KST).timestamp(),'vehicles':[{'route_id':'r','id':'v','section_order':'1','provided_at':100,'crowd_code':'0','passenger_sum':1000}]}
            p.write_bytes(gzip.compress((json.dumps(r)+'\n').encode()));rows,days=load([p])
            self.assertEqual(rows,[]);self.assertEqual(len(days),1)

    def test_rejected_artifact_is_never_used_in_ranking(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.json';p.write_text(json.dumps({'schema':'ordinal_crowd_v1','validation':{'eligible':False}}))
            self.assertIsNone(CrowdModel(p).predict('r','1',100))

if __name__=='__main__':unittest.main()

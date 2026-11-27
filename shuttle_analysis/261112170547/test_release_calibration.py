"""Transform immutable source inputs without losing demand or moving before class end."""
import math,unittest
from artifacts import ROOT,read
from prepare import prepare
class ReleaseCalibration(unittest.TestCase):
    def test_full_friday_source_mass_class_clock_and_walk_factor(self):
        cfg=read(ROOT/'config.json');cfg.update(physics='path_local_4p8',behavior='sequential',origin_choice=False,operations='v12_empirical')
        alpha=cfg['cohort_release_lag_scale'];self.assertIn(alpha,(.5,.75,1.25,1.5))
        case=next(c for c in read(ROOT/'experiment_lock.json')['pilot_cases'] if c['day']=='금' and c['scenario']=='regular')
        source=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');raw={p[0]:p for p in source['prepared']['plans']['금']}
        meta=read(ROOT/'frozen/class_release_map.json.gz');b=prepare(case,cfg);new=b['prepared']['plans']['금']
        self.assertAlmostEqual(math.fsum(p[3] for p in new),math.fsum(p[3] for p in raw.values()),places=8)
        mass={}
        for p in new:
            parent=b['parent_ids'][str(p[0])];old=raw[parent];end=meta['events'][(parent-1)//48]['class_end_seconds']
            self.assertGreaterEqual(p[4],end);self.assertAlmostEqual(p[4],end+alpha*(old[4]-end))
            self.assertEqual(p[1:3],old[1:3]);self.assertEqual(p[5][0],old[5][0])
            factor=source['walk_scales'][str(parent)]
            self.assertAlmostEqual(p[5][1],b['physical_paths'][p[5][0]]['seconds']*factor)
            mass[parent]=mass.get(parent,0.)+p[3]
        self.assertEqual(set(mass),set(raw))
        self.assertLess(max(abs(mass[k]-raw[k][3]) for k in raw),1e-8)
        self.assertEqual(b['supply'],read(ROOT/'frozen/supply.json'))
        self.assertEqual(b['prepared']['common']['route_info'],source['prepared']['common']['route_info'])
if __name__=='__main__':unittest.main()

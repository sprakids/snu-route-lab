"""Regressions for late-arriving candidates and the shared observation API limit."""
import time
import unittest
from types import SimpleNamespace
from routing import Planner, PRESETS, distance


class TimeAwareSearchTests(unittest.TestCase):
    def planner(self):
        now=time.time();p=Planner.__new__(Planner)
        self.origin=(37.46,126.95);self.destination=(37.46,126.951)
        p.routes=[{'id':str(i),'name':str(i),'interval_minutes':7,'stops':[
            {'id':'start','seq':1,'name':'start','lat':self.origin[0],'lon':self.origin[1]},
            {'id':'end','seq':2,'name':'end','lat':self.destination[0],'lon':self.destination[1]}]} for i in range(51)]
        p.by_id={r['id']:r for r in p.routes};p.interchanges={};self.prefetched=[];self.ride_times=[]
        def walk(a,b):
            # A long pedestrian detour, while the vehicle has a direct road link.
            metres=distance(a,b)*30
            return {'seconds':round(metres/1.2),'meters':metres,'steps_m':0,'geometry':[list(a),list(b)]}
        p.walk=walk
        def ride(route,i,j,when,live):
            self.ride_times.append(when)
            return {'seconds':100 if route['id']=='50' else 5,'label':'fixture ride'}
        p.ride_estimate=ride
        def arrivals(route,index):
            # Cached ETAs can exist even when this search doesn't re-fetch them.
            if index:return []
            return [{'departure_at':now+(40 if route['id']=='50' else 900),'vehicle_id':route['id'],
                     'provided_at':now,'full':False,'crowd_cost':0,'crowd_label':'여유'}]
        p.transit=SimpleNamespace(now=lambda:now,prefetch=lambda pairs:self.prefetched.extend(pairs),
            arrivals=arrivals,in_service=lambda *args:True,notes=lambda:[])
        p.geometry=SimpleNamespace(leg=lambda *args:{'meters':100,'geometry':[list(self.origin),list(self.destination)]})
        p.routing_model={}
        return p,now

    def test_waiting_can_make_the_51st_rough_candidate_fastest(self):
        planner,now=self.planner()
        result=planner.plan(self.origin,self.destination,now,'live',PRESETS['fast'],False)
        best=min(result['candidates'],key=lambda c:c['total_seconds'])
        self.assertEqual(best['route_names'],['50'])
        self.assertEqual(best['total_seconds'],140)
        self.assertEqual(result['candidate_search']['patterns_evaluated'],51)
        self.assertFalse(result['candidate_search']['early_time_pruning'])
        self.assertLessEqual(len(result['candidates']),40)
        self.assertLessEqual(len(self.prefetched),16)

    def test_future_rough_order_uses_requested_time_and_can_skip_early_pruning(self):
        planner,now=self.planner();requested=now+18000
        patterns=planner.patterns(self.origin,self.destination,False,requested,unpruned=True)
        self.assertEqual(len(patterns),51)
        self.assertTrue(self.ride_times)
        self.assertEqual(set(self.ride_times),{requested})


if __name__=='__main__':unittest.main()

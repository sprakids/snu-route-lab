import json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from adaptive import POLICY,decision,fifo_departure,queue_input,queue_arrivals,validate_context
from gate_service import uniform_first
from shuttle_timetable import KST,ShuttleTimetable
from routing import PRESETS
import server

def stamp(value):return datetime.fromisoformat(value).replace(tzinfo=KST).timestamp()
def candidate(key,seconds):
    rid,sid=key.split(':') if ':' in key else ('','')
    return {'id':key,'total_seconds':seconds,'crowd_risk':3.,'legs':[{'type':'bus','route_id':rid,'station_id':sid}] if rid else []}

class DecisionTests(unittest.TestCase):
    def setUp(self):self.now=10000.;self.context={'current_key':'shuttle-1:stop','switch_count':0,'last_switch_at':None,'abandoned_keys':[]}
    def run_decision(self,gain,**updates):
        return decision([candidate('shuttle-1:stop',1000),candidate('other:stop',1000-gain)],{**self.context,**updates},self.now)
    def test_119_seconds_keeps_and_120_seconds_suggests(self):
        self.assertEqual(self.run_decision(119)['reason'],'small_gain')
        self.assertEqual(self.run_decision(120)['action'],'suggest_switch')
    def test_cooldown_and_maximum_switches(self):
        self.assertEqual(self.run_decision(600,last_switch_at=self.now-179)['reason'],'cooldown')
        self.assertEqual(self.run_decision(600,last_switch_at=self.now-180)['action'],'suggest_switch')
        self.assertEqual(self.run_decision(600,switch_count=2)['reason'],'switch_limit')
    def test_abandoned_stop_not_recommended_and_elapsed_wait_not_readded(self):
        x=self.run_decision(500,abandoned_keys=['other:stop'],started_at=self.now-3600)
        self.assertEqual(x['recommended_candidate_id'],'shuttle-1:stop')
        self.assertEqual(x['remaining_seconds_current'],1000)
    def test_missing_current_is_explicit_and_context_rejects_invalid_numbers(self):
        self.assertEqual(decision([candidate('other:stop',200)],self.context,self.now)['reason'],'current_unavailable')
        for bad in ({**self.context,'switch_count':3},{**self.context,'last_switch_at':float('nan')}):
            with self.assertRaises(ValueError):validate_context(bad,self.now)
    def test_uniform_common_service_integral_and_probabilities(self):
        wait,p=uniform_first([600.]*5)
        self.assertAlmostEqual(wait,100.);self.assertTrue(all(abs(v-.2)<1e-9 for v in p))
        wait,p=uniform_first([420,540,540,720,600]);self.assertLess(wait,210);self.assertAlmostEqual(sum(p),1.)
    def test_fifo_full_departure_does_not_clear_the_queue(self):
        rows=[{'departure_at':100,'seats_available':60,'full':True},
              {'departure_at':200,'seats_available':25},{'departure_at':300,'seats_available':60}]
        chosen,passed,full=fifo_departure(rows,99,30)
        self.assertEqual((chosen['departure_at'],passed,full),(300,2,1))
        self.assertIsNone(fifo_departure(rows,99,100)[0])
    def test_queue_input_expires_and_cannot_claim_provider_observation(self):
        value={'route_id':'shuttle-41914','station_id':'snu-901','reported_at':self.now-91,'queue_ahead':20,'source':'observed','opportunity_departure_at':self.now+100}
        self.assertIsNone(queue_input(value,self.now));value['reported_at']=self.now
        self.assertEqual(queue_input(value,self.now)['source'],'user_report')
        value['queue_ahead']=float('nan')
        with self.assertRaises(ValueError):queue_input(value,self.now)
    def test_first_opportunity_passes_before_90_seconds_and_invalidates_all_inputs(self):
        value={'route_id':'shuttle-41914','station_id':'snu-901','reported_at':self.now-60,'queue_ahead':20,
               'next_full':True,'opportunity_departure_at':self.now-1,'opportunity_vehicle_id':'first'}
        self.assertIsNone(queue_input(value,self.now))
    def test_reference_means_are_reproduced_as_display_only(self):
        from prepare_adaptive_policy import build
        with tempfile.TemporaryDirectory() as temp:
            x=build(target=Path(temp)/'reference.json')
        self.assertTrue(x['display_only']);self.assertEqual(x['eta_adjustment_seconds'],0)
        peak=next(r for r in x['summaries'] if r['scenario']=='peak' and r['origin']=='all' and r['scope']=='snu_all')
        self.assertAlmostEqual(peak['wait_before'],5.1242740732);self.assertAlmostEqual(peak['total_after'],19.7123654209)

class PlannerAdaptiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=server.Application()
    def setUp(self):
        self.now=stamp('2026-11-09T16:00:00')
        self.clock=patch('time.time',return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)
        self.network=patch('urllib.request.urlopen',side_effect=AssertionError('No external API in adaptive tests'));self.mock_net=self.network.start();self.addCleanup(self.network.stop)
        t=self.app.transit;t.prefetch=lambda pairs:None;t.arrivals=lambda r,i:[];t.shuttle.refresh=lambda:t.shuttle.status()
        t.snapshot={};t.plan_snapshot={};t.history_snapshot={}
    def run_plan(self,report=None,origin=None,shuttles=True):
        point=origin or self.app.stops.get('snu-410') or next(s for r in self.app.transit.shuttle.routes for s in r['stops'] if s['id']=='snu-410')
        target=self.app.destinations[0]
        x=self.app.planner.plan((point['lat'],point['lon']),(target['lat'],target['lon']),self.now,'live',PRESETS['fast'],shuttles,report)
        self.app.historical.attach(x,self.app.planner);self.assertEqual(self.mock_net.call_count,0)
        return x
    def test_queue_report_replaces_hourly_extra_and_retains_missed_departures(self):
        report=queue_input({'route_id':'shuttle-41841','station_id':'snu-410','reported_at':self.now,'queue_ahead':60,'next_seats':0,
                           'opportunity_departure_at':self.now+140},self.now)
        x=self.run_plan(report)
        legs=[l for c in x['candidates'] for l in c['legs'] if l.get('queue_projection')]
        self.assertTrue(legs)
        for leg in legs:
            self.assertEqual(leg['arrival_source'],'shuttle_queue_estimate');self.assertIsNone(leg['vehicle_id'])
            q=leg['queue_projection'];self.assertEqual(q['skipped_departures'],2);self.assertEqual(q['capacity_assumption'],60)
            self.assertNotIn('queue_model',leg['arrival_options'][0]);self.assertFalse(q['observed_queue'])
            self.assertAlmostEqual(leg['departure_at']-leg['ready_at'],600,delta=2)
    def test_reverse_uses_25_seats_and_no_after_last_bus(self):
        route=self.app.transit.shuttle.routes[2];table=ShuttleTimetable(self.app.transit.geometry,use_queue=False)
        report={'queue_ahead':25,'next_seats':None,'next_full':False,'reported_at':self.now,'party_weight':1}
        rows=queue_arrivals(route,0,self.now,[],report,table,self.now)
        self.assertEqual(rows[0]['queue_projection']['capacity_assumption'],25)
        self.assertEqual(rows[0]['queue_projection']['skipped_departures'],1)
        self.assertEqual(rows[0]['departure_at'],stamp('2026-11-09T16:30:00'))
        self.assertEqual(queue_arrivals(route,0,stamp('2026-11-09T17:09:00'),[],report,table,self.now),[])
    def test_common_gate_picks_first_observed_feasible_bus_and_keeps_identity(self):
        from strategies import GATE_STOP
        def arrivals(r,i):
            if r['stops'][i]['id']!=GATE_STOP:return []
            offset=30 if r['name']=='5513' else 60
            return [{'departure_at':self.now+offset,'provided_at':self.now,'vehicle_id':r['id'],'full':False,'crowd_cost':0,'crowd_label':'여유'}]
        self.app.transit.arrivals=arrivals
        # Identity is retained when the conditional FIFO queue adds no delay.
        # Positive queue delays and cleared vehicle IDs are tested separately.
        with patch('city_wait.profile',return_value={'available':True,'extra_wait_seconds':0,'reference_headway_seconds':600}):
            x=self.run_plan(origin=self.app.stops[GATE_STOP],shuttles=False)
        common=next(c for c in x['candidates'] if c.get('common_gate_service'))
        self.assertEqual(common['common_gate_service']['kind'],'first_observed_boardable_bus')
        self.assertEqual(common['route_names'],['5513']);self.assertEqual(common['legs'][3]['vehicle_id'],'100100251')
    def test_unknown_common_service_has_no_fake_vehicle_or_single_route_load(self):
        x=self.run_plan();common=next(c for c in x['candidates'] if c.get('common_gate_service'))
        bus=next(l for l in common['legs'] if l['type']=='bus')
        self.assertEqual(bus['arrival_source'],'pooled_headway_estimate');self.assertIsNone(bus['vehicle_id'])
        self.assertEqual(len(common['common_gate_service']['eligible_route_ids']),5)
        self.assertFalse(common['historical_forecast']['available']);self.assertEqual(len(common['historical_demand']['route_details']),5)
        for c in x['candidates']:self.assertEqual(c['total_seconds'],sum(c[k] for k in ('walk_seconds','wait_seconds','ride_seconds','boarding_seconds')))
    def test_report_does_not_rebind_full_flag_to_a_different_live_vehicle(self):
        route=self.app.transit.shuttle.routes[0];i=next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410')
        report={'queue_ahead':20,'next_seats':0,'next_full':True,'reported_at':self.now,'party_weight':1,
                'opportunity_departure_at':self.now+80,'opportunity_vehicle_id':'original'}
        observed=[{'departure_at':self.now+60,'vehicle_id':'different','arrival_source':'live_shuttle'}]
        self.assertIsNone(queue_arrivals(route,i,self.now+20,observed,report,self.app.transit.shuttle.timetable,self.now))
    def test_schedule_opportunity_does_not_drift_at_60_second_recheck(self):
        route=self.app.transit.shuttle.routes[0];i=next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410')
        report={'queue_ahead':0,'next_seats':1,'next_full':False,'reported_at':self.now,'party_weight':1,
                'opportunity_departure_at':self.now+140,'opportunity_vehicle_id':None}
        first=queue_arrivals(route,i,self.now+20,[],report,self.app.transit.shuttle.timetable,self.now)[0]
        later=queue_arrivals(route,i,self.now+60,[],report,self.app.transit.shuttle.timetable,self.now+60)[0]
        self.assertEqual(first['departure_at'],later['departure_at'])
    def test_fresh_available_seats_are_used_before_nominal_capacity(self):
        route=self.app.transit.shuttle.routes[0];i=next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410')
        report={'queue_ahead':3,'next_seats':None,'next_full':False,'reported_at':self.now,'party_weight':1,
                'opportunity_departure_at':self.now+60,'opportunity_vehicle_id':'first'}
        observed=[{'departure_at':self.now+60,'vehicle_id':'first','seats_available':2,'provided_at':self.now,'arrival_source':'live_shuttle'},
                  {'departure_at':self.now+120,'vehicle_id':'second','seats_available':4,'provided_at':self.now,'arrival_source':'live_shuttle'}]
        result=queue_arrivals(route,i,self.now+20,observed,report,self.app.transit.shuttle.timetable,self.now)[0]
        self.assertEqual(result['departure_at'],self.now+120)
        self.assertEqual(result['queue_projection']['skipped_departures'],1)
        self.assertEqual(result['queue_projection']['seat_sources'],['fresh_available_seats_observation']*2)
    def test_recheck_does_not_repeat_already_completed_boarding_preparation(self):
        point=next(s for r in self.app.transit.shuttle.routes for s in r['stops'] if s['id']=='snu-410')
        target=self.app.destinations[0];ctx={'current_key':'shuttle-41841:snu-410','waiting_since':self.now-60,'abandoned_keys':[]}
        x=self.app.planner.plan((point['lat'],point['lon']),(target['lat'],target['lon']),self.now,'live',PRESETS['fast'],True,None,ctx)
        keep=[c for c in x['candidates'] if c['continuation_key']==ctx['current_key']]
        self.assertTrue(keep)
        self.assertTrue(all(next(l for l in c['legs'] if l['type']=='board')['seconds']==0 for c in keep))
    def test_user_queue_report_does_not_leak_to_next_request_or_normal_error_cohort(self):
        body={'origin_id':'snu-410','destination_id':'snu-station','departure_at':self.now,'mode':'live','preset':'fast'}
        before=self.app.plan(body)
        report={'route_id':'shuttle-41841','station_id':'snu-410','reported_at':self.now,'queue_ahead':60,'next_seats':0,
                'opportunity_departure_at':self.now+140}
        with_report=self.app.plan({**body,'queue_context':report})
        after=self.app.plan(body)
        self.assertTrue(with_report['queue_report_applied']);self.assertFalse(after['queue_report_applied'])
        regular={c['id']:c for c in before['candidates']}
        for c in with_report['candidates']:
            if any(l.get('queue_projection') for l in c['legs']):self.assertNotEqual(c['observation_key'],regular[c['id']]['observation_key'])
        self.assertEqual({c['id']:c['total_seconds'] for c in before['candidates']},{c['id']:c['total_seconds'] for c in after['candidates']})

if __name__=='__main__':unittest.main()

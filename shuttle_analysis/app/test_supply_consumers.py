"""Active-release capacities in manual FIFO, fallback and reported opportunities."""
import copy
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import server
from adaptive import POLICY,queue_arrivals,queue_input
from automatic_queue import AutomaticQueue
from shuttle_timetable import KST


def stamp(text):return datetime.fromisoformat(text).replace(tzinfo=KST).timestamp()


class SupplyConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application()
        cls.seed=json.loads((Path(__file__).parent/'data/auto_queue_inputs.json').read_bytes())

    def setUp(self):
        self.now=stamp('2026-11-10T16:00:00')
        clock=patch('time.time',return_value=self.now);clock.start();self.addCleanup(clock.stop)
        network=patch('urllib.request.urlopen',side_effect=AssertionError('No provider API for capacity'));self.network=network.start();self.addCleanup(network.stop)

    def route(self,provider):return next(r for r in self.app.transit.shuttle.routes if r['provider_id']==provider)

    def admin_index(self,route):return next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410' and s['board_allowed'])

    def model(self,updated=True,pair=True):
        data=copy.deepcopy(self.seed)
        if updated:
            route=data['routes']['shuttle-41841']
            route.update(capacity=44,capacity_periods=[{'start_second':75600,'capacity':60}])
            if pair:route['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
            data['model']['id']='261110160000'
        return AutomaticQueue(self.app.historical,data=data)

    def test_active_day_night_and_other_route_capacities(self):
        for updated,expected in ((False,60),(True,44)):
            model=self.model(updated)
            for provider,at,capacity in [('41841',self.now,expected),('41915',stamp('2026-11-10T21:10:00'),60),('41946',self.now,60),('41914',self.now,25)]:
                route=self.route(provider);index=self.admin_index(route) if provider in ('41841','41915') else 0
                row=model.with_vehicle_supply(route,index,{'departure_at':at})
                self.assertEqual(row['vehicle_supply']['capacity'],capacity)

    def test_same_vehicle_keeps_dispatch_capacity_after_eta_crosses_21(self):
        route=self.route('41841');index=self.admin_index(route);model=self.model()
        row=model.with_vehicle_supply(route,index,{'departure_at':stamp('2026-11-10T20:59:00')})
        shifted={**row,'departure_at':stamp('2026-11-10T21:01:00')}
        value=model.with_vehicle_supply(route,index,shifted)
        self.assertEqual(value['vehicle_supply']['capacity'],44)
        self.assertEqual(value['vehicle_supply']['terminal_dispatch_at'],stamp('2026-11-10T20:59:00'))
        night=self.route('41915')
        self.assertEqual(model.with_vehicle_supply(night,self.admin_index(night),{'departure_at':stamp('2026-11-10T21:10:00')})['vehicle_supply']['capacity'],60)

    def test_manual_queue_uses_two_individual_44_seat_vehicles(self):
        route=self.route('41841');index=self.admin_index(route)
        report={'queue_ahead':66,'next_seats':None,'next_full':False,'reported_at':self.now,'party_weight':1}
        old=queue_arrivals(route,index,self.now,[],report,self.app.transit.shuttle.timetable,self.now,capacity_model=self.model(False))
        new=queue_arrivals(route,index,self.now,[],report,self.app.transit.shuttle.timetable,self.now,capacity_model=self.model())
        self.assertEqual(old[0]['queue_projection']['capacity_assumption'],60)
        self.assertEqual(new[0]['queue_projection']['capacity_assumption'],44)
        self.assertEqual(new[0]['queue_projection']['skipped_departures'],1)
        self.assertLess(new[0]['departure_at'],old[0]['departure_at'])
        self.assertEqual(new[0]['batch_member'],1)
        self.assertEqual(new[0]['vehicle_supply']['batch_vehicles'],2)
        self.assertEqual(route['capacity'],60)  # Never mutate the shared catalogue.

    def test_next_seat_report_is_bounded_by_selected_vehicle_capacity(self):
        route=self.route('41841');index=self.admin_index(route)
        report={'queue_ahead':44,'next_seats':60,'next_full':False,'reported_at':self.now,'party_weight':1}
        result=queue_arrivals(route,index,self.now,[],report,self.app.transit.shuttle.timetable,self.now,capacity_model=self.model())
        self.assertEqual(result[0]['batch_member'],1)
        self.assertEqual(result[0]['queue_projection']['capacity_assumption'],44)

    def test_real_individual_vehicles_are_not_doubled_by_batch_assumption(self):
        route=self.route('41841');index=self.admin_index(route)
        observed=[{'departure_at':self.now+120,'arrival_source':'live_shuttle','vehicle_id':name,
                   'provided_at':self.now,'seats_available':44} for name in ('one','two')]
        report={'queue_ahead':88,'next_seats':None,'next_full':False,'reported_at':self.now,'party_weight':1}
        result=queue_arrivals(route,index,self.now,observed,report,self.app.transit.shuttle.timetable,self.now,capacity_model=self.model())
        self.assertGreater(result[0]['departure_at'],self.now+120)
        self.assertEqual(result[0]['queue_projection']['skipped_departures'],2)

    def test_retained_report_clock_is_not_replaced_by_new_eta_or_query_time(self):
        route=self.route('41841');index=self.admin_index(route);model=self.model()
        terminal=stamp('2026-11-10T20:59:00');eta=stamp('2026-11-10T21:01:00')
        observed=[{'departure_at':eta,'arrival_source':'live_shuttle','vehicle_id':'same','provided_at':eta-30}]
        report={'queue_ahead':0,'next_seats':60,'next_full':False,'reported_at':eta-30,'party_weight':1,
                'opportunity_departure_at':eta,'opportunity_vehicle_id':'same','opportunity_terminal_dispatch_at':terminal}
        class LastVehicle:
            def _schedule_arrival(self,*args):return None
        result=queue_arrivals(route,index,eta-20,observed,report,LastVehicle(),eta-30,capacity_model=model)
        self.assertEqual(result[0]['vehicle_supply']['capacity'],44)
        self.assertEqual(result[0]['vehicle_supply']['terminal_dispatch_at'],terminal)
        self.assertEqual(result[0]['seats_available'],44)

    def test_optional_terminal_input_must_be_finite_and_bounded(self):
        value={'route_id':'shuttle-41841','station_id':'snu-410','reported_at':self.now,'queue_ahead':1,
               'opportunity_departure_at':self.now+100,'opportunity_terminal_dispatch_at':self.now+100}
        self.assertEqual(queue_input(value,self.now)['opportunity_terminal_dispatch_at'],self.now+100)
        for bad in (True,float('nan'),float('inf'),self.now-86401,self.now+21601):
            with self.subTest(bad=bad),self.assertRaises(ValueError):queue_input({**value,'opportunity_terminal_dispatch_at':bad},self.now)

    def test_new_supply_skips_old_60_seat_hourly_delay_but_legacy_keeps_it(self):
        service=self.app.transit.shuttle;route=self.route('41841');index=self.admin_index(route)
        for updated in (False,True):
            model=self.model(updated)
            with patch.object(self.app.transit,'automatic_queue',model),patch.object(service.timetable,'arrival',wraps=service.timetable.arrival) as legacy:
                values=service.scheduled_arrivals(route,index,self.now)
            self.assertTrue(values)
            self.assertEqual(legacy.call_count,0 if updated else 1)
            self.assertEqual(values[0]['vehicle_supply']['capacity'],44 if updated else 60)
            if updated:self.assertNotIn('queue_model',values[0])

    def test_planner_exposes_next_opportunity_capacity_without_extra_api_calls(self):
        app=self.app;model=self.model();point=next(s for s in self.route('41841')['stops'] if s['id']=='snu-410');destination=app.destinations[0]
        with patch.object(app.transit,'automatic_queue',model),patch.object(app.transit,'prefetch',return_value=None),patch.object(app.transit,'arrivals',return_value=[]):
            result=app.planner.plan((point['lat'],point['lon']),(destination['lat'],destination['lon']),self.now,'live',server.PRESETS['fast'],True)
        legs=[l for c in result['candidates'] for l in c['legs'] if l.get('route_id')=='shuttle-41841']
        self.assertTrue(legs)
        for leg in legs:self.assertEqual(leg['queue_report_opportunity']['vehicle_supply']['capacity'],44)
        self.assertEqual(self.network.call_count,0)
        self.assertEqual(POLICY['max_switches'],2)


if __name__=='__main__':unittest.main()

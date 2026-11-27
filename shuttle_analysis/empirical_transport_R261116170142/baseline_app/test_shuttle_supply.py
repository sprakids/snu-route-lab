"""Supply regression: original dispatch clocks, separate vehicles and pinned data."""
import copy
import importlib.util
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from automatic_queue import AutomaticQueue,simulate,queue_at
from shuttle_supply import capacity_at,copy_settings,validate as validate_supply,vehicles
from queue_release import compatibility,accepted_compatibilities,validate
from shuttle_timetable import KST

ROOT=Path(__file__).parent


def route():
    return {'id':'shuttle-41841','capacity':44,
        'capacity_periods':[{'start_second':75600,'capacity':60}],
        'n':2,'loop':False,'anchor':0,'offsets':[0,120],
        'stops':[{'board_allowed':True},{'board_allowed':True}],
        'ready_packets':[],'flows':[],'od':{}}


def upgraded(data,pair=False):
    result=copy.deepcopy(data);r=result['routes']['shuttle-41841']
    r.update(capacity=44,capacity_periods=[{'start_second':75600,'capacity':60}])
    if pair:r['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
    return result


class ShuttleSupplyTests(unittest.TestCase):
    def test_capacity_uses_original_terminal_clock_across_night_boundary(self):
        r=route()
        with patch('automatic_queue.dispatches',return_value=[75540,75600]):
            p=simulate(r,0,0,1,0,lambda i,t:1)
        self.assertEqual([v['capacity'] for v in p['supply'][0]],[44,60])
        # First vehicle crosses 21:00 en route without gaining 16 seats.
        self.assertEqual(p['supply'][1][0]['at'],75660)
        self.assertEqual(p['supply'][1][0]['capacity'],44)
        self.assertEqual(p['supply'][1][0]['terminal_dispatch_second'],75540)
        self.assertEqual(capacity_at(r,75600),60)

    def test_two_vehicles_retain_separate_caps_and_upstream_loads(self):
        r=route();r['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
        r['ready_packets']=[[0,0,53970,60,None],[0,1,53970,50,None]]
        r['od']={'0:0':[[2,1.]],'0:1':[[1,1.]]}
        with patch('automatic_queue.dispatches',return_value=[54000]):
            p=simulate(r,0,0,1,0,lambda i,t:1)
        self.assertEqual([v['capacity'] for v in p['supply'][0]],[44,44])
        self.assertEqual([v['vehicle'] for v in p['supply'][0]],[0,1])
        self.assertEqual([v['at'] for v in p['supply'][0]],[54000,54000])
        self.assertEqual([v['free'] for v in p['supply'][1]],[0,28])
        self.assertEqual(queue_at(p,1,54121),22)
        self.assertEqual(p['input_mass'],110)
        self.assertEqual(p['boarded_mass'],88)
        self.assertEqual(p['remaining_mass'],22)
        self.assertEqual(p['max_capacity_excess'],0)
        self.assertEqual(p['max_load'],44)

    def test_67_people_are_served_by_pair_but_not_one_bus(self):
        r=route();r['ready_packets']=[[0,0,53970,67,None]]
        with patch('automatic_queue.dispatches',return_value=[54000]):
            single=simulate(r,0,0,1,0,lambda i,t:1)
            r['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
            pair=simulate(r,0,0,1,0,lambda i,t:1)
        self.assertEqual(single['remaining_mass'],23)
        self.assertEqual(pair['remaining_mass'],0)
        self.assertEqual(pair['max_load'],44)

    def test_batch_window_is_end_exclusive_and_reserve_is_per_vehicle(self):
        r=route();r['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
        fleet=list(vehicles(r,[53999,54000,68399,68400,75600]))
        self.assertEqual([v['terminal_dispatch_second'] for v in fleet],
                         [53999,54000,54000,68399,68399,68400,75600])
        with patch('automatic_queue.dispatches',return_value=[54000,75600]):
            p=simulate(r,0,0,1,.1,lambda i,t:1)
        for row in p['supply'][0]:
            self.assertAlmostEqual(row['free'],row['capacity']*.9)
        self.assertEqual([r['capacity'] for r in p['supply'][0]],[44,44,60])

    def test_copying_source_does_not_mutate_source_or_retain_stale_batches(self):
        target=route();target['dispatch_batches']=[{'start_second':0,'end_second':100,'vehicles':2}]
        source={'capacity':60};copy_settings(target,source)
        self.assertNotIn('capacity_periods',target);self.assertNotIn('dispatch_batches',target)
        self.assertEqual(source,{'capacity':60})

    def test_invalid_supply_and_alias_override_are_rejected(self):
        bad=[{'capacity':True},{'capacity':0},{'capacity':float('inf')},
            {'capacity_periods':[]},{'capacity_periods':[{'start_second':75600,'capacity':44,'source':'ignored'}]},
            {'capacity_periods':[{'start_second':75600,'capacity':60},{'start_second':75600,'capacity':44}]},
            {'capacity_periods':[{'start_second':-1,'capacity':44}]},
            {'dispatch_batches':[{'start_second':100,'end_second':100,'vehicles':2}]},
            {'dispatch_batches':[{'start_second':100,'end_second':200,'vehicles':True}]},
            {'dispatch_batches':[{'start_second':100,'end_second':200,'vehicles':2},{'start_second':150,'end_second':300,'vehicles':2}]},
            {'profile_route_id':'primary'}]
        for mutation in bad:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_supply({**route(),**mutation})


class PublishedSupplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.seed=json.loads((ROOT/'data/auto_queue_inputs.json').read_bytes())

    def test_scalar_legacy_hash_and_payload_remain_unchanged(self):
        before=copy.deepcopy(self.seed)
        spec=importlib.util.spec_from_file_location('legacy_queue_contract',ROOT/'test_fixtures/queue_release_v3_contract.py')
        legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
        self.assertEqual(compatibility(self.seed),legacy.compatibility(self.seed))
        accepted_compatibilities(self.seed)
        self.assertEqual(self.seed,before)

    def test_upgrade_allowlist_accepts_only_approved_two_supply_contracts(self):
        allowed=accepted_compatibilities(self.seed)
        self.assertEqual(len(allowed),3)
        for pair in (False,True):self.assertIn(compatibility(upgraded(self.seed,pair)),allowed)
        for mutation in (lambda d:d['routes']['shuttle-41946'].update(capacity=44),
                         lambda d:d['routes']['shuttle-41841']['capacity_periods'][0].update(start_second=75599),
                         lambda d:d['routes']['shuttle-41841']['dispatch_batches'][0].update(vehicles=3),
                         lambda d:d['routes']['shuttle-41841']['dispatch_batches'][0].update(end_second=68401),
                         lambda d:d['routes']['shuttle-41841']['offsets'].__setitem__(0,999)):
            data=upgraded(self.seed,True);mutation(data)
            self.assertNotIn(compatibility(data),allowed)

    def test_profile_validation_preserves_capacity_mass_and_exit_checks(self):
        data=upgraded(self.seed,True)
        validate(data,compatibility(data),check_profiles=True)
        invalid=copy.deepcopy(data)
        invalid['routes']['shuttle-41841']['ready_packets']=[[0,1,50000,1,49999]]
        with self.assertRaises(ValueError):validate(invalid,compatibility(invalid))

    def test_alias_and_live_shift_use_selected_vehicle_capacity(self):
        import server
        app=server.Application();service=app.transit.shuttle
        model=AutomaticQueue(None,data=upgraded(self.seed))
        for rid,text,cap,scheduled in (
            ('shuttle-41841','2026-11-09T16:00:00',44,75540),
            ('shuttle-41915','2026-11-09T21:11:00',60,76200)):
            r=next(r for r in service.routes if r['id']==rid)
            i=next(i for i,s in enumerate(r['stops']) if s['id']=='snu-410' and s['board_allowed'])
            primary=model.data['routes']['shuttle-41841'];n=primary['n']
            mid=datetime(2026,11,9,tzinfo=KST).timestamp();ready=datetime.fromisoformat(text).replace(tzinfo=KST).timestamp()
            rows=[[] for _ in range(n)];rows[1]=[{'at':ready-mid+120,'free':cap,'capacity':cap,
                                               'terminal_dispatch_second':scheduled}]
            profile={'scenario':{'demand':1},'keys':[[] for _ in range(n)],'values':[[] for _ in range(n)],'supply':rows}
            real=[{'arrival_source':'live_shuttle','departure_at':ready+125,'earliest_departure_at':ready+125,
                   'provided_at':ready,'clock_conditioning_verified':True}]
            with patch.object(model,'profiles',return_value=([profile],[[] for _ in range(n)],mid)):
                result=model.arrival(r,i,ready,real,service.timetable,ready,{},True)
            self.assertTrue(result)
            forecast=result[0]['automatic_queue']
            self.assertEqual(forecast['capacity_assumption'],cap)
            self.assertEqual(forecast['capacity_assumption_range'],[cap,cap])
            self.assertEqual(forecast['capacity_basis'],'selected_vehicle_original_terminal_dispatch')


if __name__=='__main__':unittest.main()

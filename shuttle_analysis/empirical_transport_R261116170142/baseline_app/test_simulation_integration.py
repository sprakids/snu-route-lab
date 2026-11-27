import copy,hashlib,json,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from simulation_kernel import kinematic_profile,first_boardable,ride_seconds
from simulation_travel import SimulationTravel,modeled_speed_seconds,fifo_opportunity
from shuttle_timetable import KST,ShuttleTimetable
from travel_time import TravelTime
import server

ROOT=Path(__file__).parent

class SimulationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application();cls.model=cls.app.planner.travel.simulation
        cls.fixtures=json.loads((ROOT/'test_fixtures/simulation_kernel.json').read_text(encoding='utf-8'))

    def test_vendored_bytes_and_all_354_source_service_segments_match(self):
        p=json.loads((ROOT/'data/simulation_provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256((ROOT/'simulation_kernel.py').read_bytes()).hexdigest(),p['kernel_sha256'])
        self.assertEqual(self.model.sha256,p['input_sha256'])
        count=0
        for rid,route in self.model.data['routes'].items():
            for row in route['segments']:
                self.assertAlmostEqual(ride_seconds(self.model.data,rid,row['from_index'],row['to_index']),row['model_seconds'],places=7);count+=1
        self.assertEqual(count,354)

    def test_motion_and_fifo_fixtures_reproduce_source_without_mutating_inputs(self):
        for case in self.fixtures['profile_cases']:
            result=kinematic_profile(case['points'],case['cuts'],self.model.data['campus_polygon'],case['force_campus'])
            self.assertAlmostEqual(result['duration'],case['expected_kinematic_seconds'],places=5)
            self.assertEqual(result['dwell_seconds'],15*len(case['cuts']))
        for case in self.fixtures['queue_cases']:
            args=[case[k] for k in ('rows','vehicles')]+[0.,0.,case['stage'],case['weight'],case['waiting']]
            before=copy.deepcopy(args);out=first_boardable(*args)
            self.assertEqual(out[0],case['expected']);self.assertEqual(args,before)

    def test_only_351_identical_directed_road_segments_are_mapped(self):
        coverage=self.model.info(self.app.planner.routes)['coverage']
        self.assertEqual(sum(r['mapped_segments'] for r in coverage.values()),351)
        for rid in ('100100252','100100263','100100521'):self.assertEqual(coverage[rid]['mapped_segments'],4)
        route=self.app.planner.by_id['100100250'];changed=copy.deepcopy(route)
        changed['stops'][0]['seq']=999
        self.assertIsNone(self.model.segment(changed,0))
        changed['stops'][0]['seq']=route['stops'][0]['seq'];changed['stops'][1]['id']='wrong-direction'
        self.assertIsNone(self.model.segment(changed,0))
        geometry=copy.deepcopy(self.model.geometry);geometry.routes[route['id']]['segments'][0]['meters']+=100
        self.assertIsNone(SimulationTravel(geometry).segment(route,0))

    def test_shuttle_ride_queue_and_reverse_terminal_clock_share_exact_offsets(self):
        at=datetime(2026,11,9,16,tzinfo=KST).timestamp()
        table=ShuttleTimetable(self.app.transit.geometry,use_queue=False)
        for route in self.app.transit.shuttle.routes:
            if route['id'] not in ('shuttle-41841','shuttle-41946','shuttle-41914'):
                self.assertIsNone(self.model.offsets(route))
                continue
            offsets=self.model.offsets(route);stored=self.app.transit.automatic_queue.data['routes'][route['id']]['offsets']
            self.assertEqual(offsets,stored)
            for k in range(1,len(route['stops'])):
                value=self.app.planner.travel.estimate(route,k-1,k,at)
                self.assertEqual(value['seconds'],round(offsets[k]-offsets[k-1]))
                self.assertEqual(value['model_id'],self.model.model_id)
        reverse=self.app.transit.shuttle.routes[2];offset=self.model.leg_seconds(reverse,0,2)
        clock=table._schedule_arrival(reverse,2,at)['departure_at']
        self.assertAlmostEqual(clock,datetime(2026,11,9,16,10,tzinfo=KST).timestamp()+round(offset),delta=1)
        q=self.app.transit.automatic_queue
        self.assertEqual(q.data['source_sha256']['travel_clock'],self.model.sha256)

    def test_completed_observations_and_current_speeds_bypass_scenario_floor(self):
        route=self.app.planner.by_id['100100250'];at=1794182400.
        pair=f"{route['id']}:{route['stops'][0]['seq']}:{route['stops'][1]['seq']}"
        observed={'n':6,'days':2,'median_seconds':12,'p10_seconds':10,'p90_seconds':14}
        result=self.app.planner.travel.estimate(route,0,1,at,{'travel_history':{pair:observed}},True)
        self.assertEqual(result['seconds'],12);self.assertEqual(result['source'],'measured_history')
        seq=str(route['stops'][1]['seq'])
        with patch('travel_time.time.time',return_value=at):
            snap={'traffic':{route['id']:{'fetched_at':at,'sections':{seq:{'speed_kmh':80}}}}}
            result=self.app.planner.travel.estimate(route,0,1,at,snap,True)
        self.assertEqual(result['source'],'current_section_speed')
        self.assertLess(result['seconds'],self.model.segment(route,0)['kinematic_seconds'])
        segment=self.model.segment(route,0)
        self.assertEqual(modeled_speed_seconds(segment,80),segment['kinematic_seconds'])
        self.assertAlmostEqual(modeled_speed_seconds(segment,5),segment['meters']/(5/3.6))

    def test_fifo_does_not_reuse_missed_services_or_invent_future_capacity(self):
        rows=[{'departure_at':99,'seats_available':100},
              {'departure_at':100,'seats_available':5,'full':True},
              {'departure_at':200,'seats_available':2.5},{'departure_at':300,'seats_available':4}]
        before=copy.deepcopy(rows)
        selected,passed,full=fifo_opportunity(rows,100,3.)
        self.assertEqual((selected['departure_at'],passed,full),(300,2,1));self.assertEqual(rows,before)
        self.assertIsNone(fifo_opportunity(rows,100,10.)[0])

    def test_queue_update_uses_latest_audited_conditional_inflow_and_od(self):
        # The model version must change when only vehicle clocks are updated.
        q=self.app.transit.automatic_queue
        self.assertRegex(q.config['id'],r'^[0-9]{12}$')
        self.assertEqual(q.config['algorithm_id'],'latest-v5-all-shuttle-clock-fifo-v3')
        self.assertEqual(sum(len(q.data['routes'][rid]['ready_flows']) for rid in ('shuttle-41841','shuttle-41946','shuttle-41914')),12537)
        self.assertEqual(len(q.data['routes']['shuttle-41843']['ready_flows']),4781)
        self.assertFalse(q.info()['calibrated']);self.assertFalse(q.info()['observed_queue'])

if __name__=='__main__':unittest.main()

"""Defined for the owning agent to run; synthetic geometry and physical FIFO.

These tests do not consume a new observed date or create production output.
"""
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artifacts import START, END, read
from fares import FareLedger
from fixtures import fixture
from physics import distance
from preferences import traits
from walking_opportunities import WalkingOpportunities, follows
import engine


def walking_fixture(weight=1., arrivals=None, factor=1., older_weight=0., capacity=2., departure=START):
    cfg={'behavior':'sequential','origin_choice':False,'student_strategy':True,'operations':'baseline',
         'boarding_choice':False,'complete_same_stop_pool':False,
         'preparation_seconds':20.,'forecast_committed_arrivals':True,
         'enroute_boarding_window_seconds':30.,'enroute_max_extra_meters':80.,
         'enroute_max_lateral_meters':30.}
    b=fixture([('A',weight,130)],cfg);common=b['prepared']['common']
    a=[37.45,126.95];c=[37.451,126.95];d=[37.4519,126.95];z=[37.452,126.95]
    paths=[[a,c,z],[a,c],[c,z],[c,c],[c,d],[d,z]]
    durations=[200.,100.,100.,0.,20.,10.]
    common['paths']=paths
    common['nodes']=[{'id':'city|c','city':True,'name':'platform C','lat':c[0],'lon':c[1]},
                     {'id':'city|d','city':True,'name':'alighting D','lat':d[0],'lon':d[1]}]
    common['city_nodes']=[0,1]
    common['route_info']['A'].update(n=2,capacity=capacity,offsets=[0.,20.],segments=[4])
    b['city_node_lookup']={'A|0':0,'A|1':1}
    b['physical_paths']=[{'meters':sum(distance(x,y) for x,y in zip(p,p[1:])),
                         'seconds':seconds,'stairs_meters':0.,'known_climb_meters':0.,
                         'unknown_slope_meters':0.} for p,seconds in zip(paths,durations)]
    leg={'rid':'A','board':0,'alight':1,'wait_path':3,'ride_path':4,
         'ride_seconds':20.,'next_walk':[5,10.]}
    b['prepared']['plans']['월']=[[1,'301','snu',weight,float(departure),[0,200.*factor],[]]]
    b['walk_scales']={'1':factor};b['destination_keys']={'1':'snu'}
    b['parent_ids']={'1':1};b['source_parent_mass']={'1':weight}
    b['compatible_route_policies']={'0|snu':[leg]}
    b['alternatives']={'0|snu':[{'kind':'walk','name':'continue walking','walk':[2,100.],
                                 'walk_meters':b['physical_paths'][2]['meters'],'stages':[]}]}
    b['origin_catalog']={'synthetic-existing-prefix':[{'key':'existing-C-access','walk':[1,100.],'stages':[leg]}]}
    times=[departure+130.] if arrivals is None else list(arrivals)
    b['supply']={'regular':{'A':times},'peak':{'A':times}}
    if older_weight:
        b['prepared']['plans']['월'].insert(0,[2,'301','snu',older_weight,float(departure),[3,0.],[copy.deepcopy(leg)]])
        b['walk_scales']['2']=1.;b['destination_keys']['2']='snu'
        b['parent_ids']['2']=2;b['source_parent_mass']['2']=older_weight
    return b


def node_for(bundle,stage):
    return bundle['city_node_lookup'][f"{stage['rid']}|{stage['board']}"]


class QuietPolicy:
    """Hold behavior fixed while exercising the production engine FIFO/events."""
    def __init__(self,bundle,config,locate,allow_mode=True):
        self.bundle=bundle;self.config=config;self.locate=locate;self.allow_mode=allow_mode
        self.boarding_choices=[];self.review_diagnostics=[];self.initialized=0
    def make_traits(self,uid):return traits(uid,self.config)
    def empty_ledger(self):return FareLedger()
    def student_initialize(self,state):
        if 'student_preferred_mode' not in state:
            self.initialized+=1
            state.update(student_preferred_mode='walk',student_patience_seconds=1200.,student_stop_history=[])
    def student_filter_stages(self,state,stages,allow_current=True):
        return None if stages and self.locate(stages[0]) in state.get('visited',()) else stages
    def student_mode_allowed(self,state,stages,at):return self.allow_mode
    def initial_choice(self,state,at):pass
    def maybe_switch(self,*args):return False
    def reschedule(self,*args):pass
    def complete_same_stop(self,state,stage,node):return stage
    def boarded(self,state,rid,chosen,at,end):
        if state['node'] in state['visited']:raise AssertionError('Revisited boarding platform')
        state['visited']=state['visited']|{state['node']}
        state['student_stop_history']=state['student_stop_history']+[state['node']]
    def alighted(self,*args):pass
    def accept_boarding(self,*args):return True
    def apply_boarding_walk(self,*args):return False
    def report(self):return {'initialized':self.initialized}


class CatalogueTests(unittest.TestCase):
    def catalogue(self,b):return WalkingOpportunities(b,lambda s:node_for(b,s),b['prototype_config'])
    def test_exact_existing_platform_join_keeps_clocks_and_inputs(self):
        b=walking_fixture();before=copy.deepcopy(b);catalogue=self.catalogue(b)
        opportunities=catalogue.get(0,'snu')
        self.assertEqual(len(opportunities),1)
        op=opportunities[0]
        self.assertEqual((op.prefix_path,op.suffix_path,op.node),(1,2,0))
        self.assertEqual((op.prefix_seconds,op.suffix_seconds),(100.,100.))
        self.assertLess(abs(op.extra_meters),1e-5)
        self.assertEqual(b,before)
    def test_vehicle_geometry_cannot_be_reused_as_a_walking_prefix(self):
        b=walking_fixture();b['origin_catalog']={}
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_missing_suffix_does_not_invent_connector(self):
        b=walking_fixture();b['alternatives']={}
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_exact_endpoint_gap_is_rejected_without_snapping(self):
        b=walking_fixture();b['prepared']['common']['paths'][1][-1]=[37.45100001,126.95]
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_lateral_limit_rejects_remote_real_platform(self):
        b=walking_fixture();b['prototype_config']['enroute_max_extra_meters']=1000.
        remote=[37.451,126.951]
        for index in (1,2,3):
            path=b['prepared']['common']['paths'][index]
            b['prepared']['common']['paths'][index]=[remote if p==[37.451,126.95] else p for p in path]
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_reverse_progression_is_not_a_prefix(self):
        b=walking_fixture();original=b['prepared']['common']['paths'][0]
        self.assertFalse(follows([original[0],original[-1],original[1]],original,30.))
    def test_extra_path_metres_have_an_independent_limit(self):
        b=walking_fixture();b['physical_paths'][1]['meters']+=81.
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_destination_and_unavailable_clock_are_not_inferred(self):
        b=walking_fixture();self.assertEqual(self.catalogue(b).get(0,'dorm_ug'),())
        b['physical_paths'][1]['seconds']=None
        self.assertEqual(self.catalogue(b).get(0,'snu'),())
    def test_student_origin_catalogue_paths_are_indexed(self):
        b=walking_fixture();b['student_origin_catalog']=b.pop('origin_catalog')
        self.assertEqual(len(self.catalogue(b).get(0,'snu')),1)


class EnrouteEngineTests(unittest.TestCase):
    def run_case(self,b,allow_mode=True):
        def attach(bundle,config,locate,*args,**kwargs):return QuietPolicy(bundle,config,locate,allow_mode)
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()), \
                patch.object(engine,'WORK',Path(folder)),patch.object(engine,'attach_policy',side_effect=attach):
            result=engine.simulate(b,'월','regular',export=True)
            audit=read(Path(folder)/'audit-regular-mon.json.gz')
        return result,audit
    def test_only_real_platform_prefix_then_vehicle_then_egress(self):
        result,audit=self.run_case(walking_fixture())
        trip=audit['legs'][0]
        self.assertEqual([leg[3] for leg in trip['legs'] if leg[0]==0],[1,5])
        ride=next(leg for leg in trip['legs'] if leg[0]==3)
        self.assertEqual((ride[1],ride[2]),(START+130.,START+150.))
        self.assertEqual(trip['finish_time'],START+160.)
        self.assertEqual([r['action'] for r in audit['enroute_events']],['approach_platform','boarded'])
        self.assertEqual(result['report']['final_weight'],1.)
        self.assertEqual(result['policy_report']['initialized'],1)
    def test_fractional_fifo_residual_resumes_its_own_original_suffix(self):
        result,audit=self.run_case(walking_fixture(weight=2.,older_weight=1.5,capacity=2.))
        boarded=[r for r in audit['wait_audit'] if r['outcome']=='boarded']
        self.assertEqual([(r['id'],r['weight']) for r in boarded],[(2,1.5),(1,.5)])
        self.assertLess(boarded[0]['ticket'],boarded[1]['ticket'])
        resumed=next(r for r in audit['enroute_events'] if r['action']=='resume_original_walk')
        self.assertEqual((resumed['weight'],resumed['time']),(1.5,START+150.))
        tail=next(r for r in audit['legs'] if r['id']==1 and r['weight']==1.5)
        self.assertEqual(tail['finish_time'],START+250.)
        self.assertEqual([l[3] for l in tail['legs'] if l[0]==0],[1,2])
        self.assertEqual(result['report']['final_weight'],3.5)
    def test_full_bus_does_not_remove_mass_or_keep_walker_waiting(self):
        result,audit=self.run_case(walking_fixture(older_weight=2.,capacity=2.))
        trip=next(r for r in audit['legs'] if r['id']==1)
        self.assertEqual(trip['finish_time'],START+250.)
        self.assertFalse(any(l[0]==3 for l in trip['legs']))
        resumed=next(r for r in audit['enroute_events'] if r['action']=='resume_original_walk')
        self.assertEqual(resumed['full_passes'],1)
        self.assertEqual(result['report']['final_weight'],3.)
        self.assertEqual(result['report']['unserved_trip_weight'],0.)
    def test_failed_intercept_restores_original_transit_stage(self):
        b=walking_fixture(older_weight=2.,capacity=2.)
        common=b['prepared']['common'];z=common['paths'][0][-1];e=[37.4521,126.95]
        common['paths'].extend([[z,z],[z,e],[e,z]])
        for path,seconds in zip(common['paths'][6:],[0.,20.,10.]):
            b['physical_paths'].append({'meters':sum(distance(x,y) for x,y in zip(path,path[1:])),
                                       'seconds':seconds,'stairs_meters':0.})
        common['nodes'].extend([{'id':'city|z','city':True,'name':'original platform B','lat':z[0],'lon':z[1]},
                                {'id':'city|e','city':True,'name':'other alighting','lat':e[0],'lon':e[1]}])
        common['city_nodes'].extend([2,3])
        common['route_info']['B']={'n':2,'capacity':2.,'offsets':[0.,20.],'segments':[7],'anchor':0,'city':True}
        b['prepared']['routes']['B']={'id':'B','name':'B','stops':[{'id':'z'},{'id':'e'}]}
        b['city_node_lookup'].update({'B|0':2,'B|1':3})
        b['supply']['regular']['B']=[START+280.]
        # A small synthetic tail tests state restoration, not route choice.
        original=next(p for p in b['prepared']['plans']['월'] if p[0]==1)
        original[6]=[{'rid':'B','board':0,'alight':1,'wait_path':6,'ride_path':7,
                      'ride_seconds':20.,'next_walk':[8,10.]}]
        _,audit=self.run_case(b)
        trip=next(t for t in audit['legs'] if t['id']==1)
        self.assertEqual([audit['vehicles'][l[6]]['rid'] for l in trip['legs'] if l[0]==3],['B'])
        restored=next(r for r in audit['wait_audit'] if r['id']==1 and r['node']==2)
        self.assertEqual((restored['arrival'],restored['ready'],restored['end']),
                         (START+250.,START+270.,START+280.))
        self.assertEqual(trip['finish_time'],START+310.)
    def test_pair_at_inclusive_deadline_boards_before_cancelled_timeout(self):
        result,audit=self.run_case(walking_fixture(weight=1.5,capacity=1.,arrivals=[START+150.,START+150.]))
        boardings=[r for r in audit['enroute_events'] if r['action']=='boarded']
        self.assertEqual([r['weight'] for r in boardings],[1.,.5])
        self.assertFalse(any(r['action']=='resume_original_walk' for r in audit['enroute_events']))
        self.assertEqual(result['report']['final_weight'],1.5)
    def test_preparation_cannot_board_earlier_vehicle(self):
        _,audit=self.run_case(walking_fixture(arrivals=[START+119.,START+130.]))
        boarding=next(r for r in audit['enroute_events'] if r['action']=='boarded')
        self.assertEqual((boarding['ready'],boarding['time']),(START+120.,START+130.))
    def test_personal_walking_factor_applies_exactly_once(self):
        _,audit=self.run_case(walking_fixture(factor=1.2,arrivals=[START+150.]))
        walks=[r for r in audit['legs'][0]['legs'] if r[0]==0]
        self.assertEqual([r[2]-r[1] for r in walks],[120.,12.])
        self.assertEqual(audit['legs'][0]['finish_time'],START+182.)
    def test_no_bus_in_window_preserves_full_original_walk(self):
        _,audit=self.run_case(walking_fixture(arrivals=[START+151.]))
        self.assertEqual(audit['enroute_events'],[])
        self.assertEqual(audit['legs'][0]['finish_time'],START+200.)
        self.assertEqual(audit['legs'][0]['legs'][0][3],0)
    def test_mode_commitment_can_decline_opportunity(self):
        _,audit=self.run_case(walking_fixture(),allow_mode=False)
        self.assertEqual(audit['enroute_events'],[])
        self.assertEqual(audit['legs'][0]['finish_time'],START+200.)
    def test_feature_disabled_keeps_original_walk(self):
        b=walking_fixture();b['prototype_config']['enroute_boarding_window_seconds']=0.
        result,audit=self.run_case(b)
        self.assertFalse(result['walking_opportunities_report']['enabled'])
        self.assertEqual(audit['legs'][0]['finish_time'],START+200.)
    def test_end_boundary_vehicle_precedes_timeout_and_completes_later(self):
        result,audit=self.run_case(walking_fixture(departure=END-150.,arrivals=[END]))
        boarding=next(r for r in audit['enroute_events'] if r['action']=='boarded')
        self.assertEqual(boarding['time'],END)
        self.assertEqual(audit['legs'][0]['finish_time'],END+30.)
        self.assertEqual(result['report']['unserved_trip_weight'],0.)


if __name__=='__main__':unittest.main()

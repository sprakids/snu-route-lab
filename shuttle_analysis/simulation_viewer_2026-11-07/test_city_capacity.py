import contextlib,copy,io,unittest
from city_capacity_model import first_boardable,scaled_stages,simulate,START
from prepare_city import weekday_plan,planned_departures


def leg(rid='A',board=0,alight=1):
    return {'rid':rid,'board':board,'alight':alight,'wait_path':0,'ride_path':0,
            'ride_seconds':60.,'city_wait':0.,'next_walk':[0,5.]}


def vehicle(rid='A',cap=50,onboard=()):
    return {'rid':rid,'cap':cap,'onboard':list(onboard),'last_stop':-1}


def waiter(weight,rid='A'):
    return {'w':float(weight),'stages':[leg(rid)],'stage':0}


def fixture(groups):
    point=[37.45,126.95];routes={};info={};plans=[]
    for identity,(rid,weight,first) in enumerate(groups,1):
        routes[rid]={'id':rid,'name':rid,'stops':[{'id':'s0','lat':point[0],'lon':point[1]},{'id':'s1','lat':point[0]+.001,'lon':point[1]}]}
        info[rid]={'n':2,'offsets':[0.,60.],'segments':[0],'anchor':0,'city':True,'capacity':50,
                   'origin_to_modeled_first_stop_seconds':0.,
                   'plan':{'first_seconds':START+first,'last_seconds':START+first+100,'headway_seconds':100}}
        plans.append([identity,'301','snu',float(weight),float(START),[0,1.],[leg(rid)]])
    common={'nodes':[{'id':'city|s0','city':True,'route':'city','name':'shared','lat':point[0],'lon':point[1]}],
            'city_nodes':[0],'route_info':info,'paths':[[point,[point[0]+.001,point[1]]]]}
    return {'prepared':{'common':common,'routes':routes,'plans':{'월':plans}},
            'city_node_lookup':{r+'|0':0 for r in routes},'walk_scales':{str(p[0]):1. for p in plans},
            'destination_keys':{str(p[0]):'snu' for p in plans},'alternatives':{'0|snu':[]}}


class PlannedServiceTests(unittest.TestCase):
    def test_campus_road_outside_polygon_still_has_40_ceiling(self):
        from prepare_city import CampusRoad,CAMPUS_STOP_NAMES
        from speed_capacity_model import profile
        self.assertIn('신소재',CAMPUS_STOP_NAMES)
        self.assertIn('건설환경종합연구소앞',CAMPUS_STOP_NAMES)
        curve=profile([[37.453496,126.950227],[37.447203,126.949693]],[1],CampusRoad())
        self.assertLessEqual(max(curve['cap']),40)
        self.assertLessEqual(max(curve['v'])*3.6,40.00001)
    def test_weekday_hours_override_the_current_sunday_date_field(self):
        meta={'tm_all':'06:00 ~ 23:55(평일), 06:00 ~ 23:50(토요일), 06:00 ~ 23:50(공휴일)',
              'term_all':'5분(평일), 9분(토요일), 9분(공휴일)','lastBusTm':'20261108235000'}
        plan=weekday_plan(meta)
        self.assertEqual(plan['last_seconds'],23*3600+55*60)
        self.assertEqual(plan['headway_seconds'],300)
    def test_first_and_last_are_kept_when_last_is_not_on_interval_grid(self):
        values=planned_departures({'first_seconds':100,'last_seconds':350,'headway_seconds':100})
        self.assertEqual(values,[100,200,300,350.])


class ForecastTests(unittest.TestCase):
    def test_capacity_full_vehicle_is_skipped_and_alighting_frees_seats(self):
        rows=[(100.,0,0),(200.,1,0)]
        fleet=[vehicle(onboard=[(1,{'w':50})]),vehicle()]
        self.assertEqual(first_boardable(rows,fleet,50,0,leg(),1,[])[0],200)
        fleet[0]['onboard']=[(0,{'w':50})]
        self.assertEqual(first_boardable(rows,fleet,50,0,leg(),1,[])[0],100)
    def test_incompatible_route_waiters_do_not_block_or_consume_capacity(self):
        result=first_boardable([(100.,0,0)],[vehicle()],50,0,leg(),1,[waiter(100,'B')])
        self.assertEqual(result[0],100)
    def test_current_queue_can_clear_before_hypothetical_arrival(self):
        rows=[(100.,0,0),(200.,1,0),(300.,2,0)]
        q=[waiter(30)]
        result=first_boardable(rows,[vehicle(),vehicle(),vehicle()],150,0,leg(),30,q)
        self.assertEqual(result[0],200);self.assertEqual(q[0]['w'],30)
    def test_pool_uses_first_compatible_bus_with_space(self):
        pool={**leg('A',21,25),'pool':[leg('A',21,25),leg('B',8,12)]}
        fleet=[vehicle('A',onboard=[(25,{'w':50})]),vehicle('B')]
        result=first_boardable([(100.,0,21),(110.,1,8)],fleet,0,0,pool,1,[])
        self.assertEqual((result[0],result[3]['rid']),(110,'B'))
    def test_same_stop_on_wrong_direction_or_terminal_index_is_not_boardable(self):
        rows=[(100.,0,5),(200.,1,0)]
        self.assertEqual(first_boardable(rows,[vehicle(),vehicle()],0,0,leg(),1,[])[0],200)
    def test_pool_walking_scale_does_not_mutate_source_or_double_apply(self):
        source={**leg(),'pool':[leg(),leg('B')]};before=copy.deepcopy(source)
        result=scaled_stages([source],2.)[0]
        self.assertEqual(result['next_walk'][1],10)
        self.assertEqual([x['next_walk'][1] for x in result['pool']],[10,10])
        self.assertEqual(source,before)


class VehicleIntegrationTests(unittest.TestCase):
    def run_model(self,groups):
        with contextlib.redirect_stdout(io.StringIO()):
            return simulate(fixture(groups),'월','peak',False,{'max_switches':0})
    def test_75_weight_uses_50_now_and_25_on_next_city_bus(self):
        data=self.run_model([('A',75,100)])
        events=data['events'];self.assertEqual([e[6] for e in events],[50,25])
        self.assertEqual([e[8] for e in events],[25,0])
        self.assertEqual(data['report']['final_weight'],75)
        self.assertEqual(data['report']['city_boarding_weight'],75)
        self.assertTrue(all(e[7]<=e[3] for e in events))
    def test_shared_stop_has_fifo_per_eligible_line_and_separate_denial(self):
        data=self.run_model([('A',60,100),('B',20,110)])
        first=data['events'][0]
        self.assertEqual((first[6],first[8],first[10]),(50,10,30))
        b=next(e for e in data['events'] if e[11]=='B')
        self.assertEqual((b[6],b[8]),(20,0))
        self.assertEqual(data['report']['city_denied_weight'],10)
        self.assertEqual(data['report']['city_boarding_weight'],80)
    def test_last_service_residual_is_unserved_not_zero_wait(self):
        data=self.run_model([('A',120,100)])
        self.assertEqual(data['report']['city_boarding_weight'],100)
        self.assertEqual(data['report']['city_unserved_weight'],20)
        self.assertGreater(data['hourly']['0']['11']['mean_queue_exposure_min'],0)
        self.assertAlmostEqual(data['queues'][-1][0],20)
        self.assertAlmostEqual(data['queue_timeline'][0][-1][1],20)


if __name__=='__main__':unittest.main()

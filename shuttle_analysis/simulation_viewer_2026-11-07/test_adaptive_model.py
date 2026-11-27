import copy,math,unittest
import adaptive_capacity_model as m

class AdaptiveTests(unittest.TestCase):
    def test_margin_cooldown_and_switch_cap(self):
        self.assertTrue(m.should_switch(1000,1500,1380,0,-math.inf))
        self.assertFalse(m.should_switch(1000,1500,1381,0,-math.inf))
        self.assertFalse(m.should_switch(1000,1500,1100,2,-math.inf))
        self.assertFalse(m.should_switch(1000,1500,1100,1,900))
        self.assertTrue(m.should_switch(1000,math.inf,1400,0,-math.inf))
        self.assertFalse(m.should_switch(1000,math.inf,math.inf,0,-math.inf))

    def test_queue_forecast_uses_current_seats_and_alighting(self):
        vehicles=[{'cap':60,'last_stop':-1,'onboard':[(1,{'w':20}),(4,{'w':40})]},
                  {'cap':60,'last_stop':-1,'onboard':[]}]
        schedule=[[(100,0,1),(200,1,1)]]
        self.assertEqual(m.queue_departure(schedule,vehicles,0,90,19,1),100)
        self.assertEqual(m.queue_departure(schedule,vehicles,0,90,20,1),200)
        vehicles[0]['last_stop']=1
        self.assertEqual(m.queue_departure(schedule,vehicles,0,90,0,1),200)

    def fixture(self,walking=100,weights=(10,)):
        rid='shuttle-test';when=15*3600
        stage={'rid':rid,'board':0,'alight':1,'ride_path':2,'wait_path':1,
               'ride_seconds':60,'next_walk':[3,10],'city_wait':0}
        plans=[[i+1,'301','snu',w,when,[0,0],[copy.deepcopy(stage)]] for i,w in enumerate(weights)]
        prepared={'routes':{rid:{'id':rid,'name':'test','stops':[{'lat':37.45,'lon':126.95}]*2}},
            'plans':{'월':plans},'common':{'nodes':[{'id':rid+'|0','lat':37.45,'lon':126.95}],
                'route_info':{rid:{'n':1,'anchor':0,'offsets':[0,60],'segments':[2]}},
                'paths':[[[37.45,126.95]]]*5}}
        return {'prepared':prepared,'alternatives':{'0|snu':[{'name':'도보','kind':'walk','walk':[4,walking],'stages':[]}]},
            'walk_scales':{str(i+1):1 for i in range(len(plans))},'destination_keys':{str(i+1):'snu' for i in range(len(plans))}}

    def test_leave_queue_for_walking_and_account_for_abandonment(self):
        b=self.fixture();before=copy.deepcopy(b)
        d=m.simulate(b,'월','regular',export=False)
        self.assertEqual(d['report']['switched_trip_weight'],10)
        self.assertEqual(d['report']['finished_weight'],10)
        self.assertEqual(d['report']['unserved_trip_weight'],0)
        self.assertEqual(sum(e[6] for e in d['events']),0)
        h=d['hourly']['0']['15']
        self.assertEqual(h['switched_weight'],10)
        self.assertEqual(h['served_weight'],0)
        self.assertIsNone(h['mean_wait_min'])
        self.assertEqual(b,before)

    def test_no_switch_when_walking_is_slower(self):
        d=m.simulate(self.fixture(walking=2000),'월','regular',export=False)
        self.assertEqual(d['report']['switched_trip_weight'],0)
        self.assertEqual(sum(e[6] for e in d['events']),10)

    def test_capacity_and_mass_survive_rechecks_and_partial_boarding(self):
        d=m.simulate(self.fixture(walking=2000,weights=(75,)),'월','regular',export=False,settings={'max_switches':0})
        boarded=[e[6] for e in d['events'] if e[6]]
        self.assertEqual(boarded,[60,15])
        self.assertEqual(d['report']['final_weight'],75)
        self.assertTrue(all(e[7]<=60 for e in d['events']))
        self.assertEqual(d['daily']['0']['denied_weight'],15)

    def test_city_departures_are_shared_and_not_before_ready(self):
        r={'city':{'interval_minutes':10,'stops':[{'lat':37.45,'lon':126.95}]}}
        a=m.city_departure(r,'city',0,55000,'월')
        b=m.city_departure(r,'city',0,55000,'월')
        self.assertEqual(a,b);self.assertGreaterEqual(a,55000)
        self.assertEqual(m.city_departure(r,'city',0,a+.01,'월'),a+600)

    def test_changed_walk_keeps_personal_speed_exactly_once(self):
        b=self.fixture();b['walk_scales']['1']=2
        d=m.simulate(b,'월','regular',export=False)
        self.assertAlmostEqual(d['switches'][0][8]-d['switches'][0][0],200)
        self.assertAlmostEqual(d['report']['mean_finished_trip_minutes'],220/60)

if __name__=='__main__':unittest.main()

"""Public V12 predictions. The previous release is opened only for the comparison archive."""
from bisect import bisect_right
import math

from city_wait import project
from network_replay import clock, released_network
from terminal_wait import RELEASE, TerminalWait


class NetworkQueue:
    config = {'id':RELEASE}

    def __init__(self,historical):
        self.historical = historical
        self.operations = released_network()
        self.terminal_wait = TerminalWait()
        self._archive = None

    def current(self):
        if self._archive is None:
            from queue_model_sync import LatestQueueModel
            self._archive = LatestQueueModel(self.historical)
        return self._archive.current()

    def info(self):
        return {'model_id':RELEASE,'algorithm_id':'v12_network_boarding','automatic':True,
                'calibrated':False,'observed_queue':False,'city_operations':self.operations.info(),
                'terminal_wait':self.terminal_wait.info(),'city_wait':{'available':True,'route_count':8},
                'scope':'등록 시내버스·학생 셔틀 전체','boarding_algorithm':'V12 승차 원장·정원·운행 시간표',
                'sync':{'active_model_id':RELEASE,'status':'active','source':'bundled_release',
                        'payload_sha256':self.operations.sha}}

    def legacy_queue_compatible(self,route):
        return False

    def with_vehicle_supply(self,route,index,row,*,terminal_dispatch_at=None):
        if not row:return row
        rid,i = self.operations.mapping(route,index)
        spec = self.operations.routes.get(rid)
        delta = spec['offsets'][i]-spec['offsets'][spec['anchor']] if spec and i is not None else 0
        stored = row.get('vehicle_supply') or {}
        dispatch = terminal_dispatch_at if terminal_dispatch_at is not None else stored.get('terminal_dispatch_at',row['departure_at']-delta)
        if type(dispatch) not in (int,float) or not math.isfinite(dispatch):
            raise ValueError('vehicle_terminal_clock')
        mid,sec,case = clock(dispatch)
        mid = row.get('service_midnight',stored.get('service_midnight',mid))
        node = {'shuttle-41841':'admin_snu','shuttle-daehak':'admin_daehak'}.get(rid)
        cap,count = route.get('capacity',60),1
        basis = 'registered_supply'
        schedules = self.terminal_wait.schedules.get((case,node))
        if schedules and (slot:=bisect_right(schedules[0],sec)-1)>=0:
            group = schedules[1][slot]
            cap,count,basis = group[0],len(group),'v12_terminal_dispatch_schedule'
        return {**row,'vehicle_supply':{'model_id':RELEASE,'profile_route_id':rid,'capacity':cap,
                'batch_vehicles':count,'terminal_dispatch_at':dispatch,'terminal_dispatch_second':dispatch-mid,
                'service_midnight':mid,'observed_capacity':False,'basis':basis}}

    def city_arrival(self,transit,route,index,ready,base,live=True,**kwargs):
        if not base:return base
        h = kwargs.get('headway') or (base.get('arrival_forecast') or {}).get('headway_seconds') or transit.interval(route,ready)*60
        profile = self.operations.profile(route,index,ready,h)
        return project(self,transit,route,index,ready,base,live,simulation=profile,**kwargs)

    def arrival(self,route,index,ready,observed,timetable,asof,snapshot=None,live=True,*,waiting_since=None):
        base = timetable._schedule_arrival(route,index,ready)
        if base is None:return None
        join = ready-20 if waiting_since is None else min(ready,waiting_since)
        exact = self.terminal_wait.arrival(route,index,join+20,observed,timetable,asof,live)
        if exact and exact[0]['boarding_at']>=ready:
            value = self.with_vehicle_supply(route,index,exact[0])
            profile = self.operations.profile(route,index,ready,300)
            value['automatic_queue'].update(expected_load_ratio=profile['load_ratio'],crowd_model_id=RELEASE,
                                            arrival_time=ready,remaining_wait_seconds=round(value['boarding_at']-ready))
            value['wait_seconds'] = round(value['departure_at']-ready)
            return [value]
        last = base['last_scheduled_departure_at']
        confirmed = [a for a in observed if live and a.get('arrival_source')=='live_shuttle'
                     and a.get('clock_conditioning_verified') and not a.get('observed_at_stop')
                     and a.get('provided_at') is not None and -5<=asof-a['provided_at']<=60
                     and a.get('earliest_departure_at',a['departure_at'])>=ready and a['departure_at']<=last]
        sighting = min(confirmed,key=lambda a:a['departure_at'],default=None)
        nominal = (base['wait_model'].get('headway_minutes') or 10)*60
        target = base['departure_at'] if base.get('fixed_departure') and base['departure_at']-ready>nominal else ready
        profile = self.operations.profile(route,index,target,nominal)
        event = self.operations.passage(route,index,ready)
        leave = base['departure_at']
        basis = profile['basis']
        if sighting:
            leave = sighting['departure_at']
            basis = 'observed_approach_and_v12_capacity'
        elif event and not base.get('fixed_departure') and event['departure_at']<=last:
            leave = event['departure_at']
        if waiting_since is not None:
            # Someone already ahead in the queue can use the next service opportunity.
            # Only residual capacity delay survives the time already spent waiting.
            extra = max(0,profile['extra_wait_seconds']-(ready-join))
        else:extra = profile['extra_wait_seconds']
        if base.get('fixed_departure') and not sighting:
            # Use whole scheduled opportunities for fixed departures. A small
            # risk in a pooled sample must not advance everyone to the next bus.
            for _ in range(math.floor(extra/nominal+.5)):
                next_service = timetable._schedule_arrival(route,index,leave+1)
                if not next_service or next_service['departure_at']<=leave:return []
                leave = next_service['departure_at']
        else:leave += round(extra)
        if leave>last:return []
        dwell = round(profile['onboard_dwell'] or 0) if route['stops'][index]['id']=='snu-410' else 0
        board = max(ready,leave-dwell)
        if event and not sighting and leave==event['departure_at'] and event['opens_at']<leave:
            board = max(board,event['opens_at'])
        value = self.with_vehicle_supply(route,index,{**base,'departure_at':leave})
        mid,sec,case = clock(ready)
        rid,i = self.operations.mapping(route,index)
        curve = self.operations.data['queues'].get(case,{}).get(f'{rid}:{i}')
        queue = curve.get(str(int(sec//60)),0.) if curve is not None and profile['supply_basis']=='stop_vehicle_replay' else None
        q = {'model_id':RELEASE,'source':'network_wait_v12','basis':basis,'supply_basis':profile['supply_basis'],
             'algorithm_id':'v12_network_boarding','join_at':join,'join_minute':int((join-mid)//60),
             'arrival_time':ready,'boarding_at':board,'departure_at':leave,'queue_at_arrival':queue,
             'expected_wait_seconds':round(board-ready) if waiting_since is not None else round(board-join),
             'remaining_wait_seconds':round(board-ready),'join_to_board_seconds':round(board-join),
             'onboard_before_departure_seconds':round(leave-board),'observed_queue':False,'calibrated':False,
             'future_query':not live,'estimated_at':asof,'model_only':not bool(sighting),
             'boarded_mass':profile['boarded_mass'],'cohort_available':profile['boarded_mass'] is not None,
             'profile_route_id':rid,'queue_now':None,'current_demand_multiplier':1.,'crowd_observations_used':False,
             'live_signal':{'available':False,'vehicles':0},'clock_observed_at':sighting.get('provided_at') if sighting else None,
             'extrapolated':profile['extrapolated'],'mean_capacity_delay_seconds':round(extra),
             'capacity_assumption':value['vehicle_supply']['capacity'],
             'expected_load_ratio':profile['load_ratio'],'crowd_model_id':RELEASE,
             'live_arrival_conditioned':bool(sighting),'label':'V12 셔틀 대기 추정'}
        if sighting and extra<1:
            value.update({k:sighting[k] for k in ('vehicle_id','provided_at','observed_interval','observed_at_stop') if k in sighting})
        return [{**value,'boarding_at':board,'earliest_departure_at':board,'automatic_queue':q,
                 'next_scheduled_departure_at':base['departure_at'] if base.get('fixed_departure') else None,
                 'wait_model':{**base['wait_model'],'kind':'network_wait_v12','queue_model_id':RELEASE},
                 'arrival_source':'shuttle_auto_queue_estimate','wait_seconds':round(leave-ready),
                 'eta_window_seconds':[round(board-ready)]*2,'prediction_note':q['label']}]

"""Per-minute terminal waits from the released V12 replay, on the walking-arrival clock."""
import hashlib
import json
import math
import os
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

from shuttle_timetable import KST, service_day

RELEASE = 'V261125170855'
SOURCE = f'https://snu-shuttle-simulation.vercel.app/{RELEASE}/routing-feed.json'
FILE = Path(__file__).parent / 'data' / 'terminal_wait_v12.json'
DIGEST = '548a2fa7f483ceb592a05275927671fec704ce1655151d920fee21a6eafff709'
COLUMNS = ['minute', 'boarded_mass', 'mean_join_to_board_s', 'mean_board_to_depart_s',
           'queue_mean_people', 'next_dispatch_boarding_share']
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri')
NODES = {'41841': 'admin_snu', '41843': 'admin_daehak'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class TerminalWait:
    def __init__(self, path=FILE):
        self.cells = {}
        self.schedules = {}
        self.sha = None
        self.status = 'disabled'
        if os.environ.get('SNU_TERMINAL_WAIT_ENABLED') == '0':
            return
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != DIGEST:
                raise ValueError('release_digest')
            data = json.loads(raw)
            if (data['release'] != RELEASE or data['schema'] != 'snu-terminal-wait-v1'
                    or data['timezone'] != 'Asia/Seoul' or data['columns'] != COLUMNS):
                raise ValueError('metadata')
            cases = data['cases']
            if set(cases) != {f'{s}-{d}' for s in ('regular','peak') for d in DAYS}:
                raise ValueError('coverage')
            cells = {}
            for case, nodes in cases.items():
                if set(nodes) != set(NODES.values()):
                    raise ValueError('nodes')
                for node, rows in nodes.items():
                    for minute, mass, outside, on_board, queue, next_share in rows:
                        key = (case, node, minute)
                        if (type(minute) is not int or not 0 <= minute < 1440 or key in cells
                                or not all(finite(x) and x >= 0 for x in (mass,outside,on_board))
                                or queue is not None and not (finite(queue) and queue >= 0)
                                or next_share is not None and not (finite(next_share) and 0 <= next_share <= 1)):
                            raise ValueError('cell')
                        cells[key] = (mass,outside,on_board,queue,next_share)
            if not cells:
                raise ValueError('empty')
            schedules = {}
            for case, nodes in cases.items():
                for node in nodes:
                    departures = data['schedules'][case][node]
                    schedules[case,node] = ([row[0] for row in departures], [row[1] for row in departures])
            self.cells = cells
            self.schedules = schedules
            self.sha = DIGEST
            self.status = 'active'
        except (OSError, ValueError, KeyError, TypeError):
            self.status = 'legacy_fallback'

    def info(self):
        return {'release': RELEASE, 'source': SOURCE, 'sha256': self.sha, 'status': self.status,
                'station_id':'snu-410', 'providers':list(NODES), 'timezone':'Asia/Seoul',
                'daytime_window_minutes':{'41841':[420,1260], '41843':[420,1140]}, 'peak_window_minutes':[900,1140],
                'minimum_boarded_mass':0, 'supported_cells':len(self.cells)}

    def node_at(self, route, index, time_at):
        if not self.cells or route.get('provider_id') not in NODES:
            return None
        stop = route['stops'][index]
        if stop.get('id') != 'snu-410' or not stop.get('board_allowed') or not service_day(time_at):
            return None
        date = datetime.fromtimestamp(time_at,KST)
        minute = date.hour*60 + date.minute
        if 420 <= minute < (1260 if route['provider_id']=='41841' else 1140):
            return NODES[route['provider_id']], minute, DAYS[date.weekday()]
        return None

    def with_supply(self, route, index, row):
        supply = (row or {}).get('vehicle_supply')
        if not supply:
            return row
        terminal = supply['terminal_dispatch_at']
        scope = self.node_at(route,index,terminal)
        if scope is None:
            return row
        node, minute, day = scope
        scenario = 'peak' if 900 <= minute < 1140 else 'regular'
        seconds, capacities = self.schedules[f'{scenario}-{day}',node]
        slot = bisect_right(seconds, supply['terminal_dispatch_second']) - 1
        if slot < 0:
            return row
        group = capacities[slot]
        return {**row, 'vehicle_supply':{**supply, 'model_id':RELEASE, 'capacity':group[0],
                'batch_vehicles':len(group),'basis':'v12_terminal_dispatch_schedule'}}

    def arrival(self, route, index, ready, observed, timetable, asof, live):
        # New arrivals only. The engine records the full time since physically joining,
        # including the planner's existing 20-second preparation interval.
        join = ready - 20
        scope = self.node_at(route,index,join)
        if scope is None:
            return None
        if live and any(a.get('arrival_source')=='live_shuttle' and a.get('clock_conditioning_verified')
                        and not a.get('observed_at_stop') and finite(a.get('provided_at'))
                        and -5 <= asof-a['provided_at'] <= 60
                        and a.get('earliest_departure_at',a.get('departure_at',0)) >= ready for a in observed):
            return None
        node, minute, day = scope
        scenario = 'peak' if 900 <= minute < 1140 else 'regular'
        cell = self.cells.get((f'{scenario}-{day}',node,minute))
        if not cell or cell[0] <= 0:
            return None
        base = timetable._schedule_arrival(route,index,ready)
        if not base:
            return None
        mass, outside, onboard, queue, next_share = cell
        board_at = max(ready, join + round(outside))
        dwell = round(onboard)
        leave = board_at + dwell
        last = base.get('last_scheduled_departure_at')
        if last is not None and leave > last:
            return None
        detail = {'model_id':RELEASE, 'source':'terminal_wait_v12', 'observed_queue':False,
                  'algorithm_id':'snu-terminal-wait-v1','future_query':not live,'estimated_at':asof,
                  'model_only':True,'calibrated':False,'current_demand_multiplier':1.,
                  'live_signal':{'available':False,'vehicles':0,'source':'unavailable'},
                  'node':node,'scenario':scenario,'join_minute':minute,'arrival_time':ready,
                  'join_at':join,'boarding_at':board_at,'departure_at':leave,
                  'join_to_board_seconds':round(board_at-join),'onboard_before_departure_seconds':dwell,
                  'expected_wait_seconds':round(board_at-join),'boarded_mass':mass,'queue_at_arrival':queue,
                  'next_dispatch_boarding_share':next_share,'capacity_assumption':44,
                  'unit':'weighted_expected_trip_events','range_kind':'conditional_mean_not_interval',
                  'cohort_available':True,'live_arrival_conditioned':False,'label':'V12 셔틀 대기 추정'}
        return [{**base,'arrival_source':'shuttle_auto_queue_estimate','automatic_queue':detail,
                 'wait_model':{'kind':'terminal_wait_v12','queue_model_id':RELEASE},
                 'earliest_departure_at':board_at,'boarding_at':board_at,'departure_at':leave,
                 'wait_seconds':round(leave-ready),'eta_window_seconds':[round(board_at-ready)]*2,
                 'fixed_departure':False,'next_scheduled_departure_at':None,'prediction_note':detail['label']}]

"""Boarding opportunities and travel clocks derived from the ten published V12 replays."""
import gzip
import hashlib
import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from shuttle_timetable import KST, service_day
from terminal_wait import DAYS, RELEASE

FILE = Path(__file__).parent/'data/network_v12.json.gz'
DIGEST = '8fcb84102c8b285b4f4ed70915bf7fc39a3520a6c500f60cec5ef5d03e5b228f'
ALIASES = {'shuttle-41843':'shuttle-daehak','shuttle-41942':'shuttle-daehak',
           'shuttle-41915':'shuttle-41841'}
SUPPLY_PROXIES = {'shuttle-41916':'shuttle-41914','shuttle-41869':'shuttle-41914',
                  'shuttle-41842':'shuttle-41841'}


def clock(at):
    day = datetime.fromtimestamp(at,KST)
    midnight = day.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    sec = at-midnight
    scenario = 'peak' if 15*3600<=sec<19*3600 else 'regular'
    return midnight,sec,scenario+'-'+DAYS[day.weekday()] if service_day(at) else None


@lru_cache(maxsize=1)
def released_network():
    return NetworkReplay(FILE)


class NetworkReplay:
    model_id = RELEASE

    def __init__(self,path):
        raw = path.read_bytes()
        self.sha = hashlib.sha256(raw).hexdigest()
        if self.sha != DIGEST:raise ValueError('V12 network replay checksum mismatch')
        self.data = json.loads(gzip.decompress(raw))
        if self.data['release'] != RELEASE or len(self.data['cases']) != 10:
            raise ValueError('V12 network replay release mismatch')
        self.routes = self.data['routes']
        self.by_stop = {}
        self.occurrences = {}
        self.speed = {}
        for rid,route in self.routes.items():
            self.by_stop[rid] = {(sid,seq):i for i,(sid,seq) in enumerate(route['stops'])}
            self.occurrences[rid] = {s[0]:i for i,s in enumerate(route['stops']) if s[0]}
        for kind in ('bus','shuttle'):
            self.speed[kind] = statistics.median(v['speed_mps'] for r,v in self.routes.items()
                                                  if r.startswith('shuttle')==(kind=='shuttle'))
        self.hourly = defaultdict(lambda:[0,0.,0])
        self.seconds = {}
        for case,routes in self.data['cases'].items():
            for rid,stops in routes.items():
                for idx,rows in stops.items():
                    i = int(idx)
                    self.seconds[case,rid,i] = [row[0] for row in rows]
                    for sec,cap,load,left,_ in rows:
                        hour = sec//3600
                        for key in (rid,'shuttles' if rid.startswith('shuttle') else 'buses'):
                            acc = self.hourly[case,key,hour]
                            acc[0] += 1
                            acc[1] += load/cap
                            acc[2] += int(load+1>cap+1e-6 and left>0)

    def info(self):
        return {'model_id':RELEASE,'available':True,'source_dates':[],
                'release_sha256':self.sha,'modeled_routes':len(self.routes),'cases':10,
                'observed_operations':False,'destination_dwell_included':True,
                'projection':'operating timetable with V12 route or mode priors outside replay coverage'}

    def mapping(self,route,index):
        rid = ALIASES.get(route['id'],route['id'])
        stops = self.by_stop.get(rid,{})
        stop = route['stops'][index]
        if not stops:
            return rid,None
        if route.get('kind')!='shuttle':
            return rid,stops.get((stop['id'],stop['seq']))
        if rid=='shuttle-daehak':
            # The released outbound and return legs end at distinct platforms.
            return rid,{'snu-410':0,'snu-2500':1,'snu-2501':2}.get(stop['id'])
        if route['id']=='shuttle-41915':
            return rid,self.occurrences[rid].get(stop['id'])
        i = index % len(self.routes[rid]['stops'])
        return rid,i if self.routes[rid]['stops'][i][0]==stop['id'] else None

    def ride(self,route,i,j,meters):
        rid,a = self.mapping(route,i)
        _,b = self.mapping(route,j)
        spec = self.routes.get(rid)
        if a is not None and b is not None:
            if rid=='shuttle-daehak' and j>i+1:
                times=[self.ride(route,k,k+1,0)[0] for k in range(i,j)]
                if all(t>0 for t in times):return sum(times),'v12_segment_clock'
            if rid=='shuttle-daehak' and j==i+1:
                # The app combines the town's two platforms into one stop.
                if a==2 and b==0: b=3
            elif b<=a and route.get('cycle_length'):
                b += len(spec['stops'])
            offsets = spec['offsets']
            if a<b<len(offsets):
                return offsets[b]-offsets[a],'v12_segment_clock'
        kind = 'shuttle' if route.get('kind')=='shuttle' else 'bus'
        speed = spec['speed_mps'] if spec else self.speed[kind]
        return meters/speed,'v12_route_speed_projection' if spec else 'v12_mode_speed_projection'

    def series(self,route,index,at):
        mid,sec,case = clock(at)
        rid,i = self.mapping(route,index)
        rows = self.data['cases'].get(case,{}).get(rid,{}).get(str(i),[])
        return mid,sec,case,rid,i,rows,self.seconds.get((case,rid,i),[])

    def passage(self,route,index,at,*,anchor=None,blocked=()):
        mid,sec,case,rid,i,rows,times = self.series(route,index,at)
        if not times:return None
        shift = 0
        if anchor is not None:
            k = bisect_left(times,anchor-mid)
            near = min(times[max(0,k-1):k+1],key=lambda x:abs(mid+x-anchor))
            shift = anchor-mid-near
        target = max([at,*[b+1 for b in blocked]])-mid-shift
        k = bisect_left(times,target)
        if k==len(times):return None
        row = rows[k]
        distinct = sorted(set(times[max(0,k-4):k+6]))
        gaps = [b-a for a,b in zip(distinct,distinct[1:])]
        headway = statistics.median(gaps) if gaps else (route.get('interval_minutes') or 10)*60
        # An official nighttime/feeder timetable may operate long after a replay gap.
        if abs(times[k]-target)>max(1800,2*headway):return None
        return {'departure_at':mid+row[0]+shift,'headway_seconds':max(1,headway),
                'source':'v12_vehicle_replay','future_departures_at':sorted(set(mid+t+shift for t in times[k:k+12])),
                'phase_conditioned':anchor is not None,'operations':self.info(),
                'opens_at':mid+row[4]+shift,'capacity':row[1],'load_ratio':row[2]/row[1]}

    service = passage

    def profile(self,route,index,at,headway):
        mid,sec,case,rid,i,rows,times = self.series(route,index,at)
        cohort = self.data['cohorts'].get(case,{}).get(f'{rid}:{i}:{int(sec//300)}')
        start,end = bisect_left(times,sec-900),bisect_left(times,sec+900)
        local = rows[start:end]
        if local:
            count = len(local)
            load = sum(r[2]/r[1] for r in local)/count
            blocked = sum(r[2]+1>r[1]+1e-6 and r[3]>0 for r in local)
            basis = 'stop_vehicle_replay'
        else:
            cases = [case] if case else ['regular-'+d for d in DAYS]
            mode = 'shuttles' if route.get('kind')=='shuttle' else 'buses'
            prior = rid if rid in self.routes else SUPPLY_PROXIES.get(rid)
            keys = [prior,mode] if prior else [mode]
            count,load,blocked = 0,0.,0
            for key in keys:
                for offset in (0,1,2):
                    hours = {int(sec//3600)-offset,int(sec//3600)+offset}
                    sums = [self.hourly[c,key,h] for c in cases for h in hours if (c,key,h) in self.hourly]
                    if sums:
                        count,load,blocked = map(sum,zip(*sums))
                        break
                if count:break
            all_hours = not count
            if all_hours:
                sums = [self.hourly[c,keys[0],h] for c in cases for h in range(25)
                        if (c,keys[0],h) in self.hourly]
                if sums:count,load,blocked = map(sum,zip(*sums))
            load = load/count if count else None
            basis = 'all_hours_capacity_prior' if all_hours else 'weekday_supply_prior' if case is None else 'route_or_mode_supply_prior'
        # A full vehicle with a compatible residual queue is an unavailable opportunity.
        # The extra denominator opportunity keeps a wholly full small proxy sample finite.
        skipped = blocked/(count-blocked+1) if count else 0
        extra = cohort[1] if cohort else headway*skipped
        return {'available':True,'model_id':RELEASE,'basis':'boarding_cohort' if cohort else basis,
                'supply_basis':basis,'extrapolated':not bool(local),'modeled_passages':count,
                'boarded_mass':cohort[0] if cohort else None,'load_ratio':load,
                'extra_wait_seconds':extra,'expected_skipped_services':extra/max(1,headway),
                'onboard_dwell':cohort[2] if cohort else None,'reference_headway_seconds':headway,
                'external_background_passengers_included':False}

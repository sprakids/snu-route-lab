"""Data-only, weekday-transfer city service clocks. Never identifies real buses."""
import bisect
import math
import statistics
from collections import OrderedDict
from datetime import datetime
from shuttle_timetable import KST

SCHEMA='snu_city_operations_v1'
HOLIDAYS={'2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'}

def finite(value,low=0,high=172800):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('city_operations_number')

def validate_operations(data,network,network_sha):
    if data.get('schema')!=SCHEMA or data.get('network_sha256')!=network_sha:
        raise ValueError('city_operations_network')
    if data.get('weekdays')!=list(range(5)) or data.get('transfer_estimate') is not True:
        raise ValueError('city_operations_scope')
    if data.get('includes_destination_dwell') is not True or data.get('dwell_added_separately') is not False or not isinstance(data.get('revision'),str) or not data['revision']:
        raise ValueError('city_operations_clock')
    sources=data.get('source_dates')
    if not isinstance(sources,list) or not sources or len(sources)>366:raise ValueError('city_operations_sources')
    for day in sources:datetime.strptime(day,'%Y-%m-%d')
    for field in ('term_start','term_end'):
        if field in data:datetime.strptime(data[field],'%Y-%m-%d')
    start,end=data['coverage_start_seconds'],data['coverage_end_seconds']
    finite(start,0,86400);finite(end,start+1,108000)
    routes={r['id']:r for r in network['routes']}
    if set(data.get('routes',{}))!=set(routes):raise ValueError('city_operations_routes')
    count=0
    for rid,spec in data['routes'].items():
        stops=spec['stops'];n=len(stops)
        if not 2<=n<=len(routes[rid]['stops']):raise ValueError('city_operations_stops')
        expected={s['seq']:s['id'] for s in routes[rid]['stops']}
        seqs=[s['seq'] for s in stops]
        if any(type(s) is not int for s in seqs) or seqs!=list(range(seqs[0],seqs[0]+n)):
            raise ValueError('city_operations_stop_order')
        if any(expected.get(s['seq'])!=s['id'] for s in stops):raise ValueError('city_operations_stops')
        if set(spec['departures'])!=set(map(str,range(5))) or set(spec['segment_profiles'])!=set(map(str,range(5))):
            raise ValueError('city_operations_days')
        for day in map(str,range(5)):
            departures=spec['departures'][day]
            if not isinstance(departures,list) or not 1<=len(departures)<=2000:raise ValueError('city_operations_departures')
            previous=-1
            for at in departures:
                finite(at,0,108000)
                if at<=previous:raise ValueError('city_operations_departures')
                previous=at
            cells=spec['segment_profiles'][day]
            if not 1<=len(cells)<=288:raise ValueError('city_operations_profiles')
            previous_end=None
            for row in cells:
                if len(row)!=3:raise ValueError('city_operations_profiles')
                a,b,seconds=row;finite(a,0,172799);finite(b,a+1,172800)
                if previous_end is not None and a!=previous_end:raise ValueError('city_operations_profile_gap')
                if len(seconds)!=n-1:raise ValueError('city_operations_segment_count')
                for value in seconds:finite(value,.001,7200)
                previous_end=b;count+=len(seconds)
            if cells[0][0]>start or cells[-1][1]<end:raise ValueError('city_operations_coverage')
    if count>300000:raise ValueError('city_operations_size')
    return data

class CityOperations:
    def __init__(self,data,model_id,calendar=None):
        self.data=data or {};self.model_id=model_id;self.calendar=calendar or {};self.cache=OrderedDict()

    def info(self):
        return {'available':bool(self.data),'model_id':self.model_id if self.data else None,
            'revision':self.data.get('revision'),'source_dates':self.data.get('source_dates',[]),
            'transfer_estimate':bool(self.data),'observed_operations':False,
            'weekdays':self.data.get('weekdays',[]),'destination_dwell_included':bool(self.data),
            'coverage_start_seconds':self.data.get('coverage_start_seconds'),
            'coverage_end_seconds':self.data.get('coverage_end_seconds')}

    def applicable(self,when):
        if not self.data:return False
        d=datetime.fromtimestamp(when,KST);date=d.date().isoformat();clock=(when-d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
        start=self.data.get('term_start',self.calendar.get('term_start','0001-01-01'))
        end=self.data.get('term_end',self.calendar.get('term_end','9999-12-31'))
        return d.weekday() in self.data['weekdays'] and start<=date<=end and date not in HOLIDAYS and self.data['coverage_start_seconds']<=clock<self.data['coverage_end_seconds']

    def index(self,route,index):
        spec=self.data.get('routes',{}).get(route['id']);stop=route['stops'][index]
        if spec:
            return next((i for i,s in enumerate(spec['stops']) if s['seq']==stop['seq'] and s['id']==stop['id']),None)

    @staticmethod
    def cell(spec,day,clock):
        return next((row[2] for row in spec['segment_profiles'][str(day)] if row[0]<=clock<row[1]),None)

    def segment_seconds(self,route,index,when):
        if not self.applicable(when):return None
        k=self.index(route,index);spec=self.data['routes'].get(route['id'])
        if k is None or k+1>=len(spec['stops']) or index+1>=len(route['stops']):return None
        target=route['stops'][index+1]
        if spec['stops'][k+1]['seq']!=target['seq'] or spec['stops'][k+1]['id']!=target['id']:return None
        d=datetime.fromtimestamp(when,KST);clock=when-d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        values=self.cell(spec,d.weekday(),clock)
        return values[k] if values is not None else None

    def timeline(self,rid,day):
        key=rid,day
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key]
        spec=self.data['routes'][rid];rows=[[] for _ in spec['stops']]
        for departure in spec['departures'][str(day)]:
            clock=departure;rows[0].append(clock)
            for k in range(len(rows)-1):
                values=self.cell(spec,day,clock)
                if values is None:break
                clock+=values[k];rows[k+1].append(clock)
        result=[sorted(values) for values in rows];self.cache[key]=result
        while len(self.cache)>24:self.cache.popitem(last=False)
        return result

    def service(self,route,index,ready,*,anchor=None,blocked=()):
        if not self.applicable(ready):return None
        k=self.index(route,index)
        if k is None:return None
        d=datetime.fromtimestamp(ready,KST);mid=d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        values=self.timeline(route['id'],d.weekday())[k]
        if not values:return None
        shift=0.
        if anchor is not None:
            nearest=min(values,key=lambda t:abs(mid+t-anchor))
            shift=anchor-mid-nearest
        after=max([ready,*[t+.001 for t in blocked]])
        j=bisect.bisect_left(values,after-mid-shift)
        if j>=len(values):return None
        leave=mid+values[j]+shift
        if not self.applicable(leave):return None
        gaps=[b-a for a,b in zip(values[max(0,j-2):j+3],values[max(0,j-2)+1:j+3]) if b>a]
        nominal=statistics.median(gaps) if gaps else route['interval_minutes']*60
        return {'departure_at':leave,'headway_seconds':nominal,'source':'weekday_transfer_operations',
            'future_departures_at':[mid+t+shift for t in values[j:j+12] if self.applicable(mid+t+shift)],
            'last_service_at':mid+values[-1]+shift,'phase_conditioned':anchor is not None,
            'operations':self.info()}

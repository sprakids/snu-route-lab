"""R-only shuttle corrections from completed, interval-censored previous days."""
import copy, hashlib, json, math, statistics
from datetime import datetime
from automatic_queue import AutomaticQueue, simulate, grade_signals, multiplier, pressure, dispatches
from shuttle_timetable import KST
from shuttle_live import CATALOG
from shuttle_clock import WINDOWS, FIXED

def supported(rows,asof):
    rows=[r for r in rows if isinstance(r.get('known_at'),(int,float)) and r['known_at']<=asof and
          all(isinstance(r.get(k),(int,float)) and math.isfinite(r[k]) for k in ('lo','hi','seconds')) and
          0<=r['lo']<=r['seconds']<=r['hi'] and 0<r['seconds']<=3600]
    days=sorted({r['day'] for r in rows})
    if len(rows)<5 or len(days)<2:return None
    seconds=statistics.median(r['seconds'] for r in rows)
    if statistics.median(r['hi']-r['lo'] for r in rows)>seconds*.75:return None
    values=sorted(r['seconds'] for r in rows)
    return {'seconds':seconds,'n':len(rows),'days':days,
            'range_seconds':[min(r['lo'] for r in rows),max(r['hi'] for r in rows)],
            'interval_samples':values,'time_basis':'schematic_stop_area_detection_intervals'}

def anchor_for(rid,stop):
    spec=next((r for r in CATALOG['routes'] if 'shuttle-'+r['id']==rid),None)
    if not spec:return None
    return next((i for i,a in enumerate(spec['anchors']) if a.get('stop_id',a.get('id'))==stop),None)

def wanted_pairs(app,frame):
    pairs={}
    for candidate in (frame.get('baseline') or {}).get('candidates',[]):
        for leg in candidate['legs']:
            route=app.planner.by_id.get(leg['route_id'])
            if not route or route.get('kind')!='shuttle':continue
            start=next((s for s in route['stops'] if s['seq']==leg['from_seq']),{})
            end=next((s for s in route['stops'] if s['seq']==leg['to_seq']),{})
            a,b=start.get('anchor_index'),end.get('anchor_index')
            if a is not None and b is not None:pairs.setdefault(route['id'],set()).add(f'{a}:{b}')
    model=app.transit.automatic_queue
    source=model.current() if hasattr(model.operations,'profile') else model
    for rid,route in source.data['routes'].items():
        for i in range(1,len(route.get('offsets',[]))):
            a=anchor_for(rid,route['stops'][(i-1)%route['n']]['id']);b=anchor_for(rid,route['stops'][i%route['n']]['id'])
            if a is not None and b is not None:pairs.setdefault(rid,set()).add(f'{a}:{b}')
    return {rid:sorted(values) for rid,values in pairs.items()}

class ShuttleTravel:
    def __init__(self,baseline,profile,asof):self.baseline,self.profile,self.asof=baseline,profile,asof
    def __getattr__(self,name):return getattr(self.baseline,name)
    def estimate(self,route,i,j,when,snapshot=None,live=False):
        base=self.baseline.estimate(route,i,j,when,snapshot,live)
        if route.get('kind')!='shuttle' or not base.get('available'):return base
        a,b=route['stops'][i].get('anchor_index'),route['stops'][j].get('anchor_index')
        p=supported(self.profile.get('routes',{}).get(route['id'],{}).get('rides',{}).get(f'{a}:{b}',[]),self.asof)
        if not p:return base
        return {**base,'seconds':max(1,round(p['seconds'])),'source':'R_shuttle_completed_trip_intervals',
                'label':'셔틀 과거 구간 통과시간 기반 추정','range_seconds':p['range_seconds'],
                'range_kind':'interval_censored_historical_spread','empirical_shuttle':p,
                'terminal_park_time_included':False,'intermediate_dwell_included':True}

class ShadowQueue(AutomaticQueue):
    def __init__(self,historical,*,data,profile,asof):
        super().__init__(historical,data=data);self.profile=profile;self.asof=asof;self.corrections=[]

    def profiles(self,rid,at,snapshot,live,asof):
        date=datetime.fromtimestamp(at,KST);mid=date.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        source=self.data['routes'][rid];route=copy.deepcopy(source)
        learned=self.profile.get('routes',{}).get(rid,{})
        if not learned.get('rides') and not learned.get('headways'):
            return super().profiles(rid,at,snapshot,live,asof)
        # Correct complete departures-to-arrivals, not the time a bus parks at
        # the administration terminal. A missing pair preserves the V11 offset.
        cumulative=[0.];changed=False
        for i in range(1,len(route['offsets'])):
            a=anchor_for(rid,route['stops'][(i-1)%route['n']]['id']);b=anchor_for(rid,route['stops'][i%route['n']]['id'])
            p=supported(learned.get('rides',{}).get(f'{a}:{b}',[]),asof)
            seconds=p['seconds'] if p else source['offsets'][i]-source['offsets'][i-1]
            cumulative.append(cumulative[-1]+seconds)
            if p:changed=True;self._note(rid,'ride_offset',f'{a}:{b}',p)
        if changed:route['offsets']=cumulative
        anchor=anchor_for(rid,route['stops'][route['anchor']]['id'])
        rows=[r for k,values in learned.get('headways',{}).items() if k.startswith(f'departure:{anchor}:') for r in values]
        provider=rid.removeprefix('shuttle-')
        target_second=(at-mid)
        regime=next(((a*60,b*60) for a,b,_ in WINDOWS.get(provider,[]) if a*60<=target_second<b*60),None)
        if regime:
            def same_regime(row):
                moment=datetime.fromtimestamp(row.get('at',row['known_at']),KST)
                second=moment.hour*3600+moment.minute*60+moment.second
                return regime[0]<=second<regime[1]
            rows=[r for r in rows if same_regime(r)]
        head=supported(rows,asof)
        if head and regime:head['regime_seconds']=regime
        if head:self._note(rid,'departure_headway',str(anchor),head)
        if not head and not changed:return super().profiles(rid,at,snapshot,live,asof)
        signals=[grade_signals(node,snapshot.get('vehicles',[]),asof) if live and not self.config.get('model_only') else [] for node in route['stops']]
        signature=hashlib.sha256(json.dumps(signals,sort_keys=True).encode()).hexdigest()[:16]
        key=(rid,date.date().isoformat(),date.hour,signature,'R_empirical_shuttle')
        if key in self.cache:return self.cache[key],signals,mid
        def factor(index,seconds):
            if self.config.get('model_only'):return 1.
            h=self.historical_signal(rid,index,mid+seconds)['percentile']
            return multiplier(h,pressure(signals[index],mid+seconds,self.config),self.config)
        values=[]
        for scenario in self.config['sensitivity']:
            for phase in self.config['phases']:
                clock=self.empirical_clock(rid,phase,date.hour,head)
                values.append({'scenario':scenario,**simulate(route,date.weekday(),phase,scenario['demand'],scenario['reserve'],factor,self.config['step_seconds'],dispatch_times=clock)})
        self.cache[key]=values
        while len(self.cache)>12:self.cache.popitem(last=False)
        return values,signals,mid

    def _note(self,rid,kind,section,p):
        key=(rid,kind,section)
        if any((x['route_id'],x['kind'],x['section'])==key for x in self.corrections):return
        self.corrections.append({'route_id':rid,'kind':kind,'section':section,'n':p['n'],'days':p['days'],
                                 'seconds':round(p['seconds'],3),'range_seconds':p['range_seconds'],
                                 'operating_V11_changed':False})

    @staticmethod
    def empirical_clock(rid,phase,hour,head):
        base=dispatches(rid,phase);provider=rid.removeprefix('shuttle-')
        if not head or provider in FIXED or provider not in WINDOWS:return base
        # Preserve fixed clocks, last departures, capacities and paired batches.
        lo,hi=max(0,(hour-1)*3600),min(86400,(hour+2)*3600)
        if head.get('regime_seconds'):lo=max(lo,head['regime_seconds'][0]);hi=min(hi,head['regime_seconds'][1])
        windows=[(max(start*60,lo),min(end*60,hi)) for start,end,_ in WINDOWS[provider] if max(start*60,lo)<min(end*60,hi)]
        out=[t for t in base if not any(a<=t<b for a,b in windows)]
        samples=head['interval_samples'];mean=statistics.mean(samples)
        for a,b in windows:
            t=a+phase*mean;i=int(phase*len(samples))%len(samples)
            while t<b:
                out.append(t);t+=max(30,samples[i%len(samples)]);i+=1
        return sorted(out)

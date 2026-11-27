"""Known service headways in choice perception; no future queue/load forecast.

The inherited physical Prediction remains immutable. Empty-service calendars are
exogenous scenario inputs, not observations of future realized boarding capacity.
"""
from dataclasses import replace
import bisect,math
from perception import perceived_without_transfer_wait


def residual_reference(times,ready):
    """E[residual]=sum(h*h)/(2*sum(h)), with an hour-local calendar sample.

    Whole-calendar gaps are a disclosed fallback if the hour has no midpoints;
    never substitute the exact next departure. Duplicate departures form one
    opportunity. A one-departure calendar cannot identify a headway.
    """
    values=sorted(set(times));gaps=[(a,b,b-a) for a,b in zip(values,values[1:]) if b>a]
    if not gaps:raise ValueError('Cannot infer nominal headway from fewer than two departures')
    hour=math.floor(ready/3600)*3600
    local=[h for a,b,h in gaps if hour<=(a+b)/2<hour+3600]
    selected=local or [h for a,b,h in gaps]
    return math.fsum(h*h for h in selected)/(2*math.fsum(selected)),('hour' if local else 'calendar_fallback')


class NominalTransfers:
    def __init__(self,schedule,vehicles,node_for,config):
        self.schedule=schedule;self.vehicles=vehicles;self.node_for=node_for
        self.preparation=config['preparation_seconds'];self.times={};self.references={}
        self.calls=0;self.future_rows=0;self.fallback_rows=0

    def intervals(self,pred,stages):
        timeline=pred.boarding_timeline
        if len(timeline)<=1:return (),()
        chain=list(stages);old_removed=0.;nominal_added=0.;intervals=[];details=[]
        for i,row in enumerate(timeline):
            if not chain:raise ValueError('Forecast has more boardings than its policy')
            stage=chain[0];entries=stage.get('pool',[stage])
            chosen=next((e for e in entries if e['rid']==row['route'] and e['board']==row['board_index']),None)
            if chosen is None:raise ValueError('Forecast service does not match its policy')
            if i:
                node=self.node_for(stage)
                services=frozenset((e['rid'],e['board']) for e in entries)
                key=(node,services)
                if key not in self.times:
                    self.times[key]=sorted({when for when,vid,k in self.schedule[node]
                        if (self.vehicles[vid]['rid'],k) in services})
                # Remove preceding unseen exact transfer phases before choosing
                # an arrival-hour reference; retain the current first queue.
                arrival=row['arrival']-old_removed+nominal_added
                cell=(key,int((arrival+self.preparation)//3600))
                if cell not in self.references:self.references[cell]=residual_reference(self.times[key],arrival+self.preparation)
                waiting,basis=self.references[cell];interval=self.preparation+waiting
                intervals.append(interval)
                details.append({'node':node,'expected_wait_seconds':waiting,'preparation_seconds':self.preparation,
                    'reference_basis':basis,'queue_anticipated':False,'capacity_anticipated':False,
                    'second_exact_departure_phase_used':False})
                old_removed+=row['time']-row['arrival'];nominal_added+=interval
            chain=chosen.get('continuation_stages',chain[1:])
        self.calls+=1;self.future_rows+=len(intervals)
        self.fallback_rows+=sum(d['reference_basis']=='calendar_fallback' for d in details)
        return tuple(intervals),tuple(details)

    def outlook(self,pred,stages):
        # This validation also proves that the source components/timeline agree.
        base=perceived_without_transfer_wait(pred)
        intervals,details=self.intervals(pred,stages)
        if not intervals:return pred
        preparation=len(intervals)*self.preparation
        waiting=math.fsum(intervals)-preparation
        return replace(base,eta=base.eta+waiting+preparation,wait=base.wait+waiting,
            prep=base.prep+preparation,
            wait_squared=base.first_wait**2+math.fsum(v*v for v in intervals),
            wait_cubed=base.first_wait**3+math.fsum(v*v*v for v in intervals))

    def primary_extension(self,pred,stages,primary_node,physical_prefix):
        indices=[i for i,r in enumerate(pred.boarding_timeline) if r['node']==primary_node]
        if not indices or indices[-1]==0:return physical_prefix,()
        intervals,details=self.intervals(pred,stages);target=indices[-1]
        # The primary boarding delay itself is included, just like a direct
        # first-stage mainline boarding. Waits AFTER that boarding are irrelevant
        # to this explicitly boarding-focused initial heuristic.
        return physical_prefix+math.fsum(intervals[:target]),details[:target]

    def report(self):
        return {'calls':self.calls,'future_rows':self.future_rows,'calendar_fallback_rows':self.fallback_rows,
            'reference':'sum(h^2)/(2*sum(h)); hourly, otherwise whole service calendar',
            'future_queue_or_capacity_used_by_this_reference':False,'exact_future_wait_phase_in_cost':False,
            'physical_forecast_modified':False}

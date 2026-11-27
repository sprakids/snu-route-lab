"""Additional diagnostics only; never feeds the simulation or clips a journey."""
import math
def quantile(rows,q):
    total=math.fsum(w for _,w in rows)
    if not total:return None
    sofar=0.
    for x,w in sorted(rows):
        sofar+=w
        if sofar>=q*total:return x
    return rows[-1][0]
def diagnostics(audit,start,end):
    samples={k:[] for k in ('walk_min','cumulative_wait_min','total_min','changes')}
    rawmax=0.;raw_over=0.;outside=0.;outside_max=0.;unfinished=0.
    for trip in audit['legs']:
        w=trip['weight'];legs=trip['legs']
        if trip['unserved']:unfinished+=w
        else:
            samples['walk_min'].append((math.fsum(l[2]-l[1] for l in legs if l[0]==0)/60,w))
            samples['cumulative_wait_min'].append((math.fsum(l[2]-l[1] for l in legs if l[0]==1)/60,w))
            samples['total_min'].append(((legs[-1][2]-trip['start'])/60,w))
            samples['changes'].append((len(trip['history']),w))
        pending=None;episodes=[]
        for leg in legs:
            if leg[0]==1:
                if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                else:
                    if pending:episodes.append(pending)
                    pending=[leg[4],leg[1],leg[2]]
            else:
                if pending:episodes.append(pending);pending=None
        if pending:episodes.append(pending)
        for n,a,b in episodes:
            b=min(b,end) if trip['unserved'] else b
            t=max(0.,b-a)/60;rawmax=max(rawmax,t)
            if t>20+1e-7:raw_over+=w
            if a>=end or b<=start:
                outside_max=max(outside_max,t)
                if t>20+1e-7:outside+=w
    return {'unserved_trip_weight':unfinished,'finished_trip_quantiles':{
        k:{'mean':math.fsum(x*w for x,w in rows)/math.fsum(w for x,w in rows) if rows else None,
           'p50':quantile(rows,.5),'p90':quantile(rows,.9),'p95':quantile(rows,.95),'p99':quantile(rows,.99),
           'maximum':max((x for x,w in rows),default=None)} for k,rows in samples.items()},
        'all_recorded_time_max_continuous_wait_min':rawmax,'all_recorded_time_over20_episode_weight':raw_over,
        'outside_display_window_max_continuous_wait_min':outside_max,'outside_display_window_over20_episode_weight':outside,
        'time_window_note':'Primary criterion uses episodes overlapping11:20-23:10. Additional all-recorded metrics expose earlier/later initialization trajectories. No exposure deleted.',
        'unserved_quantile_note':'Finished-trip quantiles are explicitly conditional; unserved mass is separately reported, not silently included as completed.'}

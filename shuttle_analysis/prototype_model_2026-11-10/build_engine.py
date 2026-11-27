"""One-time construction from a frozen transport core, with explicit hook seams.

The generated engine.py is private editable source, not code patched at runtime.
The frozen v9 source and protected hashes remain untouched.
"""
from artifacts import ROOT

def build():
    assert not (ROOT/'engine.py').exists(), 'One-time constructor: preserve the reviewed engine.py and its subsequent live-FIFO fixes'
    source=(ROOT/'frozen/v9_engine.py').read_text(encoding='utf8')
    def replace(a,b):
        nonlocal source
        assert a in source,a[:90];source=source.replace(a,b,1)
    a=source.index('import capacity_model as base');b=source.index('\n\ndef stable_uniform',a)
    source=source[:a]+'''import artifacts as base
from artifacts import ROOT as WORK,START,END,EPS
import metrics as v4
from policy import attach_policy
from capacity import seats,balance
OUT=WORK/'unused_public_output'
SETTINGS={'max_switches':None,'recheck_seconds':60,'minimum_gain_seconds':120,'cooldown_seconds':180}
'''+source[b:]
    replace("settings={**SETTINGS,**(settings or {})};prepared=bundle['prepared'];common=prepared['common']", "settings={**SETTINGS,**(settings or {})};prepared=bundle['prepared'];common=prepared['common']\n    config=bundle['prototype_config']")
    replace("clocks=planned_departures(info['plan']) if info.get('city') else base.dispatches(rid,scenario)","clocks=bundle['supply'][scenario][rid]")
    replace("'realized_change_count':len(state['history']),'full_passes_seen':state['full_passes']})", "'realized_change_count':len(state['history']),'full_passes_seen':state['full_passes'],\n            'parent_id':bundle['parent_ids'].get(str(state['plan'][0]),state['plan'][0]),\n            'stop_arrival_at':state['arrival'],'ready_at':state['ready_time'],\n            'boarding_at':t if outcome=='boarded' else None,'leave_at':t})")
    replace("if t+1200<=END:push(t+1200,2,'patience',(state,state['visit']))", "if config['behavior']=='v9_frozen' and t+1200<=END:push(t+1200,2,'patience',(state,state['visit']))")
    replace("'queued':False,'done':False,'check_version':0}","'queued':False,'done':False,'check_version':0,\n               'traits':policy.make_traits(plan[0]),'fare_ledger':policy.empty_ledger(),\n               'review_ordinal':0,'hazard_clock':None}")
    seam="    for plan in prepared['plans'][day]:"
    replace(seam,"""    policy=attach_policy(bundle,config,node_for,current_stage,forecast,waiting_before,
        schedule,vehicles,queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions)
    if config['behavior']!='v9_frozen':
        maybe_switch=policy.maybe_switch
        reschedule=policy.reschedule
    for plan in prepared['plans'][day]:""")
    replace("        walk_next(state,plan[4],*plan[5])", "        if config['origin_choice']:push(plan[4],0,'depart',state)\n        else:walk_next(state,plan[4],*plan[5])")
    replace("        if kind=='arrive':", "        if kind=='depart':\n            state=payload;policy.initial_choice(state,t);walk_next(state,t,*state['plan'][5]);continue\n        if kind=='arrive':")
    replace("        if kind=='ready':\n            state=payload\n            if state['done']:continue", "        if kind=='ready':\n            state=payload\n            if state['done'] or not state.get('preparing'):continue")
    replace("reschedule(state,t+settings['recheck_seconds']);continue", "reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds']);continue")
    replace("if not maybe_switch(state,t,'queue_recheck'):reschedule(state,t+settings['recheck_seconds'])", "if not maybe_switch(state,t,'queue_recheck'):reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds'])")
    replace("off+=state['w'];stage=current_stage(state);state['stage']+=1", "off+=state['w'];stage=current_stage(state);policy.alighted(state,rid,t);state['stage']+=1")
    replace("queue=queues[node];available=vehicle['cap']-vehicle['load']", "queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()")
    replace("if chosen is None or available<=EPS:continue\n                w=", "if chosen is None or available<=EPS:continue\n                if config['boarding_choice'] and not policy.accept_boarding(state,chosen,vehicle,k,t,available):\n                    voluntary.add(state['sid']);continue\n                w=")
    replace("record_wait(take,t,'boarded')", "policy.boarded(take,rid,chosen,t,end)\n                record_wait(take,t,'boarded')")
    replace("if stage_choice(current_stage(state),rid,k) is None:continue\n                eligible_left", "if stage_choice(current_stage(state),rid,k) is None or state['sid'] in voluntary:continue\n                eligible_left")
    replace("reschedule(state,t+.001)","reschedule(state,t if config['behavior']!='v9_frozen' else t+.001)")
    replace("vehicle['last_stop']=k\n        assert", "balance(vehicle['cap'],before,off,boarded,vehicle['load'])\n        vehicle['last_stop']=k\n        assert")
    replace("data.update(schema_version=5,city_capacity_applied=True,", "data.update(schema_version='prototype_v1',prototype_config=config,policy_report=policy.report(),city_capacity_applied=True,")
    replace("base.public(f'{scenario}-{base.DAYS[day]}.json',data)","base.packed(WORK/f'{scenario}-{base.DAYS[day]}.json.gz',data)")
    replace("'switches':decisions,'gate_boardings':gate_boardings,'behavior_decisions':behavior_decisions,", "'switches':decisions,'gate_boardings':gate_boardings,'behavior_decisions':behavior_decisions,\n            'prototype_config':config,'policy_report':policy.report(),'boarding_choices':policy.boarding_choices,\n            'parent_ids':bundle['parent_ids'],\n            'vehicles':[{'id':v['id'],'rid':v['rid'],'cap':v['cap'],'t0':v['t0'],'legs':v['legs']} for v in vehicles],")
    replace("'start':s['plan'][4],'legs':s['legs']}","'start':s['plan'][4],'legs':s['legs'],'traits':s['traits'].record(),'finish_time':s['finish_time'],\n                     'fare_paid':s.get('fare_paid',0.),'parent_id':bundle['parent_ids'].get(str(s['plan'][0]),s['plan'][0])}")
    (ROOT/'engine.py').write_text(source,encoding='utf8')
    print('Created isolated engine.py from frozen core; no runtime source patching')

if __name__=='__main__':build()

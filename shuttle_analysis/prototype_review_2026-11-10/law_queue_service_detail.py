"""Distinguish missing service, denied boarding and voluntary declines in the ledgers."""
from pathlib import Path
import gzip,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def main():
    target=ROOT/'law_queue_service_detail.json';assert not target.exists()
    original=read(ROOT/'law_queue_diagnostic.json');rows=[]
    for proof in original['proof']:
        folder=Path(proof['folder']);audit=read(folder/'audit-regular-mon.json.gz')
        for r in original['rows']:
            if r['behavior']!=proof['behavior']:continue
            at=r['queue_peak_second'];start=at-900;n=r['node']
            events=[e for e in audit['events'] if e[1]==n and start<=e[0]<=at]
            declines=[d for d in audit['boarding_choices'] if d['node']==n and start<=d['time']<=at]
            balance=r['queue_at_15min_start_weight']+r['inflow_visit_weight_prior15min']-r['boarding_weight_prior15min']-r['walk_away_visit_weight_prior15min']
            assert abs(balance-r['maximum_queue_weight'])<2e-5
            assert abs(math.fsum(e[6] for e in events)-r['boarding_weight_prior15min'])<2e-5
            rows.append({**r,'flow_balance_error':balance-r['maximum_queue_weight'],
                         'all_vehicle_stop_events_in_window':len(events),
                         'voluntary_decline_event_weight':math.fsum(d['weight'] for d in declines),
                         'vehicle_events':[{'at':e[0],'route':e[11],'capacity':e[3],'free_after_alight_before_local_board':e[3]-e[4]+e[5],
                                            'boarded':e[6],'denied_weight':e[8]} for e in events]})
        del audit
    target.write_text(json.dumps({'status':'POSTHOC_MODEL_FLOW_IDENTITY','rows':rows,'not_independent_field_evidence':True,
        'vehicle_event_is_all_lines_at_physical_stop_not_necessarily_eligible_for_every_waiter':True,
        'declines_and_denials_count_events_not_unique_people':True,'underlying_diagnostic_preserved':True},ensure_ascii=False,indent=2),encoding='utf8')
    print('LAW_SERVICES_RECONCILED',json.dumps([{k:r[k] for k in ('behavior','ars','queue_peak_hms','all_vehicle_stop_events_in_window','voluntary_decline_event_weight','flow_balance_error')} for r in rows],ensure_ascii=False))
if __name__=='__main__':main()

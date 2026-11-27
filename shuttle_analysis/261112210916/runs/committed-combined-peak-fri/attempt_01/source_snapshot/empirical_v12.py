"""Typed historical evidence: ordinal crowd risk is never a passenger count."""
from collections import Counter
import math

def api_grade(code):
    value=str(code)
    return int(value)-3 if value in ('3','4','5','6') else None

def ordinal_grade(value):
    return int(value) if str(value) in ('0','1','2','3') else None

def period(second):
    return 'peak' if 54000<=second<68400 else 'early' if second<54000 else 'late'

class Evidence:
    def __init__(self,data):
        self.data=data;self.calls=Counter();self.cache={}
    def headways(self,rid,seq,second):
        h=int(second//3600)%24
        cell=self.data['headways'].get(f'{rid}|{seq}|{h}')
        if cell and len(cell['seconds'])>=5:return cell['seconds'],'hour_training'
        cell=self.data['headway_periods'].get(f'{rid}|{seq}|{period(second)}')
        if cell and len(cell['seconds'])>=5:return cell['seconds'],'period_training'
        return None,'insufficient_or_missing'
    def time_spread(self,rid,left,right,second):
        cell=self.data['segment_samples'].get(f'{rid}|{left}|{right}|{int(second//3600)%24}')
        if not cell:return {'n':0,'p10_seconds':None,'p90_seconds':None}
        values=sorted(cell['seconds']);n=len(values)
        return {'n':n,'p10_seconds':values[max(0,math.ceil(.1*n)-1)],'p90_seconds':values[max(0,math.ceil(.9*n)-1)]}
    def context(self,rid,board,target,at,times):
        seqs=self.data['route_sequences'].get(rid)
        if not seqs:return None,{'crowd_source':'not_a_city_observed_route'}
        hour=int(at//3600)%24;key=(rid,board,target,hour)
        if key in self.cache:
            self.calls['context_cache']+=1
            probabilities,extra=self.cache[key]
        else:
            grade=self.data['grades'].get(f'{rid}|{seqs[board]}|{hour}')
            counts=grade['counts'] if grade else [0,0,0,0];mass=sum(counts)
            p=[x/mass for x in counts] if mass else None
            probabilities=[];transition_n=0
            for k in range(board,target):
                probabilities.append(sum(p[2:]) if p else None)
                if p and k+1<len(seqs):
                    matrix=self.data['transitions'].get(f'{rid}|{seqs[k]}|{seqs[k+1]}|{hour}')
                    if matrix:
                        updated=[0.]*4
                        for level,row in enumerate(matrix['counts']):
                            n=sum(row)
                            if n:
                                transition_n+=n
                                for j,x in enumerate(row):updated[j]+=p[level]*x/n
                            else:updated[level]+=p[level]
                        p=updated
            hw,hw_source=self.headways(rid,seqs[board],at)
            full=self.data['full_flags'].get(f'{rid}|{seqs[board]}|{hour}',{})
            extra={'crowd_source':'historical_ordinal_distribution_and_transition' if mass else 'missing_observed_grade_model_occupancy_scenario_fallback',
                   'initial_grade_n':mass,'transition_count_context':transition_n,
                   'headway_source':hw_source,'headway_interval_n':len(hw) if hw else 0,
                   'random_arrival_empty_queue_wait_reference_seconds':sum(x*x for x in hw)/(2*sum(hw)) if hw else None,
                   'full_flag_known_n':full.get('known_n',0),
                   'full_flag_probability':full.get('full_n',0)/full['known_n'] if full.get('known_n') else None,
                   'time_spread':self.time_spread(rid,seqs[board],seqs[min(board+1,len(seqs)-1)],at),
                   'reference_is_not_personal_queue_wait':True,'ordinal_grade_is_not_occupancy_count':True}
            self.cache[key]=(probabilities,extra)
        self.calls[extra['crowd_source']]+=1
        exposure=None
        if probabilities and all(p is not None for p in probabilities):
            exposure=sum((times[k+1]-times[k])*probabilities[k-board] for k in range(board,target))
        return exposure,extra
    def report(self):
        return {'training_dates':self.data['training_dates'],'calls_are_model_queries_not_people':dict(self.calls),
          'missing_crowd_routes':self.data['missing_crowd_routes'],'ordinal_to_people_conversion':False,
          'full_flag_to_seat_conversion':False,'headway_reference_is_not_individual_wait':True,
          'severe_grade_discomfort_mapping_is_uncalibrated_choice_scenario':True}

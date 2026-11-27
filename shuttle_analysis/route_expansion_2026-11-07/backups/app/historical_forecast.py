"""Bundled weekday load-sum forecast, independent of live APIs and persistence."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,math

KST=timezone(timedelta(hours=9))

class HistoricalForecast:
    def __init__(self,path=None):
        self.payload=json.loads((Path(path) if path else Path(__file__).parent/'data/weekday_history.json').read_text(encoding='utf-8'))
        assert self.payload['schema']=='snu_weekday_history_v1'
        self.segments={tuple(map(str,s)):i for i,s in enumerate(self.payload['segments'])}
        self.profiles={(int(r[0]),int(r[1])):r for r in self.payload['profiles']}
        assert len(self.segments)==259 and len(self.profiles)==2849
        for row in self.profiles.values():
            assert len(row[3])==len(row[4])==5
            assert all(math.isfinite(v) and v>=0 for v in row[3])

    def info(self):
        p=self.payload;dates=p['history_dates']
        return {k:p[k] for k in ('model_id','model','label','timezone','hours_inclusive','weekdays','source','source_url','unit','unit_label','interpretation')} | {
            'configured':True,'history_days':len(dates),'history_start':min(dates),'history_end':max(dates),
            'shrinkage_k':p['shrinkage_k'],'segments':len(self.segments),'live_observation':False,
            'scope_label':'평일 12~22시 · 요일별 과거 이용량 예측'}

    def point(self,route_id,from_seq,from_stop,to_stop,at):
        result={'available':False,'model':self.payload['model'],'model_id':self.payload['model_id'],'unit':'hourly_segment_sum_load'}
        if not math.isfinite(float(at)):raise ValueError('유효한 시각이 필요합니다.')
        t=datetime.fromtimestamp(float(at),KST)
        if t.weekday()>=5:return result|{'reason':'주말 예측 자료가 없습니다.'}
        if not 12<=t.hour<=22:return result|{'reason':'평일 12~22시에 제공하는 예측입니다.'}
        ident=(str(route_id),str(int(from_seq)),str(from_stop),str(to_stop))
        index=self.segments.get(ident)
        if index is None:return result|{'reason':'일치하는 노선·순서·구간의 과거 자료가 없습니다.'}
        profile=self.profiles.get((index,t.hour))
        if profile is None:return result|{'reason':'해당 구간·시간의 과거 자료가 없습니다.'}
        return result|{'available':True,'predicted_sum_load':profile[3][t.weekday()],
                       'pooled_mean':profile[2],'same_weekday_days':profile[4][t.weekday()],
                       'date':t.date().isoformat(),'weekday':t.weekday(),'hour':t.hour,
                       'route_id':ident[0],'from_seq':int(from_seq),'from_stop_id':ident[2],'to_stop_id':ident[3]}

    @staticmethod
    def summarize(segments,total,reason=None):
        valid=[p for p in segments if p.get('available')]
        return {'available':bool(valid),'model':'weekday_history','label':'요일별 과거 평균',
                'mean_sum_load':math.fsum(p['predicted_sum_load'] for p in valid)/len(valid) if valid else None,
                'max_sum_load':max((p['predicted_sum_load'] for p in valid),default=None),
                'matched_segments':len(valid),'total_segments':total,'partial':bool(valid) and len(valid)<total,
                'unit':'mean_hourly_segment_sum_load','unit_label':'시간당 구간 재차합 평균',
                'reason':None if valid else reason or next((p.get('reason') for p in segments if p.get('reason')),'예측 가능한 시내버스 구간이 없습니다.'),
                'segments':segments}

    def attach(self,plan,planner):
        """Add evidence without turning hourly volume into crowd cost or ETA."""
        plan['historical_prediction']=self.info()
        for candidate in plan['candidates']:
            segments=[];total=0;shuttles=0
            for leg in candidate['legs']:
                if leg['type']!='bus':continue
                route=planner.by_id[leg['route_id']]
                if route.get('kind')=='shuttle':
                    shuttles+=1;leg['historical_forecast']=self.summarize([],0,'셔틀 재차합 예측 자료가 없습니다.');continue
                by_seq={int(s['seq']):i for i,s in enumerate(route['stops'])}
                i=by_seq[int(leg['from_seq'])];j=by_seq[int(leg['to_seq'])]
                modeled=planner.ride_seconds(route,i,j)
                scale=leg['seconds']/modeled if modeled else 1.
                values=[]
                for k in range(i,j):
                    a,b=route['stops'][k:k+2]
                    entry=leg['departure_at']+planner.ride_seconds(route,i,k)*scale if k>i else leg['departure_at']
                    values.append(self.point(route['id'],a['seq'],a['id'],b['id'],entry))
                leg['historical_forecast']=self.summarize(values,j-i)
                segments.extend(values);total+=j-i
            reason='도보 경로는 버스 이용량 예측 대상이 아닙니다.' if not candidate['route_names'] else '셔틀 재차합 예측 자료가 없습니다.' if shuttles and not total else None
            summary=self.summarize(segments,total,reason)
            summary['shuttle_legs_without_history']=shuttles
            candidate['historical_forecast']=summary
        return plan

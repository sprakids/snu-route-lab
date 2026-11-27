"""Dependency-free inference for the frozen research model; no keys or live data.

Values are hourly total passenger-segment sums, never per-bus crowding ratios.
"""
from pathlib import Path
from datetime import datetime
import json,hashlib

KEY=('route_id','sta_sn','from_stop_id','to_stop_id','hour')
def key(row):return tuple(str(row[k]) for k in KEY)

class FrozenPredictor:
    def __init__(self,model_path):
        p=Path(model_path);self.artifact=json.loads(p.read_text(encoding='utf-8'))
        assert self.artifact['schema']=='snu_history_class_background_v1'
        a=self.artifact
        self.base={key(r):r for r in a['tables']['base']}
        self.wh={(int(r['weekday']),)+key(r):r for r in a['tables']['weekday']}
        self.bg={(int(r['weekday']),r['route_id'],int(r['hour'])):float(r['background_ratio']) for r in a['tables']['background']}
        self.classes={(int(r['weekday']),)+key(r):float(r['class_flow']) for r in a['class_template']}
        self.models=a['models']
        self.model_sha256=hashlib.sha256(p.read_bytes()).hexdigest()

    def predict(self,date,route_id,sta_sn,from_stop_id,to_stop_id,hour):
        weekday=datetime.strptime(str(date),'%Y%m%d').weekday();hour=int(hour)
        lo,hi=self.artifact['prediction_hours']
        if weekday>=5 or not lo<=hour<=hi:raise ValueError('Supported scope is weekdays, hours12..22')
        rid=str(route_id);k=(rid,str(int(sta_sn)),str(from_stop_id),str(to_stop_id),str(hour))
        if k not in self.base:raise LookupError('No exact trained route/sequence/endpoints/hour key')
        r=self.base[k];H=float(r['H']);wk=(weekday,)+k
        ratio=self.bg.get((weekday,rid,hour),1.)
        c0=self.classes.get(wk,0.)-float(r['C0'])
        prev=(weekday,)+k[:-1]+(str(hour-1),)
        c1=self.classes.get(prev,0.)-float(r['C1'])
        bg=H*(ratio-1.);out={}
        for name,params in self.models.items():
            if name=='history_only':value=H
            elif name=='weekday_history':
                w=self.wh.get(wk);n=float(w['weekday_n']) if w else 0.
                weight=n/(n+float(params['k'])) if n else 0.
                value=H+weight*((float(w['weekday_mean']) if w else H)-H)
            else:
                a,b,c=map(float,params['coefficients'][rid]);value=max(0.,H+a*bg+b*c0+c*c1)
            out[name]=value
        return out

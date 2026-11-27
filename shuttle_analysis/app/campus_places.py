"""Pinned public campus coordinates, kept separate from inferred outdoor access."""
import json,math
from pathlib import Path

class CampusPlaces:
    def __init__(self,path=None):
        self.data=json.loads((Path(path) if path else Path(__file__).parent/'data/campus_places.json').read_text(encoding='utf-8'))
        self.entries=self.data['buildings'];self.by_id={x['id']:x for x in self.entries}
        if len(self.by_id)!=len(self.entries):raise ValueError('Duplicate campus building IDs')
        for b in self.entries:
            for p in [b,b['routing_point'],b['access']]:
                if not (math.isfinite(p['lat']) and math.isfinite(p['lon']) and 37.438<=p['lat']<=37.486 and 126.936<=p['lon']<=126.970):
                    raise ValueError('Campus coordinate outside supported area: '+b['id'])
            if b['access']['method']=='nearby_walkway_estimate' and b['access']['representative_to_access_m']>100:
                raise ValueError('Unverified building approach exceeds 100m')

    def info(self):
        return {k:v for k,v in self.data.items() if k!='buildings'}|{'count':len(self.entries),'search_is_local':True}

    def routing_origin(self,origin):
        # Only registry IDs select a precomputed access point; user-provided fields
        # cannot claim to be an official building or override its routing origin.
        b=self.by_id.get(origin.get('id'))
        return b['routing_point'] if b else origin

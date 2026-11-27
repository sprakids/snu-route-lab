"""Input treatment for a new R; preserve all source trip IDs, weights and destinations."""
import hashlib
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
REFERENCE=HERE.parent/'261124110718'
sys.path.insert(0,str(REFERENCE))
from grade_demand import bundle as grade_bundle, ref

MODEL='R'+HERE.name
EARLY_RATE=.25
STAY_RATE=.25


def uniform(key):
    return int.from_bytes(hashlib.sha256(('campus-timing-v1/'+key).encode()).digest()[:8],'big')/2**64


def triangular(u,low,mode,high):
    if u<(mode-low)/(high-low):
        return low+math.sqrt(u*(high-low)*(mode-low))
    return high-math.sqrt((1-u)*(high-low)*(high-mode))


@lru_cache(maxsize=None)
def release(eid):
    if uniform('section/'+eid)>=EARLY_RATE:return 0.
    return 60*triangular(uniform('early-length/'+eid),2.,5.,10.)


def dwell_path(common):
    coordinates=common['paths'][common['route_info']['shuttle-daehak']['segments'][0]][0]
    point=[coordinates,coordinates]
    try:return common['paths'].index(point)
    except ValueError:
        common['paths'].append(point)
        return len(common['paths'])-1


def metadata(common):
    common['dwell_path']=dwell_path(common)
    common['candidate_id']=common['data_version']=MODEL
    common['departure_and_boarding']={
        'baseline':ref.previous.load(REFERENCE/'viewer-data/common.json.gz')['candidate_id'],
        'early_section_fraction':EARLY_RATE,'early_minutes_min_mode_max':[2,5,10],
        'stay_trip_fraction':STAY_RATE,'stay_minutes_min_mode_max':[5,15,40],
        'door_lead_seconds':'min(180, half the preceding distinct departure interval)',
        'stops':['admin_snu','admin_daehak'],'clock':'Asia/Seoul',
        'demand':'same original weighted trips; changes to timing only before simulation'}
    return common


def inputs(day,service):
    b,patch,donors,_=grade_bundle(day,service)
    common=b['prepared']['common']
    metadata(common)
    courses=ref.ref.class_events(ref.load(ref.ref.COURSES))
    rows=b['prepared']['plans'][day]
    stats=Counter();sections=set();early_sections=set();digest=hashlib.sha256()
    for i,p in enumerate(rows):
        uid=p[0];parent=donors.get(uid,uid);e=courses[(parent-1)//48]
        assert e['weekday']==day and str(e['building'])==p[1]
        eid='/'.join((day,e['section_id'],str(e['building']),e['start'],e['end']))
        early=release(eid)
        stay=0.
        if uniform(f'trip/{parent}')<STAY_RATE:
            stay=60*triangular(uniform(f'stay-length/{parent}'),5.,15.,40.)
        sections.add(eid)
        if early:early_sections.add(eid);stats['early_trip_weight']+=p[3]
        if stay:stats['stay_trip_weight']+=p[3]
        if stay and early:stats['both_trip_weight']+=p[3]
        stats['total_weight']+=p[3]
        t=p[4]-early+stay
        assert 0<=t<86400 and t>=int(e['start'][:2])*3600+int(e['start'][3:])*60
        rows[i]=[*p[:4],t,*p[5:]]
        digest.update(f'{uid}|{p[3].hex()}|{t.hex()}|{b["destination_keys"][str(uid)]}\n'.encode())
    assert math.isclose(stats['total_weight'],b['prepared']['expected'][day],abs_tol=1e-5)
    return b,patch,donors,dict(**stats,sections=len(sections),early_sections=len(early_sections),
                               demand_sha256=digest.hexdigest())

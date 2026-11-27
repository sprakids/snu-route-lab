"""Keep observed grades, estimates and ranking uncertainty in separate fields."""
from routing import CROWD_COST

LABELS={0:'여유',1:'보통',2:'혼잡',3:'매우혼잡'}

def crowd_evidence(value,now):
    value=value or {};at=value.get('provided_at');cost=value.get('crowd_cost',CROWD_COST.get(str(value.get('crowd_code','0'))))
    age=max(0,now-at) if at and now-at>=-5 else None
    usable=cost is not None and age is not None and age<=600
    observed=usable and age<=90
    estimated=float(cost) if usable else None
    uncertainty=0 if observed else min(1,max(0,(age-90)/510)) if usable else 3
    return {'crowd_cost':float(cost) if observed else None,
        'crowd_estimate':estimated,'crowd_risk':min(3,estimated+uncertainty) if usable else 3.,
        'crowd_uncertainty':uncertainty,'crowd_source':'observed' if observed else 'last_observation_estimate' if usable else 'unavailable',
        'crowd_label':LABELS[int(cost)] if observed else LABELS[int(cost)]+' 추정' if usable else '정보 부족',
        'observed_at':at if usable else None,'age_seconds':round(age) if age is not None else None,
        'model_version':'persistence-age-v1' if usable and not observed else None}

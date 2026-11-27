"""Legacy timetable helpers for parked observations; queue estimation lives in automatic_queue."""
from datetime import datetime, timedelta, timezone

KST=timezone(timedelta(hours=9))
ADMIN={'lat':37.46086,'lon':126.950347,'label':'행정관 셔틀승차장 · 학교 공개 좌표'}
STATION={'lat':37.4793866666667,'lon':126.952455,'label':'서울대입구역 셔틀 하차점 · 학교 공개 좌표'}
WINDOWS=[(420,480,15),(480,660,5),(660,900,10),(900,1140,5),(1140,1200,15),(1200,1260,30)]
NIGHT=[1270,1300,1330,1360,1390]

def parked_admin_departure(ready):
    """2026-2 published headways are not a vehicle's actual departure clock."""
    date=datetime.fromtimestamp(ready,KST);minute=date.hour*60+date.minute+date.second/60
    if date.weekday()>=5 or not '2026-09-01'<=date.date().isoformat()<='2026-12-21':return None
    if date.date().isoformat() in ('2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'):return None
    if minute>=1260:
        for m in NIGHT:
            leave=date.replace(hour=m//60,minute=m%60,second=0,microsecond=0).timestamp()
            if leave>=ready:return {'departure_at':leave,'eta_window_seconds':[round(leave-ready)]*2,
                'earliest_departure_at':leave,'prediction_note':'정차 관측 · 공식 야간 시간표의 예정 출발 · 실제 출발·탑승 차량은 미확인'}
        return None
    for start,end,interval in WINDOWS:
        if start<=minute<end:
            maximum=5 if start in (480,900) else interval
            boundary=date.replace(hour=end//60,minute=end%60,second=0,microsecond=0).timestamp()
            wait=min(maximum*60/2,max(0,boundary-ready))
            return {'departure_at':ready+wait,'earliest_departure_at':ready,
                'eta_window_seconds':[0,min(maximum*60,round(boundary-ready))],
                'prediction_note':'정차 관측 · 출발시각 미제공 · 공식 배차범위의 절반 대기 시나리오 · 탑승 차량 미확인'}
    return None

def next_shuttle(ready):
    date=datetime.fromtimestamp(ready,KST)
    if date.weekday()>=5 or not '2026-09-01'<=date.date().isoformat()<='2026-12-21':return None
    minute=date.hour*60+date.minute+date.second/60
    for start,end,interval in WINDOWS:
        if start<=minute<end:
            leave=ready+interval*30
            # Do not silently extrapolate a peak-time headway beyond its window.
            boundary=date.replace(hour=end//60,minute=end%60,second=0,microsecond=0).timestamp()
            if leave>boundary:return next_shuttle(boundary)
            return {'departure_at':leave,'source':'시간표 배차구간의 절반 대기 시나리오','interval_minutes':interval}
    midnight=date.replace(hour=0,minute=0,second=0,microsecond=0)
    for planned in NIGHT:
        leave=(midnight+timedelta(minutes=planned)).timestamp()
        if leave>=ready:return {'departure_at':leave,'source':'공식 야간도서관 셔틀 출발시간','interval_minutes':None}
    return None


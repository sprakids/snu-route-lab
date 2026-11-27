"""User-selected average walking pace across the complete walking route."""
WALK_KMH=4.8
WALK_MPS=WALK_KMH/3.6
STEP_MPS=WALK_MPS

def seconds(meters,steps_m=0):
    steps_m=max(0,min(meters,steps_m))
    return (meters-steps_m)/WALK_MPS+steps_m/STEP_MPS

def info():
    return {'ordinary_kmh':WALK_KMH,'ordinary_mps':WALK_MPS,'steps_mps':STEP_MPS,
            'source':'사용자 지정 일반 보행 속도','note':'전체 보행 평균4.8km/h · 계단 위치는 별도 표시 · 실내 이동·신호 대기는 미측정'}

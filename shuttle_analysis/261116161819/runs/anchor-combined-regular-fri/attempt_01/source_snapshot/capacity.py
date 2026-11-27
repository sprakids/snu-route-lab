"""Shared finite seats; preference never changes this physical constraint."""
def seats(capacity,onboard):
    assert -1e-7<=onboard<=capacity+1e-7
    return max(0.,capacity-onboard)
def balance(capacity,before,off,boarded,after):
    assert 0<=off<=before+1e-7
    assert 0<=boarded<=capacity-(before-off)+1e-7
    assert abs(before-off+boarded-after)<1e-6
    assert -1e-7<=after<=capacity+1e-7

def capacity_at_clock(info,clock):
    value=info.get('capacity',60)
    for period in info.get('capacity_periods',[]):
        if period['start_second']<=clock<period.get('end_second',float('inf')):value=period['capacity']
    return value

def batch_size_at_clock(info,clock):
    rows=[p['vehicles'] for p in info.get('dispatch_batches',[]) if p['start_second']<=clock<p['end_second']]
    assert len(rows)<=1
    return rows[0] if rows else 1

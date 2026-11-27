"""Shared finite seats; preference never changes this physical constraint."""
def seats(capacity,onboard):
    assert -1e-7<=onboard<=capacity+1e-7
    return max(0.,capacity-onboard)
def balance(capacity,before,off,boarded,after):
    assert 0<=off<=before+1e-7
    assert 0<=boarded<=capacity-(before-off)+1e-7
    assert abs(before-off+boarded-after)<1e-6
    assert -1e-7<=after<=capacity+1e-7

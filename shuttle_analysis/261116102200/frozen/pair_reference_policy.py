"""Vehicle rules are fixed at terminal dispatch, never a query/stop clock."""
def capacity_at_clock(info,clock):
    result=info.get('capacity',60)
    for period in info.get('capacity_periods',[]):
        if clock>=period['start_second']:result=period['capacity']
    return result

def batch_size_at_clock(info,clock):
    matches=[p['vehicles'] for p in info.get('dispatch_batches',[]) if p['start_second']<=clock<p['end_second']]
    assert len(matches)<=1
    return matches[0] if matches else 1

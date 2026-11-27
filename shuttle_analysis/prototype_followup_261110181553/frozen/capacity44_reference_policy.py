"""Only the reported daytime administration/SNU commuter changes to 44."""
def capacity_at_clock(info,clock):
    value=info.get('capacity',60)
    for period in info.get('capacity_periods',[]):
        if period['start_second']<=clock<period['end_second']:value=period['capacity']
    return value

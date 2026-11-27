"""Distinguish an actual FIFO entry from a visit cancelled during preparation."""

EPS=1e-8

def ready_status(row,end_second):
    before_ready=row['end']<row['ready']-EPS or row['ticket'] is None
    if before_ready and row['outcome']=='boarded':
        raise ValueError('boarded_without_ready_fifo_entry')
    if before_ready:return 'preparation_cancelled_weight'
    if row['ready']>end_second:return 'after_window_ready_weight'
    return 'ready_entry_weight'

def has_ready_entry(row,end_second):
    return ready_status(row,end_second)=='ready_entry_weight'

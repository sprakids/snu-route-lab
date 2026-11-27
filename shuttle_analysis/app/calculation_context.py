"""Request-local memoization. Never shares live forecasts between searches."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time

_current=ContextVar('route_calculation',default=None)

def calculation_request(function):
    """Pin model selection for a whole response, including nested helpers."""
    @wraps(function)
    def wrapped(*args,**kwargs):
        if _current.get() is not None:return function(*args,**kwargs)
        with calculation_context():return function(*args,**kwargs)
    return wrapped

@contextmanager
def calculation_context(asof=None):
    token=_current.set({'asof':time.time() if asof is None else asof,'memo':{},'pinned':asof is not None})
    try:yield
    finally:_current.reset(token)

def calculation_now():
    current=_current.get()
    return current['asof'] if current is not None else time.time()

def refresh_calculation_clock():
    # Network prefetch can take seconds. Freeze the evaluation clock only after
    # it finishes, so a just-received observation is never treated as future data.
    current=_current.get()
    if current is not None and not current.get('pinned'):current['asof']=time.time()

def memoized(namespace,key,produce):
    current=_current.get()
    if current is None:return produce()
    cache=current['memo'].setdefault(namespace,{})
    if key not in cache:cache[key]=produce()
    return cache[key]

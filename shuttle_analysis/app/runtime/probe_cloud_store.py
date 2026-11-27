import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud_store import CloudStore,Conflict
store=CloudStore()
old,etag=store.read('qa-state')
store.write('qa-state',{'checked_at':time.time(),'kind':'storage-connectivity-only'},etag)
value,version=store.read('qa-state')
assert value['kind']=='storage-connectivity-only'
try:store.write('qa-state',{'should_not_write':True},'"invalid-etag-for-qa"')
except Conflict:conditional=True
else:raise AssertionError('Conditional write was not enforced')
print(json.dumps({'private_storage_read_write':True,'etag_conflict_enforced':conditional,'real_observations_written':False}))

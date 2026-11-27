"""Bounded, resumable, HTTPS-only collection of dated public segment aggregates.

Credentials stay in DPAPI. Response pages are compressed unchanged; target route
rows are also saved separately. An empty list proves end-of-pagination. No retries.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter
import argparse,urllib.request,urllib.parse,urllib.error,json,gzip,hashlib,threading,os
from concurrent.futures import ThreadPoolExecutor
from local_secret import load_key
from probe_tdata import ENDPOINT,RestrictRedirect

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'collected'
TARGETS={'100100250':'5511','100100251':'5513','100100253':'5516','120900011':'관악02-1','120900012':'관악02-2'}
LOCK=threading.Lock()
LEDGER=ROOT/'api_request_ledger.json'

def dump(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)
def sha(data):return hashlib.sha256(data).hexdigest()
def record_id(r):return tuple(r.get(k) for k in ('stdrDe','routeId','fromStaId','toStaId','staSn'))

def reserve(maximum,date,start,count):
    with LOCK:
        day=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y%m%d')
        state=json.loads(LEDGER.read_text(encoding='utf-8')) if LEDGER.exists() else {'kst_day':day,'calls':[],'prior_probes':[]}
        assert state['kst_day']==day,'Start a new dated ledger explicitly; do not mix days'
        for p in sorted((ROOT/'probes').glob('*/receipt.json')):
            if str(p) not in state['prior_probes']:
                state['prior_probes'].append(str(p))
        used=len(state['prior_probes'])+len(state['calls'])
        assert used<maximum, f'Local T-data request budget reached ({maximum}); no request made'
        state['calls'].append({'date':date,'start_row':start,'row_count':count,'reserved_before_request':True})
        state['requests_reserved_including_prior_probes']=used+1
        state['max_requests']=maximum
        dump(LEDGER,state)
        return used+1

def collect(date,args,key):
    directory=DATA/date;directory.mkdir(parents=True,exist_ok=True)
    target=directory/'target_routes.json'
    receipt_path=directory/'collection_receipt.json'
    if receipt_path.exists() and json.loads(receipt_path.read_text(encoding='utf-8')).get('status')=='complete':
        print(f'{date}: cached complete',flush=True);return
    start=1;pages=[];selected=[];seen=set();all_rows=0
    try:
        while True:
            compressed=directory/f'page_{start:07d}.json.gz'
            meta_path=directory/f'page_{start:07d}.receipt.json'
            if compressed.exists():
                body=gzip.decompress(compressed.read_bytes())
                meta=json.loads(meta_path.read_text(encoding='utf-8'))
                assert sha(body)==meta['body_sha256']
            elif date=='20261026' and start==1:
                seed=ROOT/'probes/20261107T061259_475920Z/response.txt'
                body=seed.read_bytes()
                assert len(json.loads(body))==5000
                meta={'date':date,'start_row':start,'row_count':args.row_count,'http_status':200,
                      'body_sha256':sha(body),'seeded_from_existing_probe':str(seed),'request_made':False}
                compressed.write_bytes(gzip.compress(body,compresslevel=1));dump(meta_path,meta)
            else:
                used=reserve(args.max_requests,date,start,args.row_count)
                params={'apikey':key,'stdrDe':date,'startRow':start,'rowCnt':args.row_count}
                req=urllib.request.Request(ENDPOINT+'?'+urllib.parse.urlencode(params),
                    headers={'Accept':'application/json','User-Agent':'SNU-Route-Research/1.0'})
                meta={'date':date,'start_row':start,'row_count':args.row_count,'request_sequence':used,
                      'credential_used':True,'automatic_retries':0,'request_made':True}
                try:
                    with urllib.request.build_opener(RestrictRedirect()).open(req,timeout=35) as response:
                        meta['http_status']=response.status;body=response.read(30_000_001)
                        assert len(body)<=30_000_000,'Response exceeded bounded size'
                except urllib.error.HTTPError as error:
                    meta['http_status']=error.code
                    error_text=error.read(1_000_000).decode('utf-8',errors='replace').replace(key,'[REDACTED_API_KEY]')
                    (directory/f'error_{start:07d}.txt').write_text(error_text,encoding='utf-8')
                    dump(meta_path,meta);raise RuntimeError('HTTP request failed; no automatic retry')
                assert key.encode() not in body,'Credential echo detected; response not saved'
                meta['body_sha256']=sha(body)
                compressed.write_bytes(gzip.compress(body,compresslevel=1));dump(meta_path,meta)
            rows=json.loads(body)
            assert isinstance(rows,list),'Unexpected API response shape; not an empty dataset'
            assert len(rows)<=args.row_count
            for r in rows:
                assert r['stdrDe']==date,'API returned a different reference date'
                rid=record_id(r);assert None not in rid,'Missing segment key'
                assert rid not in seen,'Pagination duplicated a date/route/segment key'
                seen.add(rid)
                if r['routeId'] in TARGETS:selected.append(r)
            all_rows+=len(rows)
            pages.append({'start_row':start,'received_rows':len(rows),'body_sha256':sha(body)})
            print(f'{date}: row {start}, received {len(rows)}, target segments {len(selected)}',flush=True)
            if not rows:break
            start+=len(rows)
        target.write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
        counts=Counter(r['routeId'] for r in selected)
        families={'average':'a18Num','maximum':'maxA18Num','runs':'a18FcntNum','sum_load':'a18SumLoadPsngNum'}
        coverage={name:sum(r.get(f'{prefix}{h:02d}h') is not None for r in selected for h in range(24))
                  for name,prefix in families.items()}
        dump(receipt_path,{'status':'complete','date':date,'source_rows':all_rows,'pages':pages,
             'target_segments':len(selected),'target_route_counts':dict(counts),
             'target_routes_missing':[rid for rid in TARGETS if not counts[rid]],
             'target_hour_cells':len(selected)*24,'non_null_cells_by_family':coverage,
             'target_file_sha256':sha(target.read_bytes()),'end_proved_by_empty_page':True,
             'duplicate_segment_keys':0,'key_printed':False})
        print(f'{date}: COMPLETE, {all_rows} source rows, {len(selected)} target segments, coverage {coverage}',flush=True)
    except Exception as error:
        dump(receipt_path,{'status':'partial_error','date':date,'source_rows_saved':all_rows,
             'target_segments_seen':len(selected),'pages_completed':pages,'error_class':type(error).__name__,
             'no_automatic_retry':True,'key_printed':False})
        print(f'{date}: stopped with {type(error).__name__}; partial evidence retained',flush=True)
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dates',nargs='+',required=True)
    parser.add_argument('--row-count',type=int,default=5000)
    parser.add_argument('--max-requests',type=int,default=900)
    parser.add_argument('--workers',type=int,default=1)
    args=parser.parse_args()
    assert 1<=args.row_count<=5000 and 1<=args.max_requests<=950 and 1<=args.workers<=2
    assert len(set(args.dates))==len(args.dates)
    for date in args.dates:datetime.strptime(date,'%Y%m%d')
    key=load_key();DATA.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(collect,date,args,key) for date in args.dates]
        for future in futures:future.result()

if __name__=='__main__':main()

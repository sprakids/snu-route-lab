"""One bounded HTTPS T-data probe, with no secret in CLI arguments or receipts.

Uses a process T_DATA_API_KEY or the current user's DPAPI-protected credential.
--check-endpoint makes one credential-free connectivity request and cannot fetch authenticated records.
No automatic retries, schema guesses, pagination loops, or model fitting.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, urllib.request, urllib.parse, urllib.error

ROOT=Path(__file__).resolve().parent
ENDPOINT='https://t-data.seoul.go.kr/apig/apiman-gateway/tapi/TaimsTpssA18RouteSection/1.0'

class RestrictRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlsplit(newurl)
        if p.scheme!='https' or p.hostname!='t-data.seoul.go.kr' or not p.path.startswith('/apig/'):
            raise RuntimeError('Redirect outside the authorized HTTPS API endpoint was blocked')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',required=True,help='YYYYMMDD reference date')
    parser.add_argument('--start-row',type=int,default=1)
    parser.add_argument('--row-count',type=int,default=10)
    parser.add_argument('--check-endpoint',action='store_true')
    args=parser.parse_args()
    datetime.strptime(args.date,'%Y%m%d')
    assert 1<=args.row_count<=5000 and args.start_row>=1
    key='' if args.check_endpoint else os.environ.get('T_DATA_API_KEY','').strip()
    if not args.check_endpoint and not key:
        from local_secret import CREDENTIAL,load_key
        if CREDENTIAL.exists():key=load_key()
    if not args.check_endpoint and not key:
        raise SystemExit('T_DATA_API_KEY is not configured. No API request was made.')
    params={'stdrDe':args.date,'startRow':args.start_row,'rowCnt':args.row_count}
    if key:params['apikey']=key
    request=urllib.request.Request(ENDPOINT+'?'+urllib.parse.urlencode(params),
                                   headers={'Accept':'application/json','User-Agent':'SNU-Route-Research/1.0'})
    output=ROOT/'probes'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True,exist_ok=False)
    receipt={'endpoint':ENDPOINT,'reference_date':args.date,'start_row':args.start_row,
        'requested_rows':args.row_count,'credential_used':bool(key),'automatic_retries':0,
        'requests_attempted':1,'http_status':None,'json_parseable':False,
        'authentication_or_dataset_success_not_assumed':True}
    body=b''
    try:
        opener=urllib.request.build_opener(RestrictRedirect())
        with opener.open(request,timeout=30) as response:
            receipt['http_status']=response.status
            receipt['content_type']=response.headers.get('Content-Type','')
            body=response.read(20_000_001)
            receipt['response_truncated']=len(body)>20_000_000
    except urllib.error.HTTPError as error:
        receipt['http_status']=error.code
        receipt['content_type']=error.headers.get('Content-Type','')
        body=error.read(1_000_000)
        receipt['error_class']='HTTPError'
    except Exception as error:
        # Avoid printing exception strings: they can include credential-bearing URLs.
        receipt['error_class']=type(error).__name__
    text=body.decode('utf-8-sig',errors='replace')
    redacted=False
    if key:
        for variant in (key,urllib.parse.quote(key,safe=''),urllib.parse.quote_plus(key)):
            if variant in text:text=text.replace(variant,'[REDACTED_API_KEY]');redacted=True
    receipt['credential_echo_redacted']=redacted
    receipt['saved_body_bytes']=len(text.encode('utf-8'))
    receipt['saved_body_sha256']=hashlib.sha256(text.encode('utf-8')).hexdigest()
    (output/'response.txt').write_text(text,encoding='utf-8')
    try:
        payload=json.loads(text)
        receipt['json_parseable']=True
        receipt['top_level_type']=type(payload).__name__
        if isinstance(payload,dict):receipt['top_level_keys']=list(payload)[:30]
        elif isinstance(payload,list):receipt['top_level_list_length']=len(payload)
    except (ValueError,TypeError):pass
    receipt['local_output']=str(output)
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

"""Reconcile saved source receipts; package the four untouched official HWP originals."""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import json,hashlib,zipfile
ROOT=Path(__file__).resolve().parent
def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
manifest=[]
for f in sorted((ROOT/'contracts/sources').glob('*.hwp.receipt.json')):
    r=json.loads(f.read_text(encoding='utf-8'))
    p=f.parent/r['file'];data=p.read_bytes()
    assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
    assert data.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))
    manifest.append(r)
assert len(manifest)==4
save(ROOT/'contracts/all_originals_manifest.json',manifest)
ui={
    'record_type':'Human-readable transcription of observed public browser UI, not a downloaded signed contract',
    'observation_date_kst':'2026-11-07',
    'source_url':'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=20231243066&bidPbancOrd=001',
    'notice_no':'20231243066-001','reference_no':'캠퍼스관리과-12364',
    'opening_datetime':'2024-02-01 11:05:46','opening_rows':2,
    'bidder':{'name':'주식회사 동영관광','business_no':'117-81-60737','opening_rank':1,'bid_price_krw':11587950000,'price_score':'14.737','technical_score':'75.68','total_score':'90.417'},
    'detailed_evaluation':'개인정보가 있는 경우라는 사유로 상세항목 비공개 안내',
    'not_confirmed':['Signed agreement','Negotiated final contract sum','2026 annual agreement','Amendments','Actual payments'],
    'contract_search':[
        {'url':'https://www.g2b.go.kr/','page':'계약현황 검색결과','title_search':'서울대학교 셔틀버스','start':'2026-01-01','end':'2026-11-07','linked_contracts_included':True,'result_count':0,'status':'loaded'},
        {'url':'https://www.g2b.go.kr/','page':'계약현황 검색결과','title_search':'서울대학교 셔틀버스','start':'2024-01-01','end':'2024-12-31','linked_contracts_included':True,'result_count':0,'status':'loaded'},
        {'url':'https://www.g2b.go.kr/','page':'계약현황 검색결과','title_search':'서울대학교 셔틀버스','start':'2025-01-01','end':'2025-12-31','result_count':None,'status':'request_error_after_date_correction','message':'나라장터 검색 결과 요청 중 에러가 발생하였습니다.'}
    ],
    'preview_checks':{'business_specification_table_structure':'Observed all route tables in official rendered accessibility output','visual_scope':'Top portion of rendered document only; screenshot was horizontally cropped by viewport','current_2026_operations_verified_by_this_document':False},
    'secondary_searches':[
        {'url':'https://xn--hq1bh689n.com/organization/%EC%84%9C%EC%9A%B8%EB%8C%80%ED%95%99%EA%B5%90?q=%EC%85%94%ED%8B%80&sort=amount_desc','term':'셔틀','result_count':0,'limit':'Aggregator explicitly warns of missing records'},
        {'url':'https://xn--hq1bh689n.com/company/1178160737?sort=amount_desc','institution_filter':'서울대학교','matching_institutions':0,'limit':'Not a complete company contract history'}
    ]
}
assert Decimal('14.737')+Decimal('75.68')==Decimal('90.417')
save(ROOT/'contracts/public_ui_findings.json',ui)
wrapper=ROOT/'contracts/sources/사업내역서_나라장터_미리보기.receipt.json'
if wrapper.exists():
    r=json.loads(wrapper.read_text(encoding='utf-8'));r['document_role']='Dynamic viewer wrapper only, no business-specification body. Do not count as another original.';save(wrapper,r)
first=json.loads((ROOT/'survey/search_results.json').read_text(encoding='utf-8'))
pages=json.loads((ROOT/'survey/pagination/search_pages.json').read_text(encoding='utf-8'))
posts={p['post_id']:p for r in first for p in r.get('posts',[])}
for page in pages:
    for p in page['posts']:posts[p['post_id']]=p
total=len(next(r for r in first if r['query']=='총조사')['posts'])+sum(len(r['posts']) for r in pages)
assert total==54 and len(posts)==66
imgs=json.loads((ROOT/'survey/cardnews_downloads.json').read_text(encoding='utf-8'))
for r in imgs:
    p=Path(r['file']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
save(ROOT/'survey/visual_review.json',{
    'post_id':'7733','posted_date':'2024-10-06','images_reviewed':['9324','9325','9326','9327'],
    'findings':['Cover','Planned route: upper engineering to lower engineering to agriculture to SNU station; 45 seats, equal allocation planned','Five negotiation phases','Phase four complete; 2024 budget not secured, service conditional on budget'],
    'survey_result_table_present':False,'current_operation_proven':False,'observed_destination_shares_proven':False
})
plan=Path('C:/Users/김예준/iCloudDrive/Downloads/산업공학의 이해/프젝/서울대_하교길_최적화_프로젝트_계획서_3장_통합본 2.md')
plan_hash=hashlib.sha256(plan.read_bytes()).hexdigest()
assert plan_hash=='3cfc989f3981dd38099b55f41a0d3b88c84bfdb3c4debf53b93fe8af73bfa7e2'
checks={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'official_originals':4,'official_original_bytes':sum(r['bytes'] for r in manifest),'all_original_hashes_match':True,'public_search_queries':len(first),'total_survey_pages':6,'total_survey_results':total,'unique_posts_all_searches':len(posts),'new_cardnews_images':len(imgs),'survey_responses_acquired':False,'signed_current_contract_acquired':False,'bid_price_is_contract_price':False,'plan_sha256':plan_hash,'plan_unchanged':True,'contacted_institutions':False}
save(ROOT/'verification.json',checks)
archive=ROOT/'서울대_셔틀_공식입찰원문4종_2026-11-07.zip'
assert not archive.exists()
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for folder in ('contracts/sources','contracts/text'):
        for p in (ROOT/folder).glob('*'):
            if p.is_file() and (p.suffix=='.hwp' or p.suffix=='.txt' or p.name.endswith('.hwp.receipt.json')):
                z.write(p,p.relative_to(ROOT))
    for name in ('추가조사_결과.md','프로젝트_방향변경_반영.md','contracts/all_originals_manifest.json','contracts/public_ui_findings.json','verification.json'):
        p=ROOT/name
        if p.exists():z.write(p,p.relative_to(ROOT))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert sum(x.endswith('.hwp') for x in z.namelist())==4
print(json.dumps(checks,ensure_ascii=False))
print('archive',archive,archive.stat().st_size)

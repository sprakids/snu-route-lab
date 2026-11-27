"""Verify the manually reviewed public-source evidence; do not change any model."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import urlopen
import csv,hashlib,json,re
from pypdf import PdfReader

HERE=Path(__file__).resolve().parent
S=HERE/'sources'

def save(name,obj):
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    snu=PdfReader(S/'bulletin_148_2026.pdf')
    text=snu.pages[104].extract_text();compact=re.sub(r'\s','',text)
    assert '2025.3.1.-2026.2.28.' in compact
    for value in ['245,392','265,935','783,972','1,295,299','1,600,869']:
        assert value in text,value
    assert 245392+265935+783972==1295299
    assert 366794+250937+983138==1600869
    guide=PdfReader(S/'rinfo_2026_survey_manual.pdf')
    definition=guide.pages[57].extract_text();d=re.sub(r'\s','',definition)
    assert '1인1일중복허용' in d and '연간수치로확대계산' in d
    html=(S/'infographic.html').read_text(encoding='utf-8');profiles=[]
    for title in ['최근 1개월간 시간대별 대출 현황','최근 1개월간 요일별 대출 현황']:
        start=html.index(title);fragment=re.sub(r'//[^\n]*','',html[start:start+3800])
        labels=re.search(r'labels:\s*(\[[^\]]*\])',fragment).group(1)
        values=json.loads(re.search(r'\bdata:\s*(\[[^\]]*\])',fragment).group(1))
        profiles.append({'title':title,'labels':labels,'values':values,'sum':sum(values),'unit':'loan transactions, not visitors','reference_month':'not explicitly identified on page','excluded_from_commute_demand':True})
    assert profiles[0]['sum']==profiles[1]['sum']==20677
    save('excluded_loan_profiles.json',profiles)
    annual=[{'period_start':'2025-03-01','period_end':'2026-02-28','library':'중앙도서관(분관 제외)',
        'reading_material_rooms':245392,'reading_rooms':265935,'kwanjeong':783972,'total':1295299,
        'unit':'시설 이용자수, 원표 표기','grain':'annual','unique_persons_confirmed':False,
        'open_days':350,'open_days_scope':'정보서비스센터 기준','source_printed_page':201,'source_pdf_page':105}]
    save('annual_utilization_verified.json',annual)
    descriptors=[
        ('L1','https://lib.snu.ac.kr/about/statistics/infographic/','infographic.html','Monthly hourly/weekday loans; excluded from visitor flow'),
        ('L2','https://s-space.snu.ac.kr/handle/10371/236702','bulletin_148_2026.pdf','2026-05-30 bulletin148, printed201 / PDF105 annual facility use'),
        ('L3','https://www.rinfo.kr/stat/bbs/detail/2/777','rinfo_2026_survey_manual.pdf','2026 KERIS guide printed54 / PDF58 permits repeated daily visits and sampled annual extrapolation'),
        ('L4','https://lib.snu.ac.kr/using/places-carrel/places/','facilities.html','Facility guide, not historical usage series'),
        ('L5','https://lib.snu.ac.kr/using/facility/?libcode=&type=F001','facility_reading_rooms.html','Public reading-room guide response and reservation links'),
        ('L6','https://lib.snu.ac.kr/about/staff-inquiry/services/se-central/','contacts.html','Official statistics, facilities and systems contacts'),
        ('L7','https://lib.snu.ac.kr/privacy/','privacy.html','Confirms access/seat-reservation system administration; log schema not established'),
        ('L8','https://www.rinfo.kr/stat/search/basic/1','rinfo_search.html','Survey-year search interface; no daily table obtained'),
        ('L9','https://www.snu.ac.kr/campuslife/facilities/library','campus_library.html','Published operation hours, including main3A exception')]
    manifest=[]
    for sid,url,name,role in descriptors:
        p=S/name
        if not p.exists():
            with urlopen(url,timeout=25) as response:p.write_bytes(response.read())
        manifest.append({'id':sid,'url':url,'local_path':'sources/'+name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'checked_date':'2026-11-08','role':role})
    save('source_register.json',manifest)
    save('research_verification.json',{'status':'PASS','checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'snu_bulletin_pages':len(snu.pages),'snu_facility_table':{'printed_page':201,'pdf_page':105,'annual_subtotal_reconciled':True,'daily_series_obtained':False},
        'rinfo_definition':{'printed_page':54,'pdf_page':58,'duplicate_daily_visits_allowed':True,'annual_extrapolation_allowed':True,'snu_specific_method_confirmed':False},
        'hour_week_loan_totals_reconciled':20677,'loan_counts_used_as_visitors':False,
        'time_series_18_after_obtained':False,'source_count':len(manifest),'email_sent':False,'model_or_app_modified':False,
        'scope_limit':'Public pages, bulletin148, Rinfo definition and listed facility response; not an exhaustive proof that no daily data exists.'})
    print(json.dumps({'status':'PASS','sources':len(manifest),'annual_utilization':1295299,'daily_series_obtained':False,'model_changed':False,'email_sent':False}))

if __name__=='__main__':main()

"""Build the reviewed research packet from local Markdown, source registry and audits."""
from pathlib import Path
import csv, json, re, html, sys
from datetime import datetime

ROOT=Path(__file__).resolve().parent
sources=json.loads((ROOT/'source_register.json').read_text(encoding='utf-8'))
byid={s['id']:s for s in sources}
assert len(byid)==len(sources)==30
with (ROOT/'source_register.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(sources[0]));w.writeheader();w.writerows(sources)

bib=['# 출처 목록','', '열람 기준: 2026-10-22 KST. 공식 문서, 학생 진술, 연구 초록과 미검토 후보를 구분했습니다.','']
for s in sources:
    bib += [f"## {s['id']} · {s['title']}",'',
            f"- 발행: {s['publisher']} / {s['date']}",
            f"- 유형·범위: {s['type']} / {s['scope']}",
            f"- 열람 수준: {s['access']}", f"- 사용할 근거: {s['supports']}",
            f"- 한계: {s['limitations']}", f"- [원문 열기]({s['url']})",'']
(ROOT/'report/출처_목록.md').write_text('\n'.join(bib),encoding='utf-8')

reportpath=ROOT/'report/윗공대_하교_자료조사.md'
report=reportpath.read_text(encoding='utf-8')
report=report.split('\n<!-- GENERATED_BIBLIOGRAPHY -->')[0]
report=report.replace('다음에 생성되는 `출처_목록.md`에는','`출처_목록.md`에는')
mini=['\n<!-- GENERATED_BIBLIOGRAPHY -->','']
for s in sources:
    mini += [f"- [{s['id']} · {s['title']}]({s['url']}) — {s['publisher']}, {s['date']}. 열람: {s['access']}."]
report+='\n'.join(mini)+'\n'
reportpath.write_text(report,encoding='utf-8')

template=ROOT/'observation_templates'
template.mkdir(exist_ok=True)
schemas={
 'bus_events.csv':['session_id','date_kst','stop_name','stop_direction','route_label','vehicle_session_alias','arrival_time_kst','departure_time_kst','passenger_capacity_verified','capacity_source','onboard_before_alighting','alighted','boarded','queue_remaining','boardings_denied_known','weather','notes_uncertainty'],
 'queue_intervals.csv':['session_id','date_kst','stop_name','stop_direction','route_label','interval_start_kst','interval_end_kst','initial_queue','new_arrivals','boarded','left_queue_or_changed_route','final_queue','observation_complete','notes_uncertainty'],
 'trip_interviews.csv':['anonymous_case_id','interview_date_kst','degree_group_optional','departure_building','departure_time_approx','destination_zone_not_address','travel_sequence','walk_minutes_reported','wait1_minutes_reported','ride_minutes_reported','transfer_minutes_reported','wait2_minutes_reported','missed_boardings_reported','alternative_considered','reason_for_choice','time_estimate_or_record','optional_access_constraint_no_diagnosis','consent_for_use','notes_uncertainty']
}
for name,fields in schemas.items():
    with (template/name).open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerow(fields)
(template/'작성_안내.md').write_text('''# 관찰 기록 안내

세 CSV는 실제 데이터가 없는 빈 양식입니다. 시각은 KST로 기록합니다. 미관측은 빈칸이며, 관측된 0과 다릅니다.

- `session_id`: 관찰 세션의 임시 코드. 차량·학생의 영구 식별자를 쓰지 않습니다.
- `stop_direction`: 같은 정류장 이름의 양방향을 구분합니다. 순환·역순환을 합치지 않습니다.
- `passenger_capacity_verified`: 차량에 표기되거나 운영자가 확인한 승객 수용량만 입력합니다. '25인승'이라는 차종 표기와 승객정원은 구분합니다.
- `queue_remaining`: 해당 차량이 떠난 직후의 대기 인원. 다른 행선지 줄을 합치지 않습니다.
- `boardings_denied_known`: 타려고 했으나 못 탄 것이 확인된 인원만 입력합니다. 남아 있는 모든 사람을 자동으로 실패 인원으로 보지 않습니다.
- `observation_complete`: 기록 누락이나 시야 가림 여부. 불완전한 창을 0으로 처리하지 않습니다.
- `initial_queue + new_arrivals = boarded + left_queue_or_changed_route + final_queue`로 인원 보존을 검사합니다.
- 인터뷰 양식에는 학번·집 주소·진단명·연락처가 없습니다. 목적지는 역/대학동 등 생활권만 기록합니다. 녹음·인용은 동의를 받습니다.
''',encoding='utf-8')

def mdcell(text):return {'cell_type':'markdown','metadata':{},'source':text.splitlines(True)}
def codecell(text):return {'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':text.splitlines(True)}
audit=json.loads((ROOT/'evidence/handoff_audit.json').read_text(encoding='utf-8'))
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[
 mdcell('# 수강편람 인계 검증 및 가정 계산\n\n원본은 수정하지 않습니다. 슬롯 추출의 정합성과 가정 계산만 검증하며, 실제 혼잡을 추정하지 않습니다. 각 실행은 옆의 Python 파일에 포함된 코드를 실행합니다. xlrd==2.0.2가 필요합니다.'),
 codecell("from pathlib import Path\nROOT=Path.cwd()\nif not (ROOT/'verify_handoff.py').exists():\n    ROOT=ROOT/'shuttle_analysis'/'research'\nassert (ROOT/'verify_handoff.py').exists(), 'Open this notebook from its research folder'\n"),
 mdcell('## 1. XLS와 제공 CSV를 비교하는 코드\n\n모든 원본 셀과 행 번호를 비교한 뒤 시간·방·형태를 독립적으로 재파싱합니다. 아래 파일에 정확한 Python이 있습니다.'),
 codecell("audit_path=ROOT/'verify_handoff.py'\nprint(audit_path.read_text(encoding='utf-8'))\nexec(compile(audit_path.read_text(encoding='utf-8'),str(audit_path),'exec'),{'__file__':str(audit_path)})\n"),
 mdcell(f"저장된 실행 결과: {audit['original_cells_compared']:,}개 원본 셀, {audit['meeting_fields_compared']:,}개 슬롯 필드 대조, 불일치 0. 상세 결과는 evidence/handoff_audit.json입니다. 이 문장은 해당 저장 실행에 한합니다."),
 mdcell('## 2. 실제 관측과 분리한 계산 예시\n\n공표 간격의 산술 변환, 차량 수 하한의 예시, 무작위 도착 대기식과 인원 보존을 확인합니다.'),
 codecell("example_path=ROOT/'capacity_examples.py'\nprint(example_path.read_text(encoding='utf-8'))\nexec(compile(example_path.read_text(encoding='utf-8'),str(example_path),'exec'),{'__file__':str(example_path)})\n")
]}
for i,c in enumerate(nb['cells']):c['id']=f'cell-{i+1}'
(ROOT/'자료검증_및_가정계산.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')

# Render a Korean PDF with real selectable text and clickable original-source links.
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.pagesizes import A4
pdfmetrics.registerFont(TTFont('Malgun',r'C:\Windows\Fonts\malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold',r'C:\Windows\Fonts\malgunbd.ttf'))
pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold',italic='Malgun',boldItalic='MalgunBold')
styles={
 'body':ParagraphStyle('body',fontName='Malgun',fontSize=9.3,leading=15.2,spaceAfter=6,wordWrap='CJK'),
 'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=20,leading=28,spaceAfter=14,textColor=colors.HexColor('#143754'),wordWrap='CJK'),
 'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=13.2,leading=20,spaceBefore=15,spaceAfter=7,keepWithNext=True,textColor=colors.HexColor('#143754'),wordWrap='CJK'),
 'h3':ParagraphStyle('h3',fontName='MalgunBold',fontSize=10.7,leading=17,spaceBefore=9,spaceAfter=5,keepWithNext=True,wordWrap='CJK'),
 'table':ParagraphStyle('table',fontName='Malgun',fontSize=8,leading=12,wordWrap='CJK'),
 'th':ParagraphStyle('th',fontName='MalgunBold',fontSize=8,leading=12,wordWrap='CJK',textColor=colors.white),
}
def markup(text):
    # Escaping is performed around links so URL ampersands remain well-formed XML.
    chunks=[];last=0
    for m in re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)',text):
        chunks.append(html.escape(text[last:m.start()]))
        chunks.append('<link href="'+html.escape(m[2],quote=True)+'" color="#155e95">'+html.escape(m[1])+'</link>')
        last=m.end()
    chunks.append(html.escape(text[last:]))
    text=''.join(chunks)
    text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'<font color="#294e65">\1</font>',text)
    return text

story=[];lines=report.splitlines();i=0
while i<len(lines):
    line=lines[i].strip()
    if not line or line.startswith('<!--'):i+=1;continue
    if line.startswith('|'):
        block=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            row=[c.strip() for c in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?',c.replace(' ','')) for c in row):block.append(row)
            i+=1
        n=len(block[0]);width=A4[0]-88
        ratios={3:[.24,.31,.45],4:[.17,.30,.29,.24],5:[.07,.22,.27,.29,.15]}.get(n,[1/n]*n)
        data=[[Paragraph(markup(c),styles['th' if j==0 else 'table']) for c in row] for j,row in enumerate(block)]
        t=Table(data,colWidths=[width*x for x in ratios],repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#214a64')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f3f6f8'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#214a64')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d7e0e7'))]))
        story.extend([t,Spacer(1,8)]);continue
    if line.startswith('### '):style=styles['h3'];line=line[4:]
    elif line.startswith('## '):style=styles['h2'];line=line[3:]
    elif line.startswith('# '):style=styles['title'];line=line[2:]
    else:style=styles['body']
    if line.startswith('- '):line='• '+line[2:]
    formatted=markup(line)
    if style is styles['title'] and line.startswith('윗공대에서 집으로'):
        formatted='윗공대에서 집으로<br/>하교 불편과 셔틀 개선 근거 조사'
    story.append(Paragraph(formatted,style));i+=1

out=ROOT/'report/윗공대_하교_자료조사.pdf'
def page_footer(canvas,doc):
    canvas.saveState();canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#5c6c77'))
    canvas.drawString(44,26,'윗공대 하교 자료 조사 · 2026-10-22 · 현장 검증 전')
    canvas.drawRightString(A4[0]-44,26,str(doc.page));canvas.restoreState()
doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=44,title='윗공대 하교 불편과 셔틀 개선 근거 조사',author='서울공대 데이터 공모전 후보 주제 검토')
doc.build(story,onFirstPage=page_footer,onLaterPages=page_footer)
print(json.dumps({'source_records':len(sources),'interview_cases':12,'pdf':str(out),'pdf_bytes':out.stat().st_size},ensure_ascii=False))

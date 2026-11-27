"""Publish the promoted V12 map and its route-planning data."""
import gzip
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent
RESEARCH_ID = 'R' + MODEL.name
VERSION = 'V' + MODEL.name
FAMILY = 'V12'
SIM = MODEL.parent / 'simulation_viewer_2026-11-07'
OLD = SIM / 'deployment/supply_ui_261110162302_173920'
STAGE = SIM / 'deployment' / ('map_' + VERSION)
sys.path.insert(0, str(MODEL))
import map as research_map


def update(text, old, new):
    if old not in text:
        raise ValueError(old)
    return text.replace(old, new)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def build():
    config = json.loads((OLD/'vercel.json').read_text(encoding='utf8'))
    project = json.loads((OLD/'.vercel/project.json').read_text(encoding='utf8'))
    assert project['projectName']=='snu-shuttle-simulation'
    static=STAGE/'public'
    shutil.copytree(OLD/'public', static, dirs_exist_ok=True)
    # Already-open tabs still run the R bundle and check its internal IDs.
    previous=SIM/'deployment'/('map_'+RESEARCH_ID)/'public'/RESEARCH_ID
    shutil.copytree(previous, static/RESEARCH_ID, dirs_exist_ok=True)
    for name in ('.vercel/project.json','.vercelignore'):
        dest=STAGE/name
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(OLD/name,dest)
    shutil.copyfile(static/'index.html',static/'v11.html')
    release=static/VERSION
    release.mkdir(exist_ok=True)
    research_map.viewer.serve_map.MODEL=VERSION
    research_map.render_assets(release)
    html=(release/'index.html').read_text(encoding='utf8')
    html=update(html,'하교길 실험실 · 신림선 통합 R','하교길 실험실 · 공식 지도 '+FAMILY)
    html=update(html,'<span class="eyebrow">'+VERSION, '<span class="eyebrow">공식 지도 '+FAMILY+' · '+VERSION)
    html=update(html,'href="model-guide"', 'href="/model-guide.html"')
    html=update(html,'href="/model-guide"', 'href="/model-guide.html"')
    html=update(html,'href="./"', 'href="/"')
    html=update(html,'로컬 서버를 확인한 뒤 다시 불러오세요.', '연결 상태를 확인하고 다시 불러오세요.')
    html=update(html,'<h2 id="about-title">신림선 통합 하교 모형</h2>',
        '<h2 id="about-title">하교길 지도 모형</h2><p>이 지도의 공식 모형은 '+FAMILY+'('+VERSION+')'+
        '입니다. <a href="https://snu-route-lab.vercel.app/">길찾기</a>용으로 행정관 두 통학 셔틀의 승차 전·후 대기를 제공합니다. '
        '<a id="v11-link" href="/v11.html">같은 시각의 V11 지도 보기</a></p>')
    html=html.replace('출발·승차 방식 변경 전후의 도보 귀가 비율','모의 도보 귀가 비율')
    for path in (release/'index.html',static/'index.html',static/'city.html',static/RESEARCH_ID/'index.html'):
        path.write_text(html,encoding='utf8')
    js=release/'viewer.js'
    js.write_text(update(js.read_text(encoding='utf8'),'통합 R 공용 지도','V12 공용 지도'),encoding='utf8')
    with js.open('a',encoding='utf8') as handle:
        handle.write("""
const previousMap=document.getElementById('v11-link');
previousMap.addEventListener('click',()=>{
  const url=new URL('/v11.html',location.origin);
  url.searchParams.set('day',state.day);
  url.searchParams.set('scenario',state.scenario);
  url.searchParams.set('second',Math.floor(state.second));
  previousMap.href=url.href;
});
""")
    for item in research_map.viewer.serve_map.serve.SHARED:
        source=SIM/'public'/item
        dest=release/item
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
    for name in ('assets','vendor'):
        shutil.copytree(static/name,release/name,dirs_exist_ok=True)
    shutil.copyfile(research_map.viewer.serve_map.VIEWER/'integrated.css', release/'integrated.css')
    (release/'viewer-data').mkdir(exist_ok=True)
    cases=[f'{s}-{d}' for s in ('regular','peak') for d in ('mon','tue','wed','thu','fri')]
    files=['viewer-data/'+key+'.json' for key in ['common',*cases]]+['map-stats.json','station-access.json']
    digests={}
    for name in files:
        source=MODEL/(name+'.gz')
        dest=release/(name+'.gz')
        baseline=gzip.decompress(source.read_bytes())
        promoted=baseline.replace(('"'+RESEARCH_ID+'"').encode(),('"'+VERSION+'"').encode())
        if baseline==promoted:
            shutil.copyfile(source,dest)
        else:
            assert promoted.replace(('"'+VERSION+'"').encode(),('"'+RESEARCH_ID+'"').encode())==baseline
            dest.write_bytes(gzip.compress(promoted,compresslevel=6,mtime=0))
        digests[name]=hashlib.sha256(promoted).hexdigest()
    reports=release/'reports'
    reports.mkdir(exist_ok=True)
    feed=HERE/'routing-feed.json'
    assert json.loads(feed.read_bytes())['release']==VERSION
    shutil.copyfile(feed,release/feed.name)
    digests[feed.name]=hashlib.sha256(feed.read_bytes()).hexdigest()
    subprocess.run([sys.executable, '-c', 'from report import plot; import sys; plot(sys.argv[1], sys.argv[2])',
                    str(reports/'tuesday.png'), FAMILY], cwd=MODEL, check=True)
    for src,dst in [('현장비교.csv','field-counts.csv'),
                    ('평일검증.csv','weekdays.csv'),('v11_comparison/관측별_1분_비교.csv','v11-field-counts.csv')]:
        with (MODEL/src).open(encoding='utf-8-sig',newline='') as inp,(reports/dst).open('w',encoding='utf-8-sig',newline='') as out:
            reader=csv.DictReader(inp)
            writer=csv.DictWriter(out,fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                for key in ('model','condition'):
                    if row.get(key) in ('R','candidate'):
                        row[key]=FAMILY
                writer.writerow(row)
    guide=(MODEL/'guide.html').read_text(encoding='utf8').replace(RESEARCH_ID,VERSION).replace('새 R은',FAMILY+'는').replace('새 R의',FAMILY+'의').replace('새 R',FAMILY)
    guide=update(guide,'로컬 연구 지도','공식 시뮬레이션 지도')
    guide=update(guide,'/research/window.png',f'/{VERSION}/reports/tuesday.png')
    guide=update(guide,'/research/counts.csv',f'/{VERSION}/reports/field-counts.csv')
    guide=update(guide,'/research/weekdays.csv',f'/{VERSION}/reports/weekdays.csv')
    guide=update(guide,'<a href="/research/guide">입력 자료와 가정</a>', '<a href="#inputs">입력 자료와 가정</a>')
    guide=update(guide,'</main>',f'''<section id="inputs"><h2>입력 자료와 모형 범위</h2>
<p>서울대학교 수강편람의 강의실·종료 시각과 강좌별 수강 인원으로 출발 수요를 만들었습니다. 개인별 주소·귀가 기록은 수집하지 않았습니다. 기숙사·대학동 도보 선택에는 보행 경로의 거리와 경사가 반영됩니다.</p>
<p>배차는 <a href="https://cse.snu.ac.kr/ko/community/notice/25464">서울대 셔틀 운행 안내</a>를 참고했습니다. 11월 17~20일 운영사 위치 자료로 평일 복귀 시각을 추정했고, 월요일은 화요일 기록을 참고했습니다. 승차 위치에 들어온 뒤 출발할 때까지 문이 열린다고 가정합니다. 위치 자료만으로 개문 시각이나 빈자리를 직접 알 수는 없습니다.</p>
<p>11월 5일 서울시·티머니 카드자료는 교내 18개 시내버스 정류장의 15분 단위 승차 분포와 관악산역 하교 시나리오에 사용했습니다. 목요일 관악산역 320명은 가정이며, 시내버스에 교외에서 미리 타고 들어온 승객은 지도 모형에 직접 포함하지 않았습니다.</p>
<p>공식 모형은 V12({VERSION})입니다. <a href="https://snu-route-lab.vercel.app/">경로 추천 서비스</a>에 제공하는 행정관 서울대입구역행·대학동행 자료에는 줄에 선 뒤 탈 때까지와 탄 뒤 출발할 때까지의 평균이 각각 들어 있습니다. 정류장에 도착한 요일·분이 같고 그곳에서 실제로 승차한 모의 통행을 기준으로 계산합니다. <a href="/{VERSION}/routing-feed.json">길찾기용 자료</a></p>
<p>바깥줄 실측 7건에서 피크 배차의 평균 절대오차는 V11 8.24명, V12 3.80명이었습니다. 11월 24일 대학동행 차내 17명과 11월 23일 점심 즉시 승차는 V12에서도 오차가 남았습니다.</p>
<p><a href="/v11.html">이전 V11 지도</a> · <a href="/{VERSION}/reports/v11-field-counts.csv">V11과 공식 지도 실측 비교표</a> · <a href="/v11-methodology.html">V11 자료와 출처</a></p></section></main>''')
    shutil.copyfile(OLD/'public/methodology.html',static/'v11-methodology.html')
    shutil.copyfile(OLD/'public/methodology.md',static/'v11-methodology.md')
    (static/'v11-methodology.html').write_text((static/'v11-methodology.html').read_text(encoding='utf8').replace('href="methodology.md"', 'href="/v11-methodology.md"'),encoding='utf8')
    notes=(MODEL/'README.md').read_text(encoding='utf8')
    notes=notes[notes.index('## 차량이'):notes.index('## 재현')]
    notes=re.sub(r' ?\[[^\]]+\]\((?!https?://)[^)]+\)(?: · )?', '', notes)
    (static/'methodology.md').write_text(f'# 공식 하교 모형 V12 ({VERSION})\n\n[자료·가정과 현장 비교](/model-guide.html) · [길찾기 대기 자료](/{VERSION}/routing-feed.json) · [V11 설명서](/v11-methodology.md)\n\n'+notes.strip()+'\n',encoding='utf8')
    for name in ('model-guide.html','methodology.html'):
        (static/name).write_text(guide,encoding='utf8')
    config['redirects']=[
        *[{'source':p,'destination':'/'+VERSION+'/','permanent':False} for p in ('/'+RESEARCH_ID,'/'+RESEARCH_ID+'/','/'+RESEARCH_ID+'/index.html','/V12','/V12/')],
        *[
        {'source':path,'has':[{'type':'query','key':'dataset',
          'value':'(baseline_v5|empirical_speed_v1|gate_access_v1|walk_choices_v1|corrected_supply_v1)'}],
         'destination':'/v11.html','permanent':False} for path in ('/','/index.html','/city.html')]]
    config['rewrites']=[
        *[{'source':f'/{ver}/{name}','destination':f'/{ver}/{name}.gz'} for ver in (VERSION,RESEARCH_ID) for name in files],
        {'source':'/model-guide','destination':'/model-guide.html'},
        *config['rewrites']]
    for route in (f'/{ver}/{name}' for ver in (VERSION,RESEARCH_ID) for name in files):
        config['headers'].append({'source':route,'headers':[
            {'key':'Content-Type','value':'application/json; charset=utf-8'},
            {'key':'Content-Encoding','value':'gzip'},
            {'key':'Cache-Control','value':'public, max-age=31536000, immutable'}]})
    write_json(STAGE/'vercel.json',config)
    write_json(HERE/'expected.json',{'model':VERSION,'family':FAMILY,'research_id':RESEARCH_ID,'routing_model':'261110162302','decoded_sha256':digests,
                'previous_deployment':'dpl_677hD5B4SKMwJjn6nQQbdyoDfvu4',
                'public_html_sha256':hashlib.sha256((static/'index.html').read_bytes()).hexdigest()})
    assert (OLD/'public/routing-model/latest.json').read_bytes()==(static/'routing-model/latest.json').read_bytes()
    print(STAGE)


if __name__=='__main__':
    build()

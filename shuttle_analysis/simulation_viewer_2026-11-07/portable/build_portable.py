"""Build a minimal Windows release without bundling local runtimes or private inputs."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,subprocess,zipfile,gzip

HERE=Path(__file__).resolve().parent
VIEWER=HERE.parent
RELEASES=VIEWER.parent/'share_packages'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--build-id',default='2026-11-07_R1');p.add_argument('--adaptive',action='store_true');args=p.parse_args()
    args.adaptive=args.adaptive or 'viewer-v4.js' in (VIEWER/'public/index.html').read_text(encoding='utf-8')
    assert all(c.isascii() and (c.isalnum() or c in '_-') for c in args.build_id)
    name='SNU_Shuttle_Map_Windows_'+args.build_id;stage=RELEASES/name;archive=RELEASES/(name+'.zip')
    assert not stage.exists() and not archive.exists(),'Preserve prior builds; choose a fresh build id.'
    stage.mkdir(parents=True);public=stage/'public';public.mkdir();source=VIEWER/'public'
    scripts=('index.html','viewer-v4.js','viewer-v2.css','graphs-v4.js','bus-motion.js') if args.adaptive else ('index.html','viewer-v2.js','viewer-v2.css','graphs-v2.js','bus-motion.js')
    inputs=[source/n for n in scripts]
    inputs+=sorted((source/'vendor').rglob('*'))
    inputs+=sorted((source/'data/capacity_v3').glob('*.json.gz'))
    if args.adaptive:inputs+=sorted((source/'data/capacity_v4').glob('*.json.gz'))
    inputs=[s for s in inputs if s.is_file()]
    hashes={str(s.relative_to(source)).replace('\\','/'):sha(s) for s in inputs}
    assert sum(n.endswith('.json.gz') for n in hashes)==(24 if args.adaptive else 12)
    for s in inputs:
        target=public/s.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s,target)
    manifest=''.join(h+'  public/'+n+'\n' for n,h in sorted(hashes.items()))
    (stage/'assets.sha256').write_text(manifest,encoding='utf-8')
    launcher_source=stage/'launcher_source';launcher_source.mkdir()
    for n in ('MapLauncher.cs','app.manifest','launcher.exe.config'):shutil.copy2(HERE/n,launcher_source/n)
    compiler=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    if not compiler.exists():compiler=Path('C:/Windows/Microsoft.NET/Framework/v4.0.30319/csc.exe')
    assert compiler.is_file(),'Windows .NET Framework C# compiler is required only for rebuilding.'
    exe=stage/'시뮬레이션 실행.exe'
    command=[str(compiler),'/nologo','/target:winexe','/platform:anycpu','/optimize+','/utf8output',
        '/out:'+str(exe),'/win32manifest:'+str(HERE/'app.manifest'),
        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',str(HERE/'MapLauncher.cs')]
    result=subprocess.run(command,text=True,capture_output=True,encoding='utf-8')
    (stage/'launcher_source/build.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    shutil.copy2(HERE/'launcher.exe.config',stage/'시뮬레이션 실행.exe.config')
    readme='''서울대 하교길 실험실 — Windows 공유용
====================================

가장 빠른 실행 방법
1. ZIP 전체를 원하는 폴더에 압축 해제합니다.
2. 그 폴더의 [시뮬레이션 실행.exe]를 더블클릭합니다.
3. 기본 브라우저에 지도가 자동으로 열립니다.

Python, Node.js, Codex, 관리자 권한은 필요하지 않습니다.
Windows 10/11의 기본 .NET Framework 4.x를 사용합니다.
브라우저는 최신 Microsoft Edge 또는 Chrome을 권장합니다.
배경 지도를 불러오려면 인터넷 연결이 필요합니다.
시뮬레이션 계산자료와 화면 코드는 이 ZIP에 포함되어 있습니다.

실행기 창을 열어 두세요. [종료] 또는 창의 X를 누르면 로컬 서버가 종료됩니다.
브라우저 탭을 닫았으면 실행기 창의 [지도 다시 열기]를 누르세요.
실행기를 다시 더블클릭해도 같은 폴더의 서버를 중복 실행하지 않습니다.
압축을 풀지 않은 채 ZIP 내부의 exe만 실행하거나 public 폴더를 옮기면 실행되지 않습니다.
이 ZIP 전체를 다른 사람에게 전달하면 됩니다. localhost 주소만 보내서는 공유되지 않습니다.

지도에서 볼 수 있는 것
- 요일, 초 단위 시각, 재생 속도(1초/초부터)를 선택할 수 있습니다.
- [만차 장면]을 누르면 못 탄 점들이 남아 있는 장면으로 이동합니다.
- 빨간 점은 만차로 남은 모형 흐름입니다. 다음 버스에도 자리가 없으면 계속 기다립니다.
- 대형 셔틀은 정원 60명 가정, 공식 소형 역순환은 25명으로 구분합니다.
- 15~19시 피크 최소 간격(입구역3분·순환5분)과 기준(4분·6분)을 비교합니다.
- 차량 속도는 교내 최고40km/h, 교외 목표65km/h(요청 범위60~70의 중간값)입니다.
- 저장된 캠퍼스 경계와 도로 거리, 가속·감속1m/s², 정류장15초 정차를 적용했습니다.
- [그래프]에서 이번 계산과 이전 평균 대기시간 표를 볼 수 있습니다.

해석할 때
이것은 수강인원 기반의 조건부 가중 모형입니다. 실제 학생 GPS나 실측 혼잡 자료가 아닙니다.
점 1개는 약 2명 상당의 모형 이동량입니다. 정원과 통계는 전체 가중 흐름으로 계산했습니다.
앞 정류장 승객의 차내 점유, FIFO 승차, 만차 잔류, 후속 환승 지연을 반영했습니다.
기존 대표 경로 선택을 유지했으며 경로 재선택, 수업 외 승객, 실제 정체는 미반영입니다.
최소 간격은 공식 시간표 범위의 하한을 넣은 조건입니다. 실제 차량 회전·배차 실행 가능성은 미검증입니다.
이전 그래프는 평균 유입·20개 출발위상 계산이므로 이번 대표 반복과 단순 개선율 비교를 하면 안 됩니다.
야간의 2대 동시 출발은 이전 계산의 가정이며, 내부 회차표를 확인한 사실은 아닙니다.

프로그램 동작
이 컴퓨터의 127.0.0.1에만 서버를 엽니다. 빈 포트를 자동으로 골라 다른 서버와 충돌하지 않습니다.
설치, 자동 시작, 방화벽 규칙, PowerShell 실행정책을 변경하지 않습니다.
사용자 로컬 앱 데이터의 SNUShuttleMap 폴더에는 실행 상태와 오류 로그만 저장합니다.
현재 배포 코드는 디지털 서명되지 않았습니다. 조직 정책으로 실행이 제한되면 배포자에게 문의하세요.
public 폴더는 실행 자료입니다. launcher_source 폴더는 실행기 소스이며 실행에 컴파일러는 필요 없습니다.
assets.sha256은 압축 해제 누락·파일 변조 여부를 확인하는 파일 목록입니다. 서명된 게시자 인증을 뜻하지 않습니다.

자료·출처
모형 기준일: 2026-11-07 / 기존 대표 seed 20261106
공식 시간표: https://cse.snu.ac.kr/ko/community/notice/25464
.NET 안내: https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-and-server
지도·보행망: © OpenStreetMap 기여자 — https://www.openstreetmap.org/copyright
Leaflet: public/vendor/LEAFLET-LICENSE
이 패키지는 기존 계산 결과를 재생합니다. 수강신청 사이트나 교통 API에 로그인하거나 실시간 자료를 수집하지 않습니다.
'''
    if args.adaptive:
        readme=readme.replace('기존 대표 경로 선택을 유지했으며 경로 재선택, 수업 외 승객, 실제 정체는 미반영입니다.',
            '기존 대표 최초 경로에서 시작해 대기줄을 보고 도보·다른 노선으로 변경합니다.\n도착 직후·60초마다·만차 뒤 재판단, 예상 도착 2분 이상 개선·변경 후 3분 유지·최대2회 가정입니다.\n청록색 점은 변경 후 걷는 흐름입니다. [경로 변경 장면]에서 확인하고 [기존 경로 유지]와 비교할 수 있습니다.\n서울대학교 ARS21128→서울대입구역2번출구 ARS21252 구간의 5511·5513·5515·5528·6515 중 먼저 오는 버스도 이용합니다.\n대기줄을 떠난 흐름은 경로 변경량으로 따로 세며 탑승자 평균 대기와 구분합니다.\n수업 외 승객, 요금 선호, 시내버스 정원, 실제 도로 정체는 미반영입니다.')
    (stage/'먼저 읽어주세요.txt').write_text(readme,encoding='utf-8-sig')
    notices='''THIRD-PARTY NOTICES\n\nLeaflet 1.9.4: the original BSD license is included in public/vendor/LEAFLET-LICENSE.\nOpenStreetMap contributors: https://www.openstreetmap.org/copyright\nBasemap tiles: https://tile.openstreetmap.org/ (normal visible-map requests only).\nThe launcher uses the .NET Framework already supplied by Windows; no Microsoft runtime binaries are redistributed.\nOfficial shuttle schedule: https://cse.snu.ac.kr/ko/community/notice/25464\n'''
    (stage/'THIRD-PARTY-NOTICES.txt').write_text(notices,encoding='utf-8')
    team_doc=VIEWER/'팀공유_시뮬레이션_설명서_자료출처.md'
    if team_doc.exists():shutil.copy2(team_doc,stage/team_doc.name)
    if args.adaptive:
        doc=VIEWER/'팀공유_경로변경_가정과_자료출처.md';shutil.copy2(doc,stage/doc.name)
        old=stage/team_doc.name
        if old.exists():old.write_text('> 이 문서는 이전 v3의 자료 출처·계산 설명입니다. 최신 행동 변경은 `팀공유_경로변경_가정과_자료출처.md`를 먼저 읽어주세요.\n\n'+old.read_text(encoding='utf-8'),encoding='utf-8')
    # Share only a summary of model checks, with no user paths or full course inputs.
    v=json.loads((VIEWER/'capacity_model/speed_40_65/verification.json').read_text(encoding='utf-8'))
    iv=json.loads((VIEWER/'capacity_model/speed_40_65/independent_verification.json').read_text(encoding='utf-8'))
    info={'package':name,'build_time_utc':datetime.now(timezone.utc).isoformat(),'platform':'Windows 10/11 (.NET Framework 4.x)',
          'runtime_install_required':False,'input_model_status':v['status'],'runs':len(v['runs']),
          'capacity_checks':sum(r['capacity_checks'] for r in v['runs']),'independent_status':iv['status'],
          'independent_queue_samples':iv['independent_queue_time_samples'],'large_capacity_assumption':60,
          'reverse_capacity':25,'observed_passenger_validation':False,'launcher_sha256':sha(exe),
          'dataset_dir':'data/capacity_v3','bus_speed_max_kmh':{'campus':40,'external':65},
          'assets_manifest_sha256':sha(stage/'assets.sha256'),'public_file_count':len(inputs)}
    if args.adaptive:
        av=json.loads((VIEWER/'adaptive_model/independent_verification.json').read_text(encoding='utf-8'))
        info.update(dataset_dir='data/capacity_v4',comparison_dataset_dir='data/capacity_v3',adaptive=True,
            adaptive_independent_status=av['status'],adaptive_queue_samples=av['exact_queue_samples'],
            adaptive_capacity_events=av['capacity_boarding_queue_events_checked'])
    (stage/'package_info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    assert hashes=={str(s.relative_to(source)).replace('\\','/'):sha(s) for s in inputs}
    files=[f for f in stage.rglob('*') if f.is_file()]
    for f in files:
        if f.suffix.lower() in ('.json','.html','.js','.css','.cs','.txt','.log','.config','.sha256'):
            assert 'C:/Users/' not in f.read_text(encoding='utf-8-sig') and 'C:\\Users\\' not in f.read_text(encoding='utf-8-sig'),f
        if f.name.endswith('.json.gz'):
            obj=gzip.decompress(f.read_bytes()).decode('utf-8');assert 'C:/Users/' not in obj and 'C:\\\\Users\\\\' not in obj
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(files):z.write(f,str(Path(name)/f.relative_to(stage)))
    report={'status':'BUILT','folder':str(stage),'zip':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive),'files':len(files),'public_source_hashes_unchanged':True}
    (RELEASES/(name+'_build.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

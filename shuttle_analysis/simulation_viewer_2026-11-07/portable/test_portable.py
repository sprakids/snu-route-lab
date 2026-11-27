"""Exercise the exact ZIP after extraction, with no Python/Node executable on PATH."""
from pathlib import Path
import argparse,concurrent.futures,gzip,hashlib,json,os,shutil,socket,subprocess,tempfile,time,urllib.request,urllib.error,zipfile
HERE=Path(__file__).resolve().parent
VIEWER=HERE.parent
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
def sha(data):return hashlib.sha256(data).hexdigest()
def state_path(root):
    key=sha(str(root.resolve()).rstrip('\\').upper().encode())[:24]
    return Path(os.environ['LOCALAPPDATA'])/'SNUShuttleMap'/key/'instance.txt'
def read_state(root):
    p=state_path(root)
    if not p.exists():return None
    try:return dict(l.split('=',1) for l in p.read_text(encoding='utf-8-sig').splitlines() if '=' in l)
    except (OSError,ValueError):return None
def launch(root,*args):
    env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    return subprocess.Popen([str(root/'시뮬레이션 실행.exe'),*args],cwd=os.environ['SystemRoot'],env=env,creationflags=FLAGS)
def request(url,method='GET',accept='gzip',host=None):
    headers={'Accept-Encoding':accept}
    if host:headers['Host']=host
    req=urllib.request.Request(url,headers=headers,method=method)
    try:response=urllib.request.urlopen(req,timeout=5)
    except urllib.error.HTTPError as e:response=e
    with response:return response.status,dict(response.headers),response.read()
def wait_ready(root,process):
    for _ in range(100):
        if process.poll() is not None:raise AssertionError('Launcher exited: '+str(process.returncode))
        s=read_state(root)
        if s and s.get('pid')==str(process.pid):
            url='http://127.0.0.1:'+s['port']+'/'
            code,h,b=request(url+'__launcher/health')
            if code==200 and b.decode()=='SNU-Shuttle-Map-v2-20261107\n'+s['digest']:return s,url
        time.sleep(.1)
    raise AssertionError('Launcher did not become ready')
def stop(root,process,url):
    result=launch(root,'--stop');assert result.wait(5)==0
    assert process.wait(5)==0 and not state_path(root).exists()
    try:
        with socket.create_connection(('127.0.0.1',int(url.split(':')[2].rstrip('/'))),timeout=.5):raise AssertionError('Server remained after shutdown')
    except (ConnectionRefusedError,TimeoutError,OSError):pass
def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args()
    zip_path=args.archive.resolve();qa=HERE/'qa';qa.mkdir(exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='SNU_Map_Portable_20261107_'))/'한글 공백 & 괄호 (검증)';temp.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist())
        z.extractall(temp)
    root=next(p for p in temp.iterdir() if p.is_dir());process=None;tests=[]
    try:
        manifest={line[66:]:line[:64] for line in (root/'assets.sha256').read_text(encoding='utf-8').splitlines()}
        assert all(sha((root/p).read_bytes())==h for p,h in manifest.items())
        tests.append({'test':'archive_crc_and_extracted_manifest','files':len(manifest),'pass':True})
        process=launch(root,'--headless');s,url=wait_ready(root,process)
        assert int(s['port'])!=8786
        tests.append({'test':'independent_working_directory_and_no_runtime_on_path','cwd':os.environ['SystemRoot'],'url':url,'pass':True})
        # Compare every served public file byte for byte, including virtual JSON paths.
        def check(item):
            relative,expected=item;route=relative.removeprefix('public/')
            if route.endswith('.json.gz'):route=route[:-3]
            code,headers,body=request(url+route)
            assert code==200 and sha(body)==expected,(route,code)
            if route.endswith('.json'):
                assert headers.get('Content-Encoding')=='gzip'
                decoded=gzip.decompress(body);json.loads(decoded)
                assert decoded==(VIEWER/'public'/route).read_bytes()
            return route
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:served=list(executor.map(check,manifest.items()))
        tests.append({'test':'concurrent_all_assets_match_model_snapshot','files':len(served),'pass':True})
        dataset=json.loads((root/'package_info.json').read_text(encoding='utf-8'))['dataset_dir']
        for accept in ('identity','gzip;q=0'):
            code,headers,body=request(url+dataset+'/peak-mon.json',accept=accept)
            assert code==200 and 'Content-Encoding' not in headers
            assert body==(VIEWER/'public'/dataset/'peak-mon.json').read_bytes()
        code,headers,body=request(url+dataset+'/peak-mon.json',method='HEAD')
        assert code==200 and not body and int(headers['Content-Length'])==(root/'public'/dataset/'peak-mon.json.gz').stat().st_size
        tests.append({'test':'gzip_identity_q0_and_head','pass':True})
        expected={'missing':404,'launcher_source/MapLauncher.cs':404,'assets.sha256':404,'%2e%2e/assets.sha256':403,'%5c..%5cassets.sha256':403}
        for path,code in expected.items():assert request(url+path)[0]==code,path
        assert request(url,method='POST')[0]==405
        assert request(url,host='example.invalid')[0]==403
        tests.append({'test':'read_only_allowlist_and_loopback_host','pass':True})
        duplicate=launch(root,'--headless');assert duplicate.wait(5)==0
        assert read_state(root)==s and process.poll() is None
        tests.append({'test':'duplicate_reuses_existing_instance','pass':True})
        stop(root,process,url);process=None;tests.append({'test':'graceful_stop_closes_port_and_state','pass':True})
        process=launch(root,'--headless');restart_s,restart_url=wait_ready(root,process);assert int(restart_s['pid'])!=int(s['pid'])
        stop(root,process,restart_url);process=None;tests.append({'test':'restart_after_shutdown','pass':True})
        broken=temp.parent/'missing_assets';broken.mkdir()
        for n in ('시뮬레이션 실행.exe','시뮬레이션 실행.exe.config'):shutil.copy2(root/n,broken/n)
        invalid=launch(broken,'--headless');assert invalid.wait(5)==1 and not state_path(broken).exists()
        assert '압축' in (state_path(broken).parent/'launcher.log').read_text(encoding='utf-8-sig')
        tests.append({'test':'incomplete_extraction_reports_error','pass':True})
        changed=temp.parent/'changed_asset';shutil.copytree(root,changed)
        with (changed/'public/index.html').open('a',encoding='utf-8') as f:f.write('\nmodified test fixture\n')
        invalid=launch(changed,'--headless');assert invalid.wait(5)==1 and not state_path(changed).exists()
        assert '변경' in (state_path(changed).parent/'launcher.log').read_text(encoding='utf-8-sig')
        tests.append({'test':'changed_asset_detected_before_start','pass':True})
        result={'status':'PASS','zip':str(zip_path),'zip_sha256':sha(zip_path.read_bytes()),'extracted_test_folder':str(root),
            'launcher_sha256':sha((root/'시뮬레이션 실행.exe').read_bytes()),'tests':tests,
            'platform_tested':'Current Windows 11 x64; other Windows machines not physically tested',
            'no_python_node_or_codex_used_by_launcher':True,'original_viewer_inputs_changed':False}
        (qa/'portable_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    finally:
        if process and process.poll() is None:
            launch(root,'--stop').wait(5)
            try:process.wait(5)
            except subprocess.TimeoutExpired:process.terminate();process.wait(5)
if __name__=='__main__':main()

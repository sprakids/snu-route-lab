"""Serve the candidate beside the original R without altering the original local map."""
from argparse import ArgumentParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import re
import sys

HERE=Path(__file__).resolve().parent
MODEL='R'+HERE.name
VIEWER=HERE.parent/'261124103744/local-map'
sys.path.insert(0,str(VIEWER))
import serve


def assets(directory):
    html=(VIEWER/'index.html').read_text(encoding='utf8').replace(serve.VERSION,MODEL)
    html=html.replace('현재 대기량(가중치)','현재 바깥 대기줄')
    html=html.replace('<p id="next-bus"', '<p id="parked-load" hidden></p><p id="next-bus"')
    html=html.replace('지형 보정 전후','출발·승차 방식 변경 전후')
    html=html.replace('<h3>시내버스 운행계획</h3>',
        '<p>강좌별 조기 종료와 학생별 교내 체류를 가정했습니다. 행정관 셔틀은 정차 중 승차할 수 있습니다. 바깥줄과 차내 출발 대기를 따로 표시합니다. <a href="/model-guide">가정과 검증 결과</a></p><h3>시내버스 운행계획</h3>')
    js=(VIEWER/'viewer.js').read_text(encoding='utf8').replace(serve.VERSION,MODEL)
    anchor='function updateSidebar(force=false){'
    js=js.replace(anchor,"""function onboardWaiting(node,t){
  const rows=state.data.onboard_wait_timeline[node] || [];
  const i=latest(rows,t);
  return i<0?0:rows[i][1];
}
function isTerminal(node){
  const hot=state.common.hot_nodes;
  return node===hot.admin_snu || node===hot.admin_daehak;
}
"""+anchor)
    js=js.replace("$('stop-queue').textContent=fmt(q);","""const parked=$('parked-load');
  parked.hidden=!isTerminal(node);
  if(!parked.hidden){
    const onboard=onboardWaiting(node,state.second);
    parked.textContent='차내 출발 대기 '+fmt(onboard)+'명 · 바깥줄과 합계 '+fmt(q+onboard)+'명 상당';
  }
  $('stop-queue').textContent=fmt(q);""")
    js=js.replace("button.querySelector('[data-row-queue]').textContent=fmt(q);",
                  """button.querySelector('[data-row-queue]').textContent=isTerminal(node)
      ?fmt(q)+' (차내 출발 대기 '+fmt(onboardWaiting(node,state.second))+')':fmt(q);""")
    (directory/'index.html').write_text(html,encoding='utf8')
    (directory/'viewer.js').write_text(js,encoding='utf8')


def main(port):
    shared=serve.resource
    with TemporaryDirectory(prefix='snu-release-dwell-') as d:
        rendered=Path(d)
        assets(rendered)
        def resource(path,page_fetch=False):
            path='/'+path.removeprefix('/'+MODEL+'/').lstrip('/')
            if path in ('/','/index.html','/viewer.js'):
                return rendered/('viewer.js' if path=='/viewer.js' else 'index.html'),None,False
            if path=='/model-guide':
                return HERE/'README.md','text/plain',False
            if path in ('/map-stats.json','/station-access.json'):
                return HERE/(path[1:]+'.gz'),'application/json',True
            if re.fullmatch(r'/viewer-data/(common|(regular|peak)-(mon|tue|wed|thu|fri))\.json',path):
                return HERE/(path[1:]+'.gz'),'application/json',True
            if path=='/integrated.css' or path[1:] in serve.SHARED or path.startswith(('/vendor/','/assets/')):
                return shared(path)
            return None
        serve.resource=resource
        with ThreadingHTTPServer(('127.0.0.1',port),serve.Handler) as server:
            server.serve_forever()


if __name__=='__main__':
    args=ArgumentParser()
    args.add_argument('--port',type=int,default=8797)
    main(args.parse_args().port)

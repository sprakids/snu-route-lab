"""Serve the local demand-model replay on its own port using the research viewer."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
VERSION='R'+HERE.name
VIEWER=HERE.parent/'261124103744/local-map'
sys.path.insert(0,str(VIEWER))
import serve


def main(port):
    assets=serve.resource
    with TemporaryDirectory(prefix='snu-grade-demand-map-') as cache:
        cache=Path(cache)
        for file in ('index.html','viewer.js'):
            source=(VIEWER/file).read_text(encoding='utf8')
            assert serve.VERSION in source
            if file=='index.html':
                source=source.replace('신림선 통합 R</title>','신림선 통합 R · 경사별 도보 수요</title>')
                source=source.replace('신림선 통합 하교 모형</h2>','경사별 도보 수요 모형</h2>')
                source=source.replace('지형 보정 전후의 도보 귀가 비율','경사 선호 변경 전후의 도보 귀가 비율')
                source=source.replace('<h3>시내버스 운행계획</h3>',
                    '<p>도보 선택에서 경사 +10%는 실제 길이의 2배, −10%는 0.75배로 느끼도록 설정했습니다. 지도에 표시하는 보행시간은 실제 경로 길이와 개인별 속도로 계산합니다.</p><h3>시내버스 운행계획</h3>')
            (cache/file).write_text(source.replace(serve.VERSION,VERSION),encoding='utf8')
        def resource(path,page_fetch=False):
            path='/'+path.removeprefix('/'+VERSION+'/').lstrip('/')
            if path in ('/','/index.html','/viewer.js'):
                name='viewer.js' if path=='/viewer.js' else 'index.html'
                return cache/name,None,False
            if path=='/model-guide':
                return HERE/'README.md','text/plain',False
            if path=='/map-stats.json':
                return HERE/'map-stats.json.gz','application/json',True
            if re.fullmatch(r'/viewer-data/(common|(regular|peak)-(mon|tue|wed|thu|fri))\.json',path):
                return HERE/(path[1:]+'.gz'),'application/json',True
            if path=='/integrated.css' or path[1:] in serve.SHARED or path.startswith(('/vendor/','/assets/')):
                return assets(path)
            return None
        # Only this localhost process uses the candidate resource resolver.
        serve.resource=resource
        with ThreadingHTTPServer(('127.0.0.1',port),serve.Handler) as httpd:
            httpd.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8796)
    main(parser.parse_args().port)

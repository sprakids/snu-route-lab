from pathlib import Path
ROOT=Path(__file__).resolve().parent
src=(ROOT/'finalize_results.py').read_text(encoding='utf8')
needle="decision=read(w/'pilot-decision.json');group='grid' if decision['status']=='PILOT_QUALIFIED' else 'pilot'"
assert needle in src
src=src.replace(needle,"decision=read(w/'pilot-decision.json');group='pilot'  # Known initial-anchor issue overrides expansion")
needle="write(w/'RESULTS.md','\\n'.join(s))";assert needle in src
src=src.replace(needle,"s[2:2]=['**본 후보는 초기 배차 시각 기준 불일치가 발견되어 성과 통과와 관계없이 확대/채택에서 제외했습니다. [보존 사유](EXTENSION_BLOCKED.md)를 보십시오. 수정은 별도 자식261116161819에서만 합니다.**','']\n"+needle)
needle="write(w/'START_HERE.md',intro)";assert needle in src
src=src.replace(needle,"intro+='\\n**시간 기준 문제로 확대/채택 제외.** 성과 통과와 별개입니다. [사유](EXTENSION_BLOCKED.md), 수정 자식261116161819을 보십시오.\\n'\n"+needle)
out=ROOT/'finalize_blocked_pilot.py';assert not out.exists();out.write_text(src,encoding='utf8')
print('BLOCKED_REPORT_HELPER_READY')

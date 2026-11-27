"""Extract publicly visible HTML notice text; no browser or gated-file access."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent

class NoticeText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.skip += 1
        if not self.skip and tag in {'p','div','tr','h1','h2','h3','section','br','li'}:
            self.out.append('\n')
        if not self.skip and tag in {'td','th'}:
            self.out.append('\t')
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript', 'svg'} and self.skip:
            self.skip -= 1
        if not self.skip and tag in {'p','div','tr','h1','h2','h3','section','li'}:
            self.out.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)
    def result(self):
        return '\n'.join(line for raw in ''.join(self.out).splitlines()
                         if (line := re.sub(r'[ \t\xa0\r]+', ' ', raw).strip())) + '\n'

rows = []
for name in ['I01_정정입찰공고_보존본문.html', 'I02_정정입찰공고_비드프로.html']:
    path = ROOT / name
    parser = NoticeText()
    parser.feed(path.read_text(encoding='utf-8'))
    output = path.with_suffix('.txt')
    output.write_text(parser.result(), encoding='utf-8')
    if name.startswith('I01_'):
        lines = parser.result().splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith('서울대학교 캠퍼스관리과 공고'))
        end = next(i for i in range(start, len(lines)) if lines[i] == '서울대학교 시설관리국 캠퍼스관리과 분임재무원')
        (ROOT/'입찰공고_본문.txt').write_text(
            '공개 입찰공고의 제3자 보존·변환본문 (체결 계약서 아님)\n'
            '공고번호: 20231243066-01\n'
            '출처: https://www.igunsul.net/detail_bid/?bbscode=8218780&ipchal_eum=\n'
            'HTML 보존본에서 본문만 추출. 글꼴·기호 등의 변환 오류 가능성 있음.\n\n'
            + '\n'.join(lines[start:end+1]) + '\n', encoding='utf-8')
    rows.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'text_file': output.name, 'text_characters': len(parser.result())})
(ROOT/'extraction_manifest.json').write_text(json.dumps({
    'processed_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'source_type': 'Public third-party preservation of tender notice; not signed contract',
    'files': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(rows, ensure_ascii=False, indent=2))

notice = (ROOT/'입찰공고_본문.txt').read_text(encoding='utf-8')
routes = re.findall(r'제([1-8])노선\((\d+)대,\s*(44|25)인승 이상\)', notice)
assert [int(row[0]) for row in routes] == list(range(1, 9))
large = [int(count) for _, count, seats in routes if seats == '44']
small = [int(count) for _, count, seats in routes if seats == '25']
budget = int(re.search(r'사업예산\(기초금액\): 금 ([\d,]+)백만', notice).group(1).replace(',', '')) * 1_000_000
annual_budgets = [int(value.replace(',', '')) * 1_000 for value in re.findall(r'장기계속 [1-3]차: ([\d,]+)천원', notice)]
checks = {
    'large_vehicle_sum': sum(large), 'small_vehicle_sum': sum(small),
    'all_vehicle_sum': sum(large + small), 'route_count': len(large + small),
    'routes_extracted_from_source': routes,
    'budget_won': budget, 'annual_budgets_won': annual_budgets,
    'budget_reconciles': len(annual_budgets) == 3 and sum(annual_budgets) == budget,
    'earlier_news_budget_won': 12_109_800_000,
    'budget_difference_won': budget - 12_109_800_000,
    'source_strings_present': all(s in notice for s in [
        '44인승 이상 28대, 25인승 이상 10대', '금 12,198백만 원',
        '장기계속 3차: 4,066,000천원', '세부 운행조건: 별첨',
        '협상을 통해 과업내용, 가격 등을 조정', '과업지시서 제14조 확인']),
    'signed_current_contract_obtained': False,
    'full_business_schedule_obtained': False,
}
assert checks['large_vehicle_sum'] == 28
assert checks['small_vehicle_sum'] == 10
assert checks['all_vehicle_sum'] == 38 and checks['route_count'] == 8
assert checks['budget_reconciles'] and checks['source_strings_present']
(ROOT/'notice_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(checks, ensure_ascii=False, indent=2))

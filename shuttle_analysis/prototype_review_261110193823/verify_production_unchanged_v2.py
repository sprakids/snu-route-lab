"""Read-only public verification; the data host publishes immutable releases, not latest."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib, json, urllib.request

ROOT = Path(__file__).resolve().parent
SIM = ROOT.parent / 'simulation_viewer_2026-11-07'
MODEL = '261110162302'
PAYLOAD = 'f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130'
MANIFEST = 'ca0b1b487879586a6ca5ed79511e9bd3128f423a95eb18f471d06b4885d55dbc'

def digest(body):
    return hashlib.sha256(body).hexdigest()

def fetch(pair):
    name, url = pair
    item = {'name': name, 'url': url}
    try:
        request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read()
            item.update(status=response.status, bytes=len(body), sha256=digest(body))
        assert item['status'] == 200
        if name == 'lab_latest':
            data = json.loads(body)
            assert data['model_id'] == MODEL and digest(body) == MANIFEST
            item['model_id'] = data['model_id']
        elif name in ('lab_payload', 'data_payload'):
            assert digest(body) == PAYLOAD
            item['expected_payload_match'] = True
        elif name == 'route_api':
            data = json.loads(body)
            sync = data['sync']
            assert data['model_id'] == MODEL and sync['active_model_id'] == MODEL
            assert sync['status'] == 'active' and sync['last_error'] is None
            assert sync['payload_sha256'] == PAYLOAD
            item.update(model_id=MODEL, sync_status=sync['status'], payload_sha256=sync['payload_sha256'])
        else:
            assert digest(body) == digest((SIM / 'public' / name).read_bytes())
            item['local_public_asset_match'] = True
        item['check'] = 'PASS'
    except Exception as exc:
        item.update(check='FAIL', error=type(exc).__name__, message=str(exc))
    return item

def main():
    target = ROOT / 'production_unchanged_verification_v2.json'
    assert not target.exists()
    assert digest((SIM / 'public/routing-model/latest.json').read_bytes()) == MANIFEST
    lab = 'https://snu-shuttle-simulation.vercel.app/'
    release = f'routing-model/releases/{MODEL}.json'
    jobs = [('lab_latest', lab + 'routing-model/latest.json'),
            ('lab_payload', lab + release),
            ('data_payload', 'https://snu-shuttle-v9-data.vercel.app/' + release),
            ('route_api', 'https://snu-route-lab.vercel.app/api/queue-model')]
    jobs += [(name, lab + name) for name in ('index.html', 'viewer-v5.js', 'mobile-lab.js', 'mobile-lab.css')]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(fetch, jobs))
    passed = all(r['check'] == 'PASS' for r in responses)
    result = {'status': 'PASS_V11_UNCHANGED_AND_MOBILE_ASSETS_MATCH' if passed else 'FAILED_READBACK',
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'expected_model_id': MODEL, 'expected_payload_sha256': PAYLOAD,
              'production_writes': False, 'responses': responses,
              'prior_attempt_preserved': 'production_unchanged_verification.json',
              'prior_failure_explanation': 'The verifier assumed latest.json was published on the data-only host. Its release.json payload is the published artifact; no production change was made.'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    assert passed, [(r['name'], r.get('message')) for r in responses if r['check'] != 'PASS']
    print(result['status'], len(responses), MODEL)

if __name__ == '__main__':
    main()

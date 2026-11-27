"""Run a new condition or show its verified result, without duplicating stored runs."""
import argparse
import json
from candidate import HERE, base, run_case

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--day', choices=base.DAYS, default='월')
parser.add_argument('--service', choices=('regular','peak'), default='regular')
parser.add_argument('--weather', choices=('dry','rain'), default='dry')
parser.add_argument('--rate', type=int, choices=range(101), metavar='0..100')
args = parser.parse_args()
rate = args.rate if args.rate is not None else (45 if args.weather=='rain' else 50)
case = HERE/'runs'/f'{args.weather}-{rate}-{args.service}-{base.DAYS[args.day]}'
if not case.exists():
    run_case(args.day, args.service, args.weather, rate)
result = case/'result.json'
if not result.is_file():
    parser.exit(1,f'Case is still running or incomplete: {case}\n')
with result.open(encoding='utf8') as stream:
    data=json.load(stream)
if data['status']!='verified':
    parser.exit(1,f'Case has no verified result: {case}\n')
print(json.dumps({k:data[k] for k in ['selection','candidate','baseline','max_wait_min','over20_weight']},
                 ensure_ascii=False, indent=2))


"""Correct labels only: prepared plan[4] is modeled departure, not raw class end."""
from pathlib import Path
import csv,hashlib,json
ROOT=Path(__file__).resolve().parent
def main():
    source=ROOT/'engineering_snu_half_hour_comparison.json';target=ROOT/'engineering_snu_departure_half_hour_comparison.json'
    assert not target.exists();data=json.loads(source.read_bytes());rows=[]
    for old in data['rows']:
        row=dict(old);row['departure_bin_start']=row.pop('class_end_bin_start');row['departure_bin_end']=row.pop('class_end_bin_end');rows.append(row)
    with (ROOT/'engineering_snu_departure_half_hour_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    target.write_text(json.dumps({**data,'rows':rows,
        'grouping':'Modeled trip departure based on course-end data: prepared plan[4], originally collected from departure[particle]. Not observed class dismissal or queue-entry time.',
        'legacy_label_correction_only_numeric_values_unchanged':True,'legacy_file_preserved':source.name,
        'legacy_sha256':hashlib.sha256(source.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf8')
    print('DEPARTURE_LABELS_CORRECTED',len(rows))
if __name__=='__main__':main()

"""Check produced icon dimensions, references, cache versions and preserved model data."""
import hashlib,json,re,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent
APP=ROOT.parents[1]/'app'
public=APP/'public'
icons={}
for image in (public/'icons').glob('hagyogil-v2-*.png'):
    raw=image.read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    width,height=struct.unpack('>II',raw[16:24]);expected=int(image.stem.rsplit('-',1)[1])
    assert width==height==expected
    icons[image.name]={'width':width,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
ico=(public/'favicon-v2.ico').read_bytes()
assert struct.unpack('<HHH',ico[:6])==(0,1,4)
for n,size in enumerate((16,32,48,64)):
    width,height,colors,reserved,planes,bits,length,offset=struct.unpack('<BBBBHHII',ico[6+16*n:22+16*n])
    assert width==height==size and bits==32 and ico[offset:offset+8]==b'\x89PNG\r\n\x1a\n'
    assert len(ico[offset:offset+length])==length
for page in ['index.html','privacy.html','accessibility.html']:
    html=(public/page).read_text(encoding='utf-8')
    assert '/favicon-v2.ico' in html and '/icons/hagyogil-v2-180.png' in html
    assert '/site-v2.webmanifest' in html and '/brand.css?v=' in html
    assert '/icons/hagyogil-v2-96.png' in html
manifest=json.loads((public/'site-v2.webmanifest').read_text(encoding='utf-8'))
for icon in manifest['icons']:
    assert (public/icon['src'].lstrip('/')).exists()
    assert icon['sizes']==str(icons[Path(icon['src']).name]['width'])+'x'+str(icons[Path(icon['src']).name]['width'])
protected=json.loads((ROOT/'protected-data-hashes.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256(Path(row['Path']).read_bytes()).hexdigest().upper()==row['SHA256'] for row in protected)
result={'status':'PASS','icons':icons,'information_pages':3,'ico_sizes':[16,32,48,64],
    'protected_model_files_unchanged':len(protected),'header_png_bytes':icons['hagyogil-v2-96.png']['bytes'],
    'header_display_size_css_px':48,'old_source_png_preserved':(ROOT.parent/'hagyogil-snu-home-icon-v1.png').exists()}
(ROOT/'asset-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='icons'},ensure_ascii=True,indent=2))

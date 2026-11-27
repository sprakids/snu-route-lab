"""Developer CLI: provision backend credentials from environment into DPAPI, no key output."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from server import crypt, secret, saved_bus_key

NAMES=('KAKAO_JAVASCRIPT_KEY','KAKAO_REST_API_KEY','SEOUL_BUS_SERVICE_KEY')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-env',action='store_true',help='Encrypt developer environment/.env values into the current Windows account store')
    args=parser.parse_args()
    values={name:secret(name) for name in NAMES}
    target=Path(os.environ['LOCALAPPDATA'])/'SnuTransit/credentials/route_lab_settings.dpapi'
    if args.import_env:
        supplied={name:value for name,value in values.items() if value}
        if not supplied:raise SystemExit('No developer credentials supplied; nothing written.')
        if any('\n' in value or '\r' in value or not 16<=len(value)<=512 for value in supplied.values()):
            raise SystemExit('Credential format check failed; nothing written.')
        ciphertext=crypt(json.dumps(supplied).encode())
        if json.loads(crypt(ciphertext,decrypt=True).decode())!=supplied:raise SystemExit('Credential readback failed.')
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='route-lab-',delete=False) as stream:
            stream.write(ciphertext);stream.flush();os.fsync(stream.fileno());temporary=Path(stream.name)
        os.replace(temporary,target)
    existing=bool(saved_bus_key())
    configured={name:bool(value) for name,value in values.items()}
    configured['SEOUL_BUS_SERVICE_KEY']=configured['SEOUL_BUS_SERVICE_KEY'] or existing
    print(json.dumps({'encrypted_backend_store':target.exists(),'configured':configured,
                      'seoul_existing_store_available':existing,'user_key_entry_screen':False}))

if __name__=='__main__':main()

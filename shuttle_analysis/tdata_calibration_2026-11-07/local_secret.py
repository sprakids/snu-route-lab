"""Current-user Windows DPAPI storage. Never print the credential."""
from pathlib import Path
from ctypes import wintypes
import ctypes, os

DIRECTORY=Path(os.environ['LOCALAPPDATA'])/'SnuRouteLab/secrets/tdata'
CREDENTIAL=DIRECTORY/'api-key_20261107.dpapi'

class Blob(ctypes.Structure):
    _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]

def transform(data,protect):
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=library.CryptProtectData if protect else library.CryptUnprotectData
    fn.restype=wintypes.BOOL
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),
                 ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(result.pbData,result.cbData)
    finally:
        free=ctypes.WinDLL('kernel32',use_last_error=True).LocalFree
        free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
        free(ctypes.cast(result.pbData,ctypes.c_void_p))

def load_key():
    return transform(CREDENTIAL.read_bytes(),False).decode('utf-8')

def protect_staged():
    staging=DIRECTORY/'api-key.pending'
    data=staging.read_bytes().strip()
    assert len(data)==36 and b'\n' not in data
    if CREDENTIAL.exists():
        assert transform(CREDENTIAL.read_bytes(),False)==data,'Preserve a different existing credential'
    else:
        encrypted=transform(data,True)
        assert transform(encrypted,False)==data
        with CREDENTIAL.open('xb') as output:output.write(encrypted)
    assert load_key().encode()==data
    staging.unlink()
    assert not staging.exists()
    return {'provider':'T-data','service_id':'1025','issued_date':'2026-11-07',
            'protection':'Windows DPAPI, current user','credential_file':str(CREDENTIAL),
            'round_trip_verified':True,'plaintext_staging_removed':True,'key_printed':False}

if __name__=='__main__':
    import json
    receipt=protect_staged()
    (DIRECTORY/'storage_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

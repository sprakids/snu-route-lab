import os,json,urllib.request,urllib.error
identifier=os.environ.get("BLOB_STORE_ID","")
base="https://"+identifier.removeprefix("store_").lower()+".private.blob.vercel-storage.com/route-lab-v1/qa-state.json?cache=0"
checks=[]
for name in ("VERCEL_OIDC_TOKEN","BLOB_READ_WRITE_TOKEN"):
    token=os.environ.get(name)
    if not token:continue
    request=urllib.request.Request(base,headers={"Authorization":"Bearer "+token,"x-vercel-blob-store-id":identifier,"x-api-version":"12"})
    try:
        with urllib.request.urlopen(request,timeout=10) as response:status=response.status
    except urllib.error.HTTPError as error:status=error.code;error.close()
    checks.append({"credential_variable":name,"http_status":status,"classic_blob_token":token.startswith("vercel_blob_rw_")})
print(json.dumps({"configured_store":bool(identifier),"checks":checks}))

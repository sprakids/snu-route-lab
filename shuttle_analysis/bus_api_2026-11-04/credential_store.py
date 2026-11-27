"""Store the user's Seoul bus API key using Windows CurrentUser DPAPI.

The encrypted file lives outside the project. This module never prints a key.
Reference: https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
"""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile


FORMAT = "snu-transit-seoul-bus-key-v1"


def default_path():
    return Path(os.environ["LOCALAPPDATA"]) / "SnuTransit" / "credentials" / "seoul_bus_service_key.dpapi"


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(payload, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("This credential store requires Windows DPAPI")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(payload)
    input_blob = Blob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = Blob()
    if decrypt:
        fn = crypt32.CryptUnprotectData
        description = None
        second_type = ctypes.c_void_p
    else:
        fn = crypt32.CryptProtectData
        description = "SNU Transit Seoul bus API key"
        second_type = wintypes.LPCWSTR
    fn.argtypes = [ctypes.POINTER(Blob), second_type, ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    # UI_FORBIDDEN only; LOCAL_MACHINE is deliberately not set.
    succeeded = fn(ctypes.byref(input_blob), description, None, None, None, 1, ctypes.byref(output_blob))
    try:
        if not succeeded:
            raise RuntimeError("Windows DPAPI operation failed (code %d)" % ctypes.get_last_error())
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.memset(ctypes.addressof(source), 0, len(payload))
        if output_blob.pbData:
            ctypes.memset(output_blob.pbData, 0, output_blob.cbData)
            kernel32.LocalFree(output_blob.pbData)


def save_key(key, path=None):
    key = key.strip()
    if not key:
        raise ValueError("An empty credential cannot be saved")
    target = Path(path) if path is not None else default_path()
    package = {"format": FORMAT, "api_key": key,
               "sha256": hashlib.sha256(key.encode("utf-8")).hexdigest()}
    encrypted = crypt(json.dumps(package).encode("utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    # Replace only this named credential after a complete encrypted write.
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + ".", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if load_key(temporary) != key:
            raise RuntimeError("Encrypted credential readback did not match")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def load_key(path=None):
    target = Path(path) if path is not None else default_path()
    if not target.exists():
        return None
    package = json.loads(crypt(target.read_bytes(), decrypt=True).decode("utf-8"))
    key = package.get("api_key")
    if package.get("format") != FORMAT or not isinstance(key, str) or not key:
        raise ValueError("Encrypted credential has an invalid format")
    if not hmac.compare_digest(hashlib.sha256(key.encode("utf-8")).hexdigest(), package.get("sha256", "")):
        raise ValueError("Encrypted credential integrity check failed")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    importer = sub.add_parser("import-key-file")
    importer.add_argument("path", type=Path)
    importer.add_argument("--consume-task-temp-file", action="store_true")
    args = parser.parse_args()
    if args.command == "import-key-file":
        if args.consume_task_temp_file:
            temp_root = Path(os.environ["TEMP"]).resolve()
            if args.path.resolve().parent != temp_root or not args.path.name.startswith("seoul-bus-"):
                raise ValueError("Refusing to consume a file outside this task's temporary handoff")
        target = save_key(args.path.read_text(encoding="utf-8"))
        if args.consume_task_temp_file:
            args.path.unlink()
        print(json.dumps({"saved": True, "protection": "Windows CurrentUser DPAPI", "path": str(target)}))
    else:
        target = default_path()
        print(json.dumps({"saved": target.exists(), "protection": "Windows CurrentUser DPAPI", "path": str(target)}))


if __name__ == "__main__":
    main()

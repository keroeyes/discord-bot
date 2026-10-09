"""Windows DPAPI storage for an optional development-only E2B credential."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import runpy
import sys

class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

def crypt(value, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is required")
    source = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise RuntimeError("Windows credential protection failed")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))

def save_key(path, key):
    if not re.fullmatch(r"e2b_[A-Za-z0-9_-]{20,200}", key):
        raise ValueError("Invalid E2B key format")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = crypt(key.encode())
    path.write_bytes(payload)
    if crypt(path.read_bytes(), True).decode() != key:
        raise RuntimeError("Credential verification failed")

def load_key(path):
    return crypt(Path(path).read_bytes(), True).decode()

def smoke():
    from e2b import Sandbox
    sandbox = None
    try:
        sandbox = Sandbox.create(timeout=60, secure=True)
        result = sandbox.commands.run("python -c 'print(1 + 1)'", timeout=20)
        passed = result.exit_code == 0 and result.stdout.strip() == "2"
        print(json.dumps({"sandbox_created": True, "synthetic_command_passed": passed}))
        if not passed:
            raise RuntimeError("Synthetic command failed")
    finally:
        if sandbox is not None:
            sandbox.kill()
            print(json.dumps({"sandbox_terminated": True}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credential-file", required=True)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--worker", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.save:
        save_key(args.credential_file, sys.stdin.read().strip())
        print(json.dumps({"credential_saved_encrypted": True, "roundtrip_verified": True}))
        return
    os.environ["E2B_API_KEY"] = load_key(args.credential_file)
    if args.smoke:
        smoke()
    elif args.worker is not None:
        sys.argv = [str(Path(__file__).with_name("worker.py")), *args.worker]
        runpy.run_path(sys.argv[0], run_name="__main__")
    else:
        print(json.dumps({"credential_available": True}))
if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"status": "failed"}))
        sys.exit(1)

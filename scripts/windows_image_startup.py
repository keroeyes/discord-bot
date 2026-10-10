"""Per-user Windows login startup. No administrator or policy changes required."""
import argparse
import base64
import ctypes
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(command, data=None):
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
        input=data, text=True, encoding='utf-8', capture_output=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError('Windows configuration operation failed.')
    return result.stdout.strip()


def protect(token):
    # Token travels through stdin, never command-line arguments or shell history.
    encoded = base64.b64encode(token.encode('utf-8')).decode('ascii')
    return powershell(
        'Add-Type -AssemblyName System.Security; '
        '$b=[Convert]::FromBase64String([Console]::In.ReadToEnd()); '
        '[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect('
        '$b,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))', encoded)


def unprotect(cipher):
    encoded = powershell(
        'Add-Type -AssemblyName System.Security; '
        '$b=[Convert]::FromBase64String([Console]::In.ReadToEnd()); '
        '[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Unprotect('
        '$b,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))', cipher)
    return base64.b64decode(encoded, validate=True).decode('utf-8')


def ready(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/object_info/CheckpointLoaderSimple', timeout=3) as response:
            return 'CheckpointLoaderSimple' in json.loads(response.read(1048576))
    except Exception:
        return False


def validate(config):
    if not config['owner'].isdigit() or int(config['owner']) <= 0:
        raise ValueError('Invalid Discord user ID.')
    if not 1 <= config['port'] <= 65535:
        raise ValueError('Invalid ComfyUI port.')
    model = config['checkpoint']
    if not model or '/' in model or '\\' in model:
        raise ValueError('Invalid checkpoint name.')
    for key in ('python', 'pythonw', 'worker', 'comfy'):
        if not Path(config[key]).is_file():
            raise ValueError(f'Missing file: {key}')
    if Path(config['comfy']).suffix.lower() != '.exe':
        raise ValueError('Choose the ComfyUI Desktop executable.')


def shortcut(config, runner, link):
    powershell(
        '$s=New-Object -ComObject WScript.Shell; '
        f'$l=$s.CreateShortcut({ps_quote(link)}); '
        f'$l.TargetPath={ps_quote(config["pythonw"])}; '
        f'$l.Arguments={ps_quote(subprocess.list2cmdline([str(runner), "--run"]))}; '
        f'$l.WorkingDirectory={ps_quote(Path(config["worker"]).parent)}; '
        '$l.Save()')


def install(state, link):
    from tkinter import Tk, filedialog
    project = Path(__file__).resolve().parent.parent
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    comfy = filedialog.askopenfilename(title='Select ComfyUI Desktop executable',
                                      filetypes=[('Windows executable', '*.exe')])
    root.destroy()
    if not comfy:
        raise ValueError('Installation cancelled.')
    config = {
        'comfy': comfy,
        'owner': input('Discord user ID: ').strip(),
        'port': int(input('ComfyUI port [8188]: ').strip() or '8188'),
        'checkpoint': input('Checkpoint [sd_xl_base_1.0.safetensors]: ').strip() or 'sd_xl_base_1.0.safetensors',
        'python': str(project / '.venv-images' / 'Scripts' / 'python.exe'),
        'pythonw': str(project / '.venv-images' / 'Scripts' / 'pythonw.exe'),
        'worker': str(project / 'image_worker.py'),
    }
    validate(config)
    if not ready(config['port']):
        raise ValueError('Start ComfyUI and check its port first.')
    token = getpass.getpass('Existing Discord bot token (hidden): ').strip()
    if not token:
        raise ValueError('Empty token.')
    cipher = protect(token)
    if unprotect(cipher) != token:
        raise RuntimeError('Token encryption verification failed.')
    del token
    state.mkdir(parents=True, exist_ok=True)
    # Do not persist plaintext credentials or log configuration contents.
    (state / 'token.dpapi').write_text(cipher, encoding='ascii')
    (state / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    runner = state / 'startup.py'
    runner.write_bytes(Path(__file__).read_bytes())
    (state / 'enabled').touch()
    try:
        shortcut(config, runner, link)
    except Exception:
        (state / 'enabled').unlink(missing_ok=True)
        raise
    print('Login startup installed. Stop the manual image worker with Ctrl+C first.')
    print('Then run this installer with --start, or sign out and sign in.')


def supervise(state):
    # A session mutex prevents two startup supervisors from launching two workers.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, 'Local\\KeroroLocalImageStartup')
    if not handle:
        raise RuntimeError('Cannot acquire startup lock.')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return
    child = None
    try:
        config = json.loads((state / 'config.json').read_text(encoding='utf-8'))
        validate(config)
        env = os.environ.copy()
        env.update(DISCORD_TOKEN=unprotect((state / 'token.dpapi').read_text(encoding='ascii')),
                   IMAGE_OWNER_ID=config['owner'], COMFYUI_PORT=str(config['port']),
                   COMFYUI_CHECKPOINT=config['checkpoint'])
        comfy_attempted = False
        while (state / 'enabled').exists():
            if not ready(config['port']):
                if not comfy_attempted:
                    subprocess.Popen([config['comfy']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    comfy_attempted = True
                (state / 'status.txt').write_text('Waiting for ComfyUI.', encoding='utf-8')
                time.sleep(5)
                continue
            child = subprocess.Popen([config['python'], config['worker']], env=env,
                cwd=Path(config['worker']).parent, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            (state / 'status.txt').write_text('Worker process started; Discord delivery not yet verified.', encoding='utf-8')
            while child.poll() is None and (state / 'enabled').exists():
                time.sleep(2)
            if not (state / 'enabled').exists():
                break
            (state / 'status.txt').write_text('Worker exited; retrying in 60 seconds.', encoding='utf-8')
            time.sleep(60)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='install', choices=['install'])
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('This installer runs only on Windows.')
    state = Path(os.environ['LOCALAPPDATA']) / 'KeroroLocalImages'
    link = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/KeroroLocalImages.lnk'
    if args.remove:
        (state / 'enabled').unlink(missing_ok=True)
        link.unlink(missing_ok=True)
        for name in ('token.dpapi', 'config.json'):
            (state / name).unlink(missing_ok=True)
        print('Startup removed. ComfyUI was left open.')
    elif args.start:
        config = json.loads((state / 'config.json').read_text(encoding='utf-8'))
        subprocess.Popen([config['pythonw'], str(state / 'startup.py'), '--run'],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        print('Startup supervisor launched; test a new Discord image request.')
    elif args.run:
        try:
            supervise(state)
        except Exception:
            state.mkdir(parents=True, exist_ok=True)
            (state / 'status.txt').write_text('Startup failed. Run the installer again.', encoding='utf-8')
    else:
        install(state, link)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Setup failed ({type(exc).__name__}). Check inputs and Windows configuration.')
        sys.exit(1)

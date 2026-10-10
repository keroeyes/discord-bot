import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('windows_image_startup', Path(__file__).parents[1] / 'scripts/windows_image_startup.py')
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def test_secret_uses_stdin_not_command_arguments(self):
        import base64
        secret = 'synthetic-test-secret'
        with patch.object(startup, 'powershell', return_value='encrypted') as call:
            self.assertEqual(startup.protect(secret), 'encrypted')
        command, stdin = call.call_args.args
        self.assertNotIn(secret, command)
        self.assertEqual(base64.b64decode(stdin).decode(), secret)
        self.assertIn('CurrentUser', command)
        self.assertNotIn('LocalMachine', command)

    def test_shortcut_quotes_paths_and_contains_no_secret(self):
        with patch.object(startup, 'powershell') as call:
            startup.shortcut({'pythonw': "C:/a'b/pythonw.exe", 'worker': 'C:/bot/image_worker.py'}, Path('C:/a b/startup.py'), Path('C:/a b/startup.lnk'))
        command = call.call_args.args[0]
        self.assertIn("a''b", command)
        self.assertIn('--run', command)
        self.assertNotIn('DISCORD_TOKEN', command)
        self.assertNotIn('ExecutionPolicy', command)

    def test_rejects_bad_owner_port_model_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'ComfyUI.exe'
            exe.touch()
            config = dict(owner='123456789012345678', port=8188, checkpoint='sdxl.safetensors',
                          python=str(exe), pythonw=str(exe), worker=str(exe), comfy=str(exe))
            startup.validate(config)
            for key, value in [('owner', 'account-name'), ('port', 0), ('checkpoint', '../model'), ('python', str(exe) + 'missing')]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    startup.validate(dict(config, **{key: value}))

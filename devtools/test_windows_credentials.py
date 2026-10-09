import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import windows_credentials as credentials

class CredentialTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_encrypted_roundtrip_and_tamper_rejection(self):
        key = "e2b_" + "synthetic" * 5
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential.dpapi"
            credentials.save_key(path, key)
            self.assertEqual(credentials.load_key(path), key)
            self.assertNotIn(key.encode(), path.read_bytes())
            path.write_bytes(b"invalid encrypted content")
            with self.assertRaises(RuntimeError):
                credentials.load_key(path)

    def test_invalid_input_creates_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential.dpapi"
            with self.assertRaises(ValueError):
                credentials.save_key(path, "invalid")
            self.assertFalse(path.exists())

    def test_autopatcher_receives_encrypted_key_without_cli_secret(self):
        import sys
        with patch.dict(os.environ, {}, clear=False), patch.object(
                sys, "argv", ["runner", "--credential-file", "synthetic.dpapi",
                "--autopatcher", "--state-dir", "synthetic-state", "--job", "synthetic"]), patch.object(
                credentials, "load_key", return_value="synthetic-key"), patch.object(
                credentials.runpy, "run_path") as run:
            credentials.main()
            self.assertTrue(run.call_args.args[0].endswith("autopatcher.py"))
            self.assertEqual(sys.argv[1:], ["--state-dir", "synthetic-state", "--job", "synthetic"])
            self.assertEqual(os.environ["E2B_API_KEY"], "synthetic-key")
            self.assertNotIn("synthetic-key", str(sys.argv))

    def test_smoke_cleans_up_after_failed_command(self):
        killed = []
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic error")
        sandbox = SimpleNamespace(commands=SimpleNamespace(run=fail), kill=lambda: killed.append(True))
        with patch("e2b.Sandbox.create", return_value=sandbox):
            with self.assertRaises(RuntimeError):
                credentials.smoke()
        self.assertEqual(killed, [True])

if __name__ == "__main__":
    unittest.main()

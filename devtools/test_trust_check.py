"""Offline regression tests for security evidence, never real TLS/E2B calls."""
import contextlib
import inspect
import io
import json
import ssl
import unittest
from unittest.mock import patch, MagicMock

import trust_check


class TrustCheckTests(unittest.TestCase):
    def test_rejects_pre_advisory_versions_and_prereleases(self):
        for name, old in (("certifi", "2026.7.22"), ("pip", "26.2.1"), ("uv", "0.13.1")):
            floor = trust_check.FLOORS[name]
            self.assertEqual(trust_check.version_status(old, floor), "update_required")
            self.assertEqual(trust_check.version_status(floor, floor), "meets_floor")
            self.assertEqual(trust_check.version_status(floor + "rc1", floor), "unknown")
        self.assertEqual(trust_check.version_status(None, "0.13.4"), "unknown")
        self.assertEqual(trust_check.version_status("0.13.10", "0.13.4"), "meets_floor")

    def test_only_ca_verification_errors_establish_rejection(self):
        for code, expected in ((20, "ca_rejected"), (10, "inconclusive_tls_error"),
                               (62, "inconclusive_tls_error")):
            error = ssl.SSLCertVerificationError("synthetic-private-detail")
            error.verify_code = code
            outer = RuntimeError("synthetic-private-detail")
            outer.__cause__ = error
            self.assertEqual(trust_check.classify_error(outer), expected)
        self.assertEqual(trust_check.classify_error(TimeoutError()), "network_or_client_error")

    def test_network_errors_are_not_security_success(self):
        with patch("trust_check.socket.create_connection", side_effect=OSError("synthetic-secret")):
            self.assertEqual(trust_check.probe_ssl(trust_check.HOSTS[0]), "network_or_client_error")
        with patch("httpx.Client", side_effect=TimeoutError("synthetic-secret")):
            self.assertEqual(trust_check.probe_httpx(trust_check.HOSTS[0]), "network_or_client_error")

    def test_httpx_probe_uses_verification_and_does_not_follow_redirects(self):
        with patch("httpx.Client") as client:
            self.assertEqual(trust_check.probe_httpx(trust_check.HOSTS[0]), "accepted")
        client.assert_called_once_with(timeout=10, follow_redirects=False)
        client.return_value.__enter__.return_value.stream.assert_called_once_with(
            "GET", "https://" + trust_check.HOSTS[0] + "/")

    def test_uv_on_path_cannot_be_hidden_by_updated_python_distribution(self):
        with patch("trust_check.metadata.version", return_value="2026.10.19"), \
             patch("trust_check.shutil.which", return_value="synthetic-path"), \
             patch("trust_check.command_version", side_effect=["uv 0.13.1", "uvx 0.13.1", "synthetic-ca"]):
            report = trust_check.inventory()
        self.assertEqual(report["packages"]["uv"]["status"], "meets_floor")
        self.assertEqual(report["packages"]["uv_path"]["status"], "update_required")
        self.assertFalse(trust_check.report_ok(report, require_uv=True))

    def test_default_is_offline_and_does_not_disclose_override_values(self):
        output = io.StringIO()
        with patch("sys.argv", ["trust_check"]), \
             patch.dict("os.environ", {"SSL_CERT_FILE": "synthetic-private-path"}), \
             patch("trust_check.metadata.version", return_value="2026.10.19"), \
             patch("trust_check.command_version", return_value=None), \
             patch("trust_check.probe_httpx") as http, patch("trust_check.probe_ssl") as native, \
             patch("e2b.Sandbox.create") as create, contextlib.redirect_stdout(output):
            self.assertEqual(trust_check.main(), 0)
        http.assert_not_called()
        native.assert_not_called()
        create.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertIn("SSL_CERT_FILE", report["configured_overrides"])
        self.assertNotIn("synthetic-private-path", output.getvalue())
        self.assertEqual(report["native_os_revocation"], "not_checked")
        self.assertEqual(report["e2b_pyqwest_transport"], "not_checked")
        self.assertNotIn("probes", report)

    def test_probe_exit_requires_both_clients_to_reject_both_chains(self):
        for result, expected in (("accepted", 1), ("network_or_client_error", 1), ("ca_rejected", 0)):
            with patch("sys.argv", ["trust_check", "--probe"]), \
                 patch("trust_check.metadata.version", return_value="2026.10.19"), \
                 patch("trust_check.command_version", return_value=None), \
                 patch("trust_check.probe_httpx", return_value="ca_rejected") as http, \
                 patch("trust_check.probe_ssl", side_effect=["ca_rejected", result]) as native, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(trust_check.main(), expected)
            self.assertEqual(http.call_count, 2)
            self.assertEqual(native.call_count, 2)

    def test_pinned_e2b_create_signature_still_accepts_worker_arguments(self):
        from e2b import Sandbox
        # Binding the real installed SDK signature performs no network request.
        inspect.signature(Sandbox.create).bind(timeout=300, secure=True)

    def test_pinned_e2b_uses_system_ca_transport_without_any_api_request(self):
        from e2b.api import client_sync
        # Exercise the pinned SDK's real transport builder, but replace the
        # network transport constructor. No Sandbox or authenticated API client.
        with patch.dict(client_sync._transports, {}, clear=True), \
             patch.dict(client_sync._pools, {}, clear=True), \
             patch.object(client_sync, "SyncHTTPTransport") as transport:
            client_sync.get_pyqwest_transport(None, retry_connect=False)
        self.assertTrue(transport.call_args.kwargs["tls_include_system_certs"])
        self.assertFalse(transport.call_args.kwargs["follow_redirects"])


if __name__ == "__main__":
    unittest.main()

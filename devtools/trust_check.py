"""Read-only eMudhra checks; no E2B API, credentials, installs or model calls.

Default: offline version inventory. --probe: credential-free TLS requests to
the two advisory hosts, using generic HTTPX defaults and Python's default SSL
context. E2B 2.55.0's pyqwest/system-CA transport is separate and is NOT probed.
A network error is never evidence of distrust.
"""
import argparse
from importlib import metadata
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys

FLOORS = {"certifi": "2026.10.19", "pip": "26.2.2", "uv": "0.13.4"}
HOSTS = ("dv-g3b-emudhra.we-have-a-problem.com",
         "dv-g3b-aaa-emudhra.we-have-a-problem.com")
OVERRIDES = ("SSL_CERT_FILE", "SSL_CERT_DIR", "PIP_CERT", "REQUESTS_CA_BUNDLE",
             "CURL_CA_BUNDLE", "UV_SYSTEM_CERTS", "UV_NATIVE_TLS", "UV_INSECURE_HOST",
             "PIP_TRUSTED_HOST", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def version_status(value, floor):
    # Do not silently count prereleases or unrecognized CLI output as patched.
    if not value or not re.fullmatch(r"\d+(?:\.\d+)+", value):
        return "unknown"
    return "meets_floor" if tuple(map(int, value.split("."))) >= tuple(
        map(int, floor.split("."))) else "update_required"


def command_version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=10, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def inventory():
    packages = {}
    for name, floor in FLOORS.items():
        try:
            value = metadata.version(name)
        except metadata.PackageNotFoundError:
            value = None
        packages[name] = {"version": value, "status": version_status(value, floor)}
    # An independently installed uv/uvx can shadow the Python distribution.
    for name in ("uv", "uvx"):
        raw = command_version([name, "--version"]) if shutil.which(name) else None
        match = re.fullmatch(r"uvx? (\d+(?:\.\d+)+)(?: .*)?", raw or "")
        value = match.group(1) if match else None
        packages[name + "_path"] = {"version": value,
            "status": version_status(value, FLOORS["uv"])}
    ca = command_version(["dpkg-query", "-W", "-f=${Version}", "ca-certificates"])
    return {"platform": platform.system(), "python": platform.python_version(),
        "packages": packages, "os_ca_package": ca,
        "e2b_pyqwest_transport": "not_checked",
        "native_os_revocation": "not_checked",
        "configured_overrides": sorted(name for name in OVERRIDES
            if os.environ.get(name) or os.environ.get(name.lower())),
        "e2b_connection": "not_checked", "codex_model_call": "not_checked"}


def classify_error(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            # Expiry/hostname errors do not establish removal of a compromised CA.
            return "ca_rejected" if error.verify_code in {19, 20, 21, 23, 27} else "inconclusive_tls_error"
        error = error.__cause__ or error.__context__
    return "network_or_client_error"


def probe_httpx(host):
    try:
        import httpx
        # Generic HTTPX/certifi, including configured CA/proxy overrides.
        # This is NOT E2B's pyqwest/system-CA transport. No API credentials.
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            with client.stream("GET", "https://" + host + "/"):
                return "accepted"
    except Exception as error:
        return classify_error(error)


def probe_ssl(host):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host):
                return "accepted"
    except Exception as error:
        return classify_error(error)


def report_ok(report, require_uv=False):
    required = ["certifi", "pip"]
    if require_uv:
        required += ["uv", "uv_path", "uvx_path"]
    return (sys.version_info >= (3, 11)
        and all(report["packages"][name]["status"] == "meets_floor" for name in required)
        and all(result == "ca_rejected" for results in report.get("probes", {}).values()
                for result in results.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-uv", action="store_true", help="Check Serena's uv and uvx on PATH too")
    parser.add_argument("--probe", action="store_true", help="TLS requests only; no E2B sandbox or model call")
    args = parser.parse_args()
    report = inventory()
    if args.probe:
        report["probes"] = {host: {"httpx": probe_httpx(host), "python_ssl": probe_ssl(host)}
                            for host in HOSTS}
    print(json.dumps(report, sort_keys=True))
    return 0 if report_ok(report, args.require_uv) else 1


if __name__ == "__main__":
    sys.exit(main())

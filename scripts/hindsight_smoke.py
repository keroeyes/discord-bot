"""Explicit, synthetic-only smoke test for the deployed Hindsight API."""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone


async def smoke(url, api_key):
    from hindsight_client import Hindsight
    from hindsight_client_api.exceptions import ApiException

    bank = "smoke-" + uuid.uuid4().hex
    marker = "smoketoken" + uuid.uuid4().hex
    client = Hindsight(base_url=url, api_key=api_key, timeout=20, max_attempts=1)
    deleted = False
    print(f"Temporary bank: {bank}", flush=True)
    try:
        retained = await asyncio.wait_for(client.aretain(
            bank_id=bank,
            content=f"The synthetic smoke test verification token is {marker}.",
            timestamp=datetime.now(timezone.utc),
            document_id="smoke-document",
            context="Synthetic connection test; no real user data.",
            retain_async=False,
        ), timeout=90)
        if not retained.success:
            raise RuntimeError("retain was not confirmed")
        print("PASS retain", flush=True)

        recalled = await asyncio.wait_for(client.arecall(
            bank_id=bank, query="What is the synthetic smoke test verification token?",
            budget="low", max_tokens=1200,
        ), timeout=25)
        if not any(marker in item.text for item in recalled.results):
            raise RuntimeError("recall did not return the unique synthetic token")
        print("PASS recall", flush=True)

        # Unlike the bot's forgiving delete wrapper, require a successful DELETE.
        await asyncio.wait_for(client.adelete_bank(bank_id=bank), timeout=25)
        deleted = True
        try:
            await asyncio.wait_for(client.arecall(
                bank_id=bank, query="synthetic smoke test verification token",
                budget="low", max_tokens=1200,
            ), timeout=25)
        except ApiException as exc:
            if exc.status != 404:
                raise
        else:
            raise RuntimeError("deleted bank is still accessible; expected HTTP 404")
        print("PASS delete (recall returned HTTP 404)", flush=True)
    finally:
        try:
            if not deleted:
                try:
                    await asyncio.wait_for(client.adelete_bank(bank_id=bank), timeout=25)
                    print("Temporary bank cleanup completed", flush=True)
                except ApiException as exc:
                    if exc.status != 404:
                        print(f"CLEANUP FAILED: manually delete temporary bank {bank}", file=sys.stderr)
                        raise RuntimeError("temporary bank cleanup failed") from None
                except Exception:
                    print(f"CLEANUP FAILED: manually delete temporary bank {bank}", file=sys.stderr)
                    raise RuntimeError("temporary bank cleanup failed") from None
        finally:
            await client.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="Explicitly run retain/recall/delete against HINDSIGHT_URL")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; this test contacts the configured Hindsight server")
    url = os.getenv("HINDSIGHT_URL", "").strip()
    if not url:
        parser.error("HINDSIGHT_URL is required")
    try:
        asyncio.run(smoke(url, os.getenv("HINDSIGHT_API_KEY")))
    except KeyboardInterrupt:
        print("INTERRUPTED: check the printed temporary bank for cleanup", file=sys.stderr)
        return 1
    except Exception as exc:
        # Do not log exception text, request bodies, credentials, or server URLs.
        print(f"FAIL Hindsight smoke test ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

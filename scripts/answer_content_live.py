"""Opt-in real provider evaluation of fixed synthetic questions only.
No Discord, memory lookup/write, Langfuse, DeepEval or external judge.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from answer_evals.content import CASES, evaluate
from subscription import SubscriptionAnswers


async def run():
    # Disable client logs; never print response text or exception messages.
    logging.disable(logging.CRITICAL)
    client = SubscriptionAnswers(os.environ['HINDSIGHT_URL'], os.getenv('HINDSIGHT_API_KEY'))
    passed = True
    # Synthetic source fixture and injected search failure are offline tests.
    # Live endpoint does not expose search-failure injection or source snapshots.
    for case in (CASES[0], CASES[2], CASES[3]):
        try:
            text = await client.answer(case.query, list(case.facts))
            result = evaluate(case, text)
            ok = all(result.values())
            print(case.id, 'PASS' if ok else 'FAIL', result)
        except Exception:
            ok = False
            print(case.id, 'ERROR')
        passed &= ok
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Authorize 3 real model calls; usage/cost may apply')
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required; no model calls were made')
    if not os.getenv('HINDSIGHT_URL'):
        parser.error('HINDSIGHT_URL is required')
    raise SystemExit(asyncio.run(run()))

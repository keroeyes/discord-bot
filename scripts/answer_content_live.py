"""Opt-in fixed synthetic/public questions. No user bank or external judge.
Run in the existing private service environment; never expose its endpoint.
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aiohttp
from answer_evals.content import CASES, evaluate
from answer_evals.official import fetch_snapshot, evaluate_latest
from subscription import validate_answer

LATEST_QUERY = ('현재 Python의 최신 정식 안정 버전은 무엇인가요? 프리릴리스는 제외하고 '
                'https://www.python.org/downloads/ 공식 원문을 웹 검색으로 확인해 주세요. '
                '최신 버전 하나와 근거 URL만 답하세요.')


async def request_answer(query, facts):
    headers = {'Authorization': 'Bearer ' + os.environ['HINDSIGHT_API_KEY']} if os.getenv('HINDSIGHT_API_KEY') else {}
    url = os.environ['HINDSIGHT_URL'].rstrip('/') + '/ext/answers'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=190)) as session:
        async with session.post(url, json={'query': query, 'facts': facts},
                                headers=headers, allow_redirects=False) as response:
            if response.status != 200:
                raise RuntimeError('Provider unavailable')
            body = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                body.extend(chunk)
                if len(body) > 262144:
                    raise ValueError('Provider response too large')
            import json
            return validate_answer(json.loads(body))


async def run():
    logging.disable(logging.CRITICAL)
    passed = True
    for case in (CASES[0], CASES[2], CASES[3]):
        try:
            data = await request_answer(case.query, list(case.facts))
            result = evaluate(case, data['text'], data['sources'], data['search_count'])
            ok = all(result.values())
            print(case.id, 'PASS' if ok else 'FAIL', result)
        except Exception:
            ok = False
            print(case.id, 'ERROR')
        passed &= ok
    # Only a fixed public query is searched. Synthetic private memory is absent.
    # Refresh the independent official oracle before AND after model execution.
    try:
        before = await asyncio.to_thread(fetch_snapshot)
        data = await request_answer(LATEST_QUERY, [])
        after = await asyncio.to_thread(fetch_snapshot)
        result = evaluate_latest(data['text'], data['sources'], data['search_count'], before, after)
        ok = all(result.values())
        print('official_latest', 'PASS' if ok else 'FAIL', result)
    except Exception:
        ok = False
        print('official_latest', 'ERROR')
    return 0 if passed and ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Authorize at most 4 real model calls; usage/cost may apply')
    args = parser.parse_args(argv)
    if not args.run:
        parser.error('--run is required; no model calls were made')
    if not os.getenv('HINDSIGHT_URL'):
        parser.error('HINDSIGHT_URL is required; no model calls were made')
    return asyncio.run(run())


if __name__ == '__main__':
    raise SystemExit(main())

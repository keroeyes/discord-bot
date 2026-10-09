"""Private subscription answer protocol; contains no credentials or model tools."""
import json
import re
from urllib.parse import urlsplit
import aiohttp


def valid_source_url(url):
    if (not isinstance(url, str) or not url or len(url) >= 2000
            or re.search(r'[\s<>\\\\\x00-\x1f\x7f]', url)):
        return False
    try:
        parsed = urlsplit(url)
        return bool(parsed.scheme in {'http', 'https'} and parsed.hostname
                    and parsed.username is None and parsed.password is None
                    and (parsed.port is None or 0 < parsed.port <= 65535))
    except ValueError:
        return False


def validate_answer(data):
    """Validate protocol metadata; this does not establish factual truth."""
    if (not isinstance(data, dict) or data.get('version') != 'subscription-search-v3'
            or not isinstance(data.get('text'), str) or not data['text'].strip()
            or len(data['text']) > 60000
            or type(data.get('search_count')) is not int or data['search_count'] < 0
            or not isinstance(data.get('sources'), list) or len(data['sources']) > 8
            or any(not valid_source_url(url) for url in data['sources'])):
        raise ValueError('Invalid subscription response')
    return data


class SearchEvidence:
    def __init__(self):
        self.search_ids = set()
        self.sources = []

    def observe(self, event):
        if not isinstance(event, dict):
            return
        items = []
        if event.get('type') == 'response.output_item.done':
            items = [event.get('item', {})]
        elif event.get('type') == 'response.completed':
            response = event.get('response')
            items = response.get('output', []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'web_search_call' and item.get('status') == 'completed':
                search_id = item.get('id')
                if isinstance(search_id, str) and search_id:
                    self.search_ids.add(search_id)
            parts = item.get('content', [])
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict) or not isinstance(part.get('annotations', []), list):
                    continue
                for annotation in part.get('annotations', []):
                    if not isinstance(annotation, dict):
                        continue
                    if annotation.get('type') != 'url_citation':
                        continue
                    url = annotation.get('url', '')
                    if valid_source_url(url) and url not in self.sources:
                        self.sources.append(url)

    def result(self, content, model):
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Empty model response')
        content = re.sub(r'(?:cite|navlist|image_group)[\s\S]*?', '', content).strip()
        if not content:
            raise ValueError('Empty model response')
        missing = [url for url in self.sources[:8] if url not in content]
        if missing:
            content += '\n\n출처:\n' + '\n'.join(f'- <{url}>' for url in missing)
        if self.search_ids and not self.sources:
            content = '※ 웹 검색은 실행됐지만 인용 가능한 출처를 확보하지 못했어요.\n' + content
        return {'text': content, 'model': model, 'search_count': len(self.search_ids),
                'sources': self.sources[:8], 'version': 'subscription-search-v3'}


class SubscriptionAnswers:
    def __init__(self, base_url, api_key=None, evidence_callback=None):
        if not base_url:
            raise ValueError('Subscription answers require HINDSIGHT_URL')
        self.url = base_url.rstrip('/') + '/ext/answers'
        self.api_key = api_key
        self.evidence_callback = evidence_callback

    async def answer(self, query, facts):
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=190)) as session:
            async with session.post(self.url, json={'query': query, 'facts': facts},
                                    headers=headers) as response:
                if response.status != 200:
                    raise RuntimeError('Subscription answer service unavailable')
                chunks = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    chunks.extend(chunk)
                    if len(chunks) > 262144:
                        raise ValueError('Subscription response too large')
                data = validate_answer(json.loads(chunks))
        if self.evidence_callback is not None:
            try:
                self.evidence_callback(data['search_count'], len(data['sources']))
            except Exception:
                pass
        return data['text']

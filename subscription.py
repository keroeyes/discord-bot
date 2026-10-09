"""Private subscription answer protocol; contains no credentials or model tools."""
import json
import re
from urllib.parse import urlsplit
import aiohttp


class SearchEvidence:
    def __init__(self):
        self.search_ids = set()
        self.sources = []

    def observe(self, event):
        items = []
        if event.get('type') == 'response.output_item.done':
            items = [event.get('item', {})]
        elif event.get('type') == 'response.completed':
            items = event.get('response', {}).get('output', [])
        for item in items:
            if item.get('type') == 'web_search_call' and item.get('status') == 'completed':
                self.search_ids.add(item.get('id', 'search'))
            for part in item.get('content', []):
                for annotation in part.get('annotations', []):
                    if annotation.get('type') != 'url_citation':
                        continue
                    url = annotation.get('url', '')
                    if (isinstance(url, str) and len(url) < 2000
                            and urlsplit(url).scheme in {'http', 'https'}
                            and urlsplit(url).netloc and not re.search(r'[\s<>]', url)
                            and url not in self.sources):
                        self.sources.append(url)

    def result(self, content, model):
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Empty model response')
        content = re.sub(r'(?:cite|navlist|image_group)[\s\S]*?', '', content).strip()
        missing = [url for url in self.sources[:8] if url not in content]
        if missing:
            content += '\n\n출처:\n' + '\n'.join(f'- <{url}>' for url in missing)
        if self.search_ids and not self.sources:
            content = '※ 웹 검색은 실행됐지만 인용 가능한 출처를 확보하지 못했어요.\n' + content
        return {'text': content, 'model': model, 'search_count': len(self.search_ids),
                'sources': self.sources[:8], 'version': 'subscription-search-v3'}


class SubscriptionAnswers:
    def __init__(self, base_url, api_key=None):
        if not base_url:
            raise ValueError('Subscription answers require HINDSIGHT_URL')
        self.url = base_url.rstrip('/') + '/ext/answers'
        self.api_key = api_key

    async def answer(self, query, facts):
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=190)) as session:
            async with session.post(self.url, json={'query': query, 'facts': facts},
                                    headers=headers) as response:
                if response.status != 200:
                    raise RuntimeError('Subscription answer service unavailable')
                data = await response.json()
        if (not isinstance(data, dict) or data.get('version') != 'subscription-search-v3'
                or not isinstance(data.get('text'), str) or not data['text'].strip()
                or not isinstance(data.get('search_count'), int)
                or not isinstance(data.get('sources'), list)):
            raise ValueError('Invalid subscription response')
        return data['text']

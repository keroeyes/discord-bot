import gzip
import unittest
from unittest.mock import patch
from answer_evals.official import INDEX, parse_snapshot, evaluate_latest, fetch_snapshot

HTML = '''<a href="/downloads/release/python-3148/">Python 3.14.8</a>
<a href="/downloads/release/python-3150/">Python 3.15.0rc1</a>
<a href="/downloads/release/python-31316/">Python 3.13.16</a>'''


class OfficialContent(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.before = parse_snapshot(HTML)
        self.text = '최신 정식 안정 버전은 Python 3.14.8입니다. ' + self.before.url

    def score(self, text=None, sources=None, count=1, after=None):
        return evaluate_latest(self.text if text is None else text,
                               [self.before.url] if sources is None else sources, count,
                               self.before, self.before if after is None else after)

    def test_official_oracle_excludes_prereleases_and_uses_numeric_order(self):
        self.assertEqual(self.before.version, '3.14.8')
        page = HTML + '<a href="/downloads/release/python-31410/">Python 3.14.10</a>'
        self.assertEqual(parse_snapshot(page).version, '3.14.10')

    def test_oracle_rejects_changed_markup_and_untrusted_links(self):
        for html in ('', '<a href="https://evil.invalid">Python 9.9.9</a>',
                     '<a href="/downloads/release/python-3148/">Python 3.15.0</a>'):
            with self.assertRaises(ValueError):
                parse_snapshot(html)

    def test_matching_live_content_passes_only_with_search_and_source(self):
        self.assertTrue(all(self.score().values()))
        self.assertFalse(self.score(count=0)['search_evidence'])
        self.assertFalse(self.score(count=True)['search_evidence'])
        self.assertFalse(self.score(sources=[])['source_alignment'])
        self.assertFalse(self.score(sources=['https://evil.invalid'])['source_alignment'])
        self.assertFalse(self.score(text=self.text + ' https://evil.invalid')['source_alignment'])

    def test_stale_negated_contradictory_or_question_only_answers_fail(self):
        for text in ('최신 버전은 3.14.7입니다.', '최신 버전은 3.14.8이 아닙니다.',
                     '최신 버전은 3.14.8인가요?',
                     '최신 버전은 3.14.8입니다. 실제 최신 버전은 3.14.7입니다.',
                     '최신 버전은 3.14.8입니다. 3.14.8은 틀렸습니다.'):
            self.assertFalse(self.score(text=text)['accuracy'])

    def test_source_change_during_model_call_fails_closed(self):
        after = parse_snapshot(HTML + '<a href="/downloads/release/python-3149/">Python 3.14.9</a>')
        self.assertFalse(self.score(after=after)['source_stable'])

    def test_empty_and_url_only_answers_fail(self):
        self.assertFalse(any(self.score(text='').values()))
        self.assertFalse(self.score(text=self.before.url)['relevance'])

    def test_redirect_is_blocked_before_following_destination(self):
        from urllib.request import Request
        from answer_evals.official import NoRedirect
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(Request(INDEX), None, 302,
                                                   'Found', {}, 'https://evil.invalid'))

    def test_fetch_bounded_compressed_source_and_redirect_rejection(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return INDEX
            def read(self, limit): return gzip.compress(HTML.encode())[:limit]
        with patch('answer_evals.official.urlopen', return_value=Response()) as fetch:
            self.assertEqual(fetch_snapshot().version, '3.14.8')
            self.assertEqual(fetch.call_args.args[0].full_url, INDEX)
        response = Response()
        response.geturl = lambda: 'https://evil.invalid'
        with patch('answer_evals.official.urlopen', return_value=response), self.assertRaises(ValueError):
            fetch_snapshot()
        response = Response()
        response.read = lambda limit: gzip.compress(b'a' * 1_000_002)
        with patch('answer_evals.official.urlopen', return_value=response), self.assertRaises(ValueError):
            fetch_snapshot()

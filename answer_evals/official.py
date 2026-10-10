"""Bounded official Python release oracle for opt-in live evaluation.
Never fetch model-supplied URLs. No imports from bot, Langfuse or judge SDKs.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import zlib
from urllib.request import Request, HTTPRedirectHandler, build_opener
from answer_evals.content import affirmative_claims, clean_prose

INDEX = 'https://www.python.org/downloads/'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Refuse before any request to a redirect destination, not after fetching it.
        return None


urlopen = build_opener(NoRedirect()).open


@dataclass(frozen=True)
class Snapshot:
    version: str
    url: str
    checked_at: str


class ReleaseLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.label = ''
        self.releases = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.label = ''

    def handle_data(self, text):
        if self.href:
            self.label += text

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            match = re.fullmatch(r'Python (3\.\d+\.\d+)', self.label.strip())
            if match and re.fullmatch(r'/downloads/release/python-\d+/', self.href):
                version = match[1]
                if self.href == '/downloads/release/python-' + version.replace('.', '') + '/':
                    self.releases.append((version, 'https://www.python.org' + self.href))
            self.href = None
            self.label = ''


def parse_snapshot(html):
    parser = ReleaseLinks()
    parser.feed(html)
    if not parser.releases:
        raise ValueError('Official source contract changed')
    version, url = max(parser.releases, key=lambda pair: tuple(map(int, pair[0].split('.'))))
    return Snapshot(version, url, datetime.now(timezone.utc).isoformat())


def fetch_snapshot():
    # Redirects fail closed; index fetch is the only permitted public request.
    with urlopen(Request(INDEX, headers={'User-Agent': 'discord-bot-content-eval/1', 'Cache-Control': 'no-cache',
                                   'Accept-Encoding': 'identity'}), timeout=20) as response:
        if response.geturl() != INDEX or response.status != 200:
            raise ValueError('Unexpected official response')
        body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError('Official response too large')
    if body.startswith(b'\x1f\x8b'):
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = decoder.decompress(body, 1_000_001)
        if len(body) > 1_000_000 or not decoder.eof:
            raise ValueError('Compressed official response too large')
    return parse_snapshot(body.decode('utf-8'))


def evaluate_latest(text, sources, search_count, before, after):
    """Check a narrow current-release claim, never general web factuality."""
    if not isinstance(text, str) or not text.strip():
        return dict(accuracy=False, relevance=False, source_alignment=False,
                    search_evidence=False, source_stable=False)
    prose = clean_prose(text)
    versions = set(re.findall(r'(?<![\d.])3\.\d+\.\d+(?![\d.])', prose))
    fact = re.escape(before.version)
    affirmative = (rf'(?:최신|정식|안정|stable|latest)[^\n!?]{{0,60}}{fact}'
                   rf'\s*(?:입니다|이다|예요|이에요|(?:이|가)\s*맞)',)
    accurate = versions == {before.version} and affirmative_claims(prose, affirmative, (fact,))
    urls = set(re.findall(r'https?://[^\s<>\)]+', text))
    allowed = {INDEX, before.url}
    aligned = (bool(sources) and set(sources).issubset(allowed)
               and bool(urls) and urls.issubset(allowed) and set(sources).issubset(urls)
               and accurate)
    return dict(accuracy=bool(accurate), relevance=bool(re.search(fact, prose)),
                source_alignment=bool(aligned),
                search_evidence=type(search_count) is int and search_count > 0,
                source_stable=(before.version, before.url) == (after.version, after.url))

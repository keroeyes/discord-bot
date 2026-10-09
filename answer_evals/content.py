"""Bounded deterministic rubrics, not a general factual-truth classifier.

Only repository-owned synthetic cases are accepted. Never load user transcripts.
Source support is checked against curated claims, not URL presence alone.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Case:
    id: str
    query: str
    facts: tuple[str, ...]
    required: tuple[str, ...]
    forbidden: tuple[str, ...] = ()
    source: str | None = None
    evidence: str = ''
    evidence_required: tuple[str, ...] = ()
    search_required: bool = False


CASES = (
    Case('knowledge', '물의 화학식은 무엇인가요?', (), (r'(?<![A-Za-z0-9])H2O(?![A-Za-z0-9])|H₂O',),
         (r'(?<![A-Za-z0-9])CO2(?![A-Za-z0-9])|CO₂',)),
    Case('current', '합성 공지의 2026-10-09 기준 큐브앱 최신 버전과 발표일은? '
         '제공된 공지: https://example.invalid/cube/releases/2026-10-09 '
         '큐브앱 2.4, 2026-10-09 발표. 실제 서비스가 아닌 평가용 공지입니다.', (),
         (r'2\.4', r'2026[-년 ./]+10[-월 ./]+0?9'), (r'2\.3',),
         source='https://example.invalid/cube/releases/2026-10-09',
         evidence='합성 공지: 큐브앱 2.4, 2026-10-09 발표.',
         evidence_required=(r'2\.4', r'2026-10-09'), search_required=True),
    Case('memory', '내 합성 세차 버킷 용량은? 현재 질문 기준 20L로 바꿨어요.',
         ('합성 기록: 예전 버킷은 18L.',), (r'20\s*(?:L|리터)',),
         (r'18\s*(?:L|리터)(?:입니다|예요|이에요|를 사용)',)),
    Case('missing_memory', '내 합성 차량 번호는?', (),
         (r'알 수 없|모르|기억.*없|정보.*없|확인.*(?:못|불가|없)',),
         (r'\d{2,3}[가-힣]\s?\d{4}',)),
    Case('search_failure', '합성 서비스 검색이 실패했습니다. 지금 큐브앱 가격은?', (),
         (r'검색.*실패|확인.*(?:못|불가|없)|알 수 없',),
         (r'\d[\d,]*\s*원', r'검색.*(?:확인했|성공)', r'무료입니다')),
)


def evaluate(case, text, sources=(), search_count=None):
    """Return dimension booleans only. No answer, query or evidence is logged."""
    if case not in CASES:
        raise ValueError('Only fixed synthetic cases are supported')
    if not isinstance(text, str) or not text.strip():
        return dict(accuracy=False, relevance=False, source_alignment=False,
                    search_evidence=False)
    accuracy = (all(re.search(pattern, text, re.I) for pattern in case.required)
                and not any(re.search(pattern, text, re.I) for pattern in case.forbidden))
    # Required task-specific facts must occur in answer prose, not only a URL.
    prose = re.sub(r'https?://\S+', '', text)
    relevance = all(re.search(pattern, prose, re.I) for pattern in case.required)
    alignment = not sources if case.id == 'search_failure' else True
    if case.source:
        urls = re.findall(r'https?://[^\s<>\)]+', text)
        alignment = (case.source in sources and case.source in urls
                     and set(sources) == {case.source}
                     and set(urls) == {case.source}
                     and all(re.search(p, case.evidence) for p in case.evidence_required)
                     and accuracy)
    search = (type(search_count) is int and search_count > 0) if case.search_required else True
    return dict(accuracy=bool(accuracy), relevance=bool(relevance),
                source_alignment=bool(alignment), search_evidence=bool(search))

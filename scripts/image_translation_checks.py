"""Synthetic translation probes, not a general semantic quality evaluator."""
import re

CASES = [
    ('벚꽃이 핀 나무들이 늘어선 도로 위의 흰색 자동차, 실사 사진',
     [('white',), ('car',), ('road',), ('cherry',), ('blossom', 'blossoms'),
      ('lined', 'rows', 'lining'), ('photograph', 'photo')]),
    ('빨간 우산을 든 고양이 두 마리, 수채화',
     [('red',), ('umbrella', 'umbrellas'), ('cat', 'cats'), ('two', '2'),
      ('watercolor', 'watercolour')]),
    ('검은 자동차 뒤에 파란 자전거, 밤, 애니메이션 그림',
     [('black',), ('car',), ('blue',), ('bicycle', 'bike'), ('night',),
      ('anime', 'animation', 'animated')]),
]


def issues(index, output):
    """Check selected concepts and the direction of the fixed spatial probe."""
    normalized = ' '.join(output.lower().split())
    missing = [group[0] for group in CASES[index][1]
               if not any(re.search(r'\b' + re.escape(term) + r'\b', normalized)
                          for term in group)]
    if index == 2:
        car = r'(?:a |the )?black car'
        bike = r'(?:a |the )?blue (?:bicycle|bike)'
        patterns = [bike + r' (?:is |located |positioned )?(?:behind|following) ' + car,
                    car + r' (?:is )?followed by ' + bike,
                    car + r' (?:is |located |positioned )?(?:in front of|ahead of) ' + bike]
        if not any(re.search(pattern, normalized) for pattern in patterns):
            missing.append('spatial direction (blue bicycle behind black car)')
    return missing

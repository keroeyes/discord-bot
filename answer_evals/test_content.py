import unittest
from unittest.mock import patch
from answer_evals.content import CASES, evaluate


class ContentRegression(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_curated_positive_answers(self):
        answers = ('물의 화학식은 H2O입니다.',
                   '큐브앱 2.4는 2026-10-09 발표되었습니다. '
                   'https://example.invalid/cube/releases/2026-10-09',
                   '현재 버킷은 20L입니다. 예전 기록은 18L였습니다.',
                   '차량 번호 정보가 없어 알 수 없어요.',
                   '검색 실패로 현재 가격을 확인하지 못했습니다.')
        for case, answer in zip(CASES, answers):
            with self.subTest(case=case.id):
                sources = [case.source] if case.source else []
                self.assertTrue(all(evaluate(case, answer, sources, search_count=1).values()))

    def test_wrong_irrelevant_stale_and_fabricated_answers_fail(self):
        answers = ('물의 화학식은 CO2입니다.',
                   '최신 버전은 2.3입니다. 발표일은 2026-10-08입니다.',
                   '18L를 사용합니다.', '차량 번호는 123가4567입니다.',
                   '검색으로 확인했습니다. 현재 가격은 12,000원입니다.')
        for case, answer in zip(CASES, answers):
            with self.subTest(case=case.id):
                self.assertFalse(evaluate(case, answer)['accuracy'])
        self.assertFalse(evaluate(CASES[0], '세차 버킷은 20L입니다.')['relevance'])

    def test_url_presence_does_not_prove_support(self):
        case = CASES[1]
        url = case.source
        for text, sources in [
            ('2.3 2026-10-09 ' + url, [url]),
            ('2.4 2026-10-09 https://example.invalid/wrong', [url]),
            ('2.4 2026-10-09 ' + url, []),
            ('2.4 2026-10-09 ' + url, [url, 'https://example.invalid/wrong']),
            ('2.4 2026-10-09 ' + url + ' https://example.invalid/wrong', [url]),
        ]:
            with self.subTest(text=text):
                self.assertFalse(evaluate(case, text, sources)['source_alignment'])

    def test_failure_cannot_claim_price_or_attach_evidence(self):
        case = CASES[-1]
        self.assertFalse(evaluate(case, '확인 불가. 100원입니다.')['accuracy'])
        self.assertFalse(evaluate(case, '확인 불가', ['https://example.invalid'])['source_alignment'])

    def test_empty_and_non_text_fail_closed(self):
        for text in ('', ' ', None, {}):
            self.assertFalse(any(evaluate(CASES[0], text).values()))

    def test_no_arbitrary_case_or_user_data(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):
            evaluate(replace(CASES[0], query='untrusted input'), 'H2O')

    def test_search_completion_is_required_but_insufficient(self):
        case = CASES[1]
        answer = '2.4 2026-10-09 ' + case.source
        for count in (None, 0, -1, True, '1'):
            self.assertFalse(evaluate(case, answer, [case.source], count)['search_evidence'])
        result = evaluate(case, '2.3 2026-10-08 ' + case.source, [case.source], 3)
        self.assertTrue(result['search_evidence'])
        self.assertFalse(result['accuracy'])

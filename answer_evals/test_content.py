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

    def test_affirmative_words_do_not_override_negation_or_contradiction(self):
        samples = (
            (0, '물의 화학식은 H2O가 아닙니다.'),
            (0, '물의 화학식은 H2O입니다. H2O라는 답은 틀렸습니다.'),
            (0, '물의 화학식은 H2O인가요?'),
            (0, 'H2O라고 하지 않습니다.'),
            (0, 'H2O is not the answer.'),
            (1, '최신 버전은 2.4가 아닙니다. 발표일은 2026-10-09입니다.'),
            (1, '큐브앱 2.4는 2026-10-09 발표되었습니다. 최신 버전은 2.5입니다.'),
            (1, '큐브앱 2.4는 2026-10-09 발표되었습니다. 발표일은 2026-10-08입니다.'),
            (2, '20L는 아닙니다.'),
            (2, '현재 버킷은 20L입니다. 실제로는 18L예요.'),
            (2, '20L라는 질문이지만 현재 버킷은 18L 입니다.'),
            (2, '현재 버킷은 20L입니다. 20L라는 기록은 오류입니다.'),
        )
        for index, text in samples:
            with self.subTest(case=CASES[index].id, sample=index):
                self.assertFalse(evaluate(CASES[index], text)['accuracy'])

    def test_formatting_unicode_and_supported_short_affirmations(self):
        for text in ('물의 화학식은 **H₂O**입니다.', 'H2O입니다.', '물의 화학식은 `H2O`예요.'):
            self.assertTrue(evaluate(CASES[0], text)['accuracy'])

    def test_uncertainty_cannot_be_negated_into_a_success_claim(self):
        for index, text in ((3, '알 수 없다는 말은 틀렸습니다.'),
                            (4, '검색은 실패하지 않았습니다.'),
                            (4, '확인 불가라는 말은 거짓입니다.')):
            self.assertFalse(evaluate(CASES[index], text)['accuracy'])

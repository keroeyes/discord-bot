"""Run synthetic answers through actual bot handling and assess delivered content."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from answer_evals.content import CASES, evaluate
import test_bot as bot_fixtures


class DeliveredContent(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await bot_fixtures.BotTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await bot_fixtures.BotTests.asyncTearDown(self)

    async def test_general_memory_and_failure_content_survive_delivery(self):
        samples = (
            (CASES[0], '물의 화학식은 H2O입니다.'),
            (CASES[2], '현재 버킷은 20L입니다. 예전에는 18L였습니다.'),
            (CASES[3], '차량 번호 정보가 없어 알 수 없습니다.'),
            (CASES[4], '검색 실패로 현재 가격을 확인하지 못했습니다.'),
        )
        with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
            for case, answer in samples:
                with self.subTest(case=case.id):
                    self.memory.recall.return_value = list(case.facts)
                    self.ai.chat.completions.create.return_value = NS(
                        choices=[NS(message=NS(content=answer))])
                    msg = bot_fixtures.message('!질문 ' + case.query)
                    await self.bot.on_message(msg)
                    delivered = '\n'.join(call.args[0] for call in msg.channel.send.call_args_list)
                    self.assertTrue(all(evaluate(case, delivered).values()))
                    msg.channel.send.reset_mock()
            self.memory.save.assert_not_awaited()

    async def test_delivery_success_does_not_make_wrong_answer_correct(self):
        self.memory.recall.return_value = []
        self.ai.chat.completions.create.return_value = NS(
            choices=[NS(message=NS(content='물의 화학식은 CO2입니다.'))])
        msg = bot_fixtures.message('!질문 ' + CASES[0].query)
        await self.bot.on_message(msg)
        msg.channel.send.assert_awaited()
        self.assertFalse(evaluate(CASES[0], msg.channel.send.call_args.args[0])['accuracy'])

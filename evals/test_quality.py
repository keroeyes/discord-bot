"""Offline DeepEval route regression tests. No model or production data is used."""
import os
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
os.environ["DEEPEVAL_DISABLE_PROGRESS_BAR"] = "1"

from unittest.mock import patch
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, ToolCall
from test_observability import BotTraceCase
from test_bot import message


class NoJudge(DeepEvalBaseLLM):
    def __init__(self):
        pass

    def load_model(self):
        return None

    def generate(self, *args, **kwargs):
        raise AssertionError("Offline evaluation must never call an LLM")

    async def a_generate(self, *args, **kwargs):
        raise AssertionError("Offline evaluation must never call an LLM")

    def get_model_name(self):
        return "offline-no-judge"


def route_score(trace, expected):
    metric = ToolCorrectnessMetric(model=NoJudge(), should_exact_match=True)
    case = LLMTestCase(
        input="Synthetic route regression",
        actual_output=trace["status"],
        tools_called=[ToolCall(name=step["name"]) for step in trace["stages"]],
        expected_tools=[ToolCall(name=name) for name in expected],
    )
    # Fail the test if this evaluation tries to use a network service.
    with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
        metric.measure(case)
    return metric.score


class DeepEvalRoutes(BotTraceCase):
    async def test_general_question_uses_recall_answer_and_delivery(self):
        trace = await self.capture(message('!질문 synthetic local recommendation'))
        self.assertEqual(route_score(trace, ['memory_recall', 'answer_generation', 'delivery']), 1)
        self.memory.reflect.assert_not_awaited()
        self.memory.save.assert_not_awaited()

    async def test_explicit_memory_does_not_generate_answer(self):
        trace = await self.capture(message('!기억 synthetic fact'))
        self.assertEqual(route_score(trace, ['memory_save', 'delivery']), 1)
        self.bot.subscription.answer.assert_not_awaited()

    async def test_memory_search_does_not_generate_answer(self):
        trace = await self.capture(message('!기억검색 synthetic query'))
        self.assertEqual(route_score(trace, ['memory_recall', 'delivery']), 1)
        self.bot.subscription.answer.assert_not_awaited()

    async def test_evaluator_rejects_missing_or_extra_steps(self):
        trace = await self.capture(message('!질문 synthetic question'))
        self.assertEqual(route_score(trace, ['answer_generation', 'delivery']), 0)
        self.assertEqual(route_score(trace, ['memory_recall', 'answer_generation',
                                             'memory_save', 'delivery']), 0)

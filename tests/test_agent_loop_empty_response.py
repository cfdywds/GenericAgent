import unittest
from types import SimpleNamespace

from agent_loop import BaseHandler, StepOutcome, agent_runner_loop, exhaust


class FakeResponse:
    def __init__(self, tool_calls=None):
        self.content = ""
        self.tool_calls = tool_calls or []


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.last_tools = ""

    def chat(self, **_kwargs):
        response = self.responses.pop(0)

        def stream():
            if False:
                yield None
            return response

        return stream()


class EmptyResponseHandler(BaseHandler):
    def __init__(self):
        self.parent = SimpleNamespace(task_dir=None)
        self._done_hooks = []
        self.empty_counts = []

    def do_work(self, _args, _response):
        if False:
            yield None
        return StepOutcome({}, next_prompt="continue")

    def do_no_tool(self, _args, _response):
        if False:
            yield None
        self.empty_counts.append(getattr(self, "_empty_ct", 0))
        self._empty_ct = getattr(self, "_empty_ct", 0) + 1
        if self._empty_ct >= 3:
            return StepOutcome(
                {"reason": "EMPTY_RESPONSE_RETRY_EXHAUSTED", "attempts": self._empty_ct},
                should_exit=True,
            )
        return StepOutcome({}, next_prompt="retry")


def work_call():
    return SimpleNamespace(function=SimpleNamespace(name="work", arguments="{}"), id="work-1")


class AgentLoopEmptyResponseTests(unittest.TestCase):
    def run_loop(self, responses, max_turns=8):
        handler = EmptyResponseHandler()
        result = exhaust(agent_runner_loop(
            FakeClient(responses), "system", "user", handler, [],
            max_turns=max_turns, verbose=False,
        ))
        return handler, result

    def test_tool_calls_reset_empty_response_counter(self):
        handler, result = self.run_loop([
            FakeResponse(),
            FakeResponse([work_call()]),
            FakeResponse(),
            FakeResponse([work_call()]),
            FakeResponse(),
        ], max_turns=5)

        self.assertEqual(handler.empty_counts, [0, 0, 0])
        self.assertEqual(result, {"result": "MAX_TURNS_EXCEEDED"})

    def test_three_consecutive_empty_responses_exit_with_reason(self):
        handler, result = self.run_loop([FakeResponse(), FakeResponse(), FakeResponse()])

        self.assertEqual(handler.empty_counts, [0, 1, 2])
        self.assertEqual(result, {
            "result": "EXITED",
            "data": {"reason": "EMPTY_RESPONSE_RETRY_EXHAUSTED", "attempts": 3},
        })


if __name__ == "__main__":
    unittest.main()

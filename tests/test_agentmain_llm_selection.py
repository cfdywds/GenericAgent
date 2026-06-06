import types
import unittest
from unittest.mock import patch

import agentmain


def _client(name, history=None):
    backend = types.SimpleNamespace(name=name, model=name, history=history or [])
    return types.SimpleNamespace(backend=backend, last_tools="", name=name)


class GenericAgentLlmSelectionTests(unittest.TestCase):
    def test_load_llm_sessions_skips_failed_mixin_entries(self):
        agent = agentmain.GenericAgent.__new__(agentmain.GenericAgent)
        agent.llm_no = 0

        good = _client("good")
        mykeys = {
            "mixin_config": {"llm_nos": ["missing"]},
            "oai_config": {"name": "good"},
        }

        with patch.object(agentmain, "reload_mykeys", return_value=(mykeys, True)), \
             patch.object(agentmain, "resolve_client", return_value=good), \
             patch.object(agentmain, "MixinSession", side_effect=ValueError("bad mixin")), \
             patch("builtins.print"):
            agent.load_llm_sessions()

        self.assertEqual(agent.llmclients, [good])
        self.assertIs(agent.llmclient, good)

    def test_next_llm_switches_from_stale_bad_mixin_to_valid_client(self):
        agent = agentmain.GenericAgent.__new__(agentmain.GenericAgent)
        agent.llm_no = 0
        agent.llmclients = [{"mixin_cfg": {"llm_nos": ["missing"]}}, _client("good")]
        agent.llmclient = agent.llmclients[0]

        with patch.object(agentmain.GenericAgent, "load_llm_sessions", return_value=None), \
             patch.object(agentmain, "load_tool_schema", return_value=None):
            agent.next_llm(1)

        self.assertEqual(agent.llm_no, 1)
        self.assertIs(agent.llmclient, agent.llmclients[1])


if __name__ == "__main__":
    unittest.main()

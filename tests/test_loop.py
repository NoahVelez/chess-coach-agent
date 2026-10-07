import io
import json
import unittest
from types import SimpleNamespace

import httpx
import openai

from agent import loop
from agent.facts_store import FactsStore, GameFacts
from tests.fixtures import SAMPLE_GAMES


class ScriptedClient:
    """Fake OpenAI client: returns scripted replies in order (or raises Exception instances)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(dict(kwargs, messages=list(kwargs["messages"])))
        reply = self.replies.pop(0) if self.replies else self.replies_default()
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    def replies_default(self):
        return tool_reply("get_player_profile")


def tool_reply(name, args=None, question="q", **extra):
    body = {
        "type": "tool",
        "name": name,
        "args": args or {},
        "open_question": question,
        "why_this_next": "w",
        "would_change_my_mind_if": "c",
        "decision_so_far": "d",
    }
    body.update(extra)
    return json.dumps(body)


def final_reply(report="# Report\nDo X first."):
    return json.dumps({"type": "final", "decision_so_far": "X", "report": report})


def run(replies, **kwargs):
    kwargs.setdefault("audit_rounds", 0)
    store = FactsStore([GameFacts(i, r) for i, r in enumerate(SAMPLE_GAMES)])
    client = ScriptedClient(replies)
    log = io.StringIO()
    result = loop.run_coaching_agent(store, "tester", client=client, model="m", log=log, **kwargs)
    return result, client, log.getvalue()


class LoopTests(unittest.TestCase):
    def test_tool_then_final_logs_reasoning_and_feeds_result_back(self):
        result, client, log = run(
            [tool_reply("opening_sequences", {"color": "white"}, question="what does white play?"), final_reply()]
        )
        self.assertEqual((result.status, result.turns_used), ("final", 2))
        self.assertEqual(result.report, "# Report\nDo X first.")
        self.assertIn("open_question:  what does white play?", log)
        self.assertIn("decision_so_far: d", log)
        last_user = client.requests[-1]["messages"][-1]
        self.assertTrue(last_user["content"].startswith("TOOL RESULT (opening_sequences)"))
        self.assertEqual(client.requests[0]["response_format"], {"type": "json_object"})

    def test_first_user_message_has_only_username_volume_and_goal(self):
        _, client, _ = run([final_reply()])
        first = client.requests[0]["messages"][1]["content"]
        self.assertIn("tester", first)
        self.assertIn("6 recent", first)
        self.assertIn("4 as White", first)
        self.assertNotIn("Start by", first)

    def test_malformed_replies_do_not_consume_turns(self):
        result, client, _ = run(["not json", tool_reply("get_player_profile"), "```json\n" + final_reply() + "\n```"])
        self.assertEqual(result.status, "final")
        self.assertEqual(result.turns_used, 2)
        self.assertEqual(len(client.requests), 3)

    def test_tool_turn_without_reasoning_fields_is_rejected_by_shape(self):
        bare = json.dumps({"type": "tool", "name": "get_player_profile", "args": {}})
        result, client, _ = run([bare, tool_reply("get_player_profile"), final_reply()])
        self.assertEqual(result.turns_used, 2)
        rejection = client.requests[1]["messages"][-1]["content"]
        self.assertIn("open_question", rejection)

    def test_unknown_tool_and_bad_args_come_back_as_error_facts(self):
        result, client, _ = run(
            [tool_reply("recommend_opening"), tool_reply("get_game_moves", {"game_index": 99}), final_reply()]
        )
        self.assertEqual(result.status, "final")
        self.assertIn('"error"', client.requests[1]["messages"][-1]["content"])
        self.assertIn("out of range", client.requests[2]["messages"][-1]["content"])

    def test_cap_forces_a_final_report_and_blocks_tools(self):
        result, client, log = run(
            [tool_reply("get_player_profile"), tool_reply("get_player_profile"), tool_reply("get_player_profile"), final_reply("# Best effort")],
            max_iterations=2,
        )
        self.assertEqual(result.status, "cap_reached")
        self.assertEqual(result.report, "# Best effort")
        self.assertEqual(result.turns_used, 3)
        self.assertEqual(len(result.trail), 3)
        self.assertIn("iteration cap reached", log)
        self.assertIn("turn cap has been reached", client.requests[2]["messages"][-1]["content"])
        self.assertIn("no tool calls are allowed", client.requests[3]["messages"][-1]["content"])

    def test_unparseable_output_still_returns_a_report_with_trail(self):
        replies = [tool_reply("get_player_profile", question="first question")] + ["garbage"] * 10
        result, _, _ = run(replies)
        self.assertEqual(result.status, "unparseable")
        self.assertIn("first question", result.report)
        self.assertIn("never parsed", result.report)

    def test_rejected_optional_parameters_are_dropped(self):
        request = httpx.Request("POST", "http://test")
        err = openai.BadRequestError(
            "Unsupported value: 'temperature' does not support 0.4",
            response=httpx.Response(400, request=request),
            body=None,
        )
        result, client, _ = run([err, final_reply()])
        self.assertEqual(result.status, "final")
        self.assertIn("temperature", client.requests[0])
        self.assertNotIn("temperature", client.requests[1])
        self.assertIn("response_format", client.requests[1])

    def test_model_errors_still_produce_a_report(self):
        err = openai.APIConnectionError(request=httpx.Request("POST", "http://test"))
        result, _, _ = run([tool_reply("get_player_profile"), err])
        self.assertEqual(result.status, "model_error")
        self.assertIn("model call failed", result.report)

    def test_model_name_from_environment(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"OPENAI_MODEL": "gpt-x"}):
            self.assertEqual(loop.get_model(), "gpt-x")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(loop.get_model(), loop.DEFAULT_MODEL)


class BudgetLineTests(unittest.TestCase):
    def test_tool_results_carry_plain_run_status_facts(self):
        _, client, _ = run([tool_reply("get_player_profile"), final_reply()])
        message = client.requests[1]["messages"][-1]["content"]
        self.assertIn("RUN STATUS: turns used 1 of 20; engine tool calls so far 0; games with engine analysis 0.", message)

    def test_status_line_has_no_instructions(self):
        line = loop._budget_line(FactsStore([]), 3, 20, 2).lower()
        for word in ("should", "must", "try", "consider", "use "):
            self.assertNotIn(word, line)

    def test_engine_calls_are_counted(self):
        _, client, _ = run(
            [tool_reply("evaluate_position", {"moves": ["e4"]}), tool_reply("get_player_profile"), final_reply()]
        )
        self.assertIn("engine tool calls so far 1", client.requests[2]["messages"][-1]["content"])


class AuditTests(unittest.TestCase):
    def test_audit_message_follows_first_final_and_revision_is_used(self):
        result, client, log = run([final_reply("# Draft"), final_reply("# Revised")], audit_rounds=1)
        self.assertEqual((result.report, result.audit, result.status), ("# Revised", "revised", "final"))
        self.assertEqual(result.turns_used, 2)
        self.assertEqual(client.requests[1]["messages"][-1]["content"], loop.AUDIT_MESSAGE)
        self.assertIn("asking the model to audit", log)

    def test_unchanged_draft_is_confirmed(self):
        result, _, _ = run([final_reply("# Same"), final_reply("# Same")], audit_rounds=1)
        self.assertEqual((result.report, result.audit), ("# Same", "confirmed"))

    def test_audit_may_call_a_tool_before_the_final(self):
        result, client, _ = run(
            [final_reply("# Draft"), tool_reply("get_player_profile"), final_reply("# Checked")], audit_rounds=1
        )
        self.assertEqual((result.report, result.audit, result.turns_used), ("# Checked", "revised", 3))

    def test_only_one_audit_round(self):
        result, client, _ = run([final_reply("# A"), final_reply("# B")], audit_rounds=1)
        self.assertEqual(len(client.requests), 2)

    def test_unparseable_audit_keeps_first_draft(self):
        result, _, _ = run([final_reply("# Draft")] + ["garbage"] * 6, audit_rounds=1)
        self.assertEqual((result.report, result.status, result.audit), ("# Draft", "final", "confirmed"))

    def test_model_error_during_audit_keeps_first_draft(self):
        err = openai.APIConnectionError(request=httpx.Request("POST", "http://test"))
        result, _, _ = run([final_reply("# Draft"), err], audit_rounds=1)
        self.assertEqual((result.report, result.status), ("# Draft", "final"))

    def test_final_on_the_last_turn_is_not_audited(self):
        result, client, _ = run([tool_reply("get_player_profile"), final_reply("# Late")], audit_rounds=1, max_iterations=2)
        self.assertEqual((result.report, result.audit, result.status), ("# Late", "not_run", "final"))
        self.assertEqual(len(client.requests), 2)

    def test_audit_message_has_no_chess_question_list(self):
        text = loop.AUDIT_MESSAGE.lower()
        for phrase in ("opening", "castle", "as white", "as black", "alternative"):
            self.assertNotIn(phrase, text)

    def test_conversation_is_returned_for_transcripts(self):
        result, _, _ = run([final_reply()])
        self.assertEqual(result.conversation[0]["role"], "system")
        self.assertEqual(result.conversation[-1]["role"], "assistant")


class PromptTests(unittest.TestCase):
    def test_system_prompt_has_no_question_checklist(self):
        text = loop.SYSTEM_PROMPT.lower()
        for phrase in ("step 1", "first, ", "start by", "standard openings", "what are the user"):
            self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()

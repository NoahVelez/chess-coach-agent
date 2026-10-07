import datetime as dt
import tempfile
import unittest
from pathlib import Path

from agent.facts_store import FactsStore, GameFacts
from agent.loop import AgentRun
from main import build_header, write_report, write_transcript
from tests.fixtures import SAMPLE_GAMES

NOW = dt.datetime(2026, 10, 4, 15, 30, 5)


def make_store():
    return FactsStore([GameFacts(i, r) for i, r in enumerate(SAMPLE_GAMES)])


def make_run(status="final", report="## My own heading\nDo X."):
    return AgentRun(report=report, status=status, turns_used=7, model="m-test")


class ReportTests(unittest.TestCase):
    def test_writes_exactly_one_file_with_header_and_model_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_report("Some.User", make_store(), make_run(), Path(tmp) / "reports", NOW)
            self.assertEqual([p.name for p in path.parent.iterdir()], ["Some_User_20261004-153005.md"])
            text = path.read_text(encoding="utf-8")
        self.assertIn("# Coaching report: Some.User", text)
        self.assertIn("- Games analyzed: 6 loaded, 0 with engine analysis", text)
        self.assertIn("- Model: m-test", text)
        self.assertIn("- Agent turns used: 7", text)
        self.assertIn("- Self-audit: not run", text)
        self.assertIn("## My own heading\nDo X.", text)
        self.assertNotIn("Cap reached", text)

    def test_code_adds_no_section_template(self):
        header = build_header("u", make_store(), make_run(), NOW)
        self.assertEqual([l for l in header.splitlines() if l.startswith("#")], ["# Coaching report: u"])

    def test_cap_reached_is_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_report("u", make_store(), make_run("cap_reached"), Path(tmp), NOW)
            self.assertIn("Cap reached", path.read_text(encoding="utf-8"))

    def test_same_second_runs_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write_report("u", make_store(), make_run(report="first"), Path(tmp), NOW)
            b = write_report("u", make_store(), make_run(report="second"), Path(tmp), NOW)
            self.assertNotEqual(a, b)
            self.assertIn("first", a.read_text(encoding="utf-8"))
            self.assertIn("second", b.read_text(encoding="utf-8"))

    def test_audit_outcome_shown_in_header(self):
        run = make_run()
        run.audit = "revised"
        self.assertIn("Self-audit: draft re-checked and revised", build_header("u", make_store(), run, NOW))


class TranscriptTests(unittest.TestCase):
    def test_writes_one_json_message_per_line_outside_reports(self):
        run = make_run()
        run.conversation = [{"role": "system", "content": "s"}, {"role": "assistant", "content": "caf\u00e9"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_transcript("Some.User", run, Path(tmp) / "logs", NOW)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(path.name, "Some_User_20261004-153005.jsonl")
        self.assertEqual([__import__("json").loads(l)["role"] for l in lines], ["system", "assistant"])


if __name__ == "__main__":
    unittest.main()

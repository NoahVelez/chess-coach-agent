"""The agent loop: send conversation to the model, parse tool call vs. final
answer, run the tool myself, feed the result back. Repeat up to a hard cap.

This is the only place in the project that calls the OpenAI API, and the
only place that decides what the facts *mean*. Everything it reads comes from
`FactsStore`, which only reports numbers.

The loop never decides the next question. Each model turn names its own
`open_question`, says `why_this_next`, and states its `decision_so_far`; the
loop checks the shape of that, logs it, and keeps it in the conversation.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import TextIO

import openai
from openai import OpenAI

from agent.facts_store import TOOL_SCHEMA, FactsStore, call_tool

MAX_ITERATIONS = 20  # valid model turns (tool calls + the final answer) before the cap forces a report
MAX_FORMAT_RETRIES = 3  # consecutive malformed replies tolerated; these do not use up investigation turns
DEFAULT_MODEL = "gpt-4o-mini"
TEMPERATURE = 0.4

# Keys every tool-calling turn must carry. Only the shape is checked, never the content.
TURN_REASONING_KEYS = ("open_question", "why_this_next", "would_change_my_mind_if", "decision_so_far")

SYSTEM_PROMPT = f"""You are an opinionated chess coach. You are graded on clear decisions, not on \
coverage. A report full of hedges ("it seems", "might want to consider", "could be worth \
looking at") with no ranking fails the task.

GOAL: for one Chess.com player, produce a single coaching report that tells them, with evidence, \
what they typically play, where their games tend to turn against them (especially when the \
opponent leaves the lines the player knows, and whether the player copes), what opponents \
actually throw at them, and what to do about it: what to study, what to review, and what to \
change, including alternative openings or lines that fit what this player demonstrably does. \
You decide how to get there: which questions to ask, in what order, which color or line to dig \
into, what to skip, and when you know enough. Nothing is scripted for you.

You see no data directly. You request facts with tools. Tools only measure, count and look \
things up; they never rank, label or recommend. All interpretation and every recommendation is \
yours. Engine tools are slow and cost time, so use them where you have a reason to.

STANDARD OF EVIDENCE:
- Every claim must be traceable to a tool result you actually received in this conversation. \
Never invent games, moves, evaluations, counts or rates. If you did not see it, you do not know it.
- Cite evidence in the report: game indexes, move numbers/plies, counts and rates from tool results.
- Respect sample sizes. Where the counts are too small to conclude, say so using the actual counts.
- A recommended alternative must be justified from this player's own facts (and, where useful, \
engine evaluation of the line via a tool), not from general opening folklore.

DECISIVENESS: the final report must rank its recommendations and say what to do first. For each \
major finding give: the claim, the evidence, a confidence level, and the concrete action. State \
at least one thing you considered and rejected, and why. You choose the report's section \
headings; write Markdown.

PROTOCOL: reply with EXACTLY ONE JSON object per turn and no other text.
- To call a tool:
  {{"type": "tool", "name": "<tool_name>", "args": {{...}},
    "open_question": "<what you are trying to resolve right now>",
    "why_this_next": "<why this beats the other questions you could ask now>",
    "would_change_my_mind_if": "<what result from this tool would make you change course>",
    "decision_so_far": "<your current working conclusion; revise it freely>"}}
- To finish:
  {{"type": "final", "decision_so_far": "<your headline decision>", "report": "<the Markdown report>"}}
You may abandon a line of inquiry, go deeper on one color, or skip an area if the data says it \
does not matter. You may finish early on a clear picture, but not without a decision. You have at \
most {MAX_ITERATIONS} turns. If you reach that limit without finishing, you will be forced to \
write the best report you can from what you have learned, so do not leave your decisions to the end.

Available tools (name: description and arguments):
{json.dumps(TOOL_SCHEMA, indent=1)}"""

FORCED_FINAL_MESSAGE = (
    "The turn cap has been reached. Do not call any more tools. Write the best report you can from "
    "what you have already learned, following the report standards in your instructions, and say "
    "where the evidence you gathered falls short. Reply with exactly one JSON object: "
    '{"type": "final", "decision_so_far": "...", "report": "<Markdown report>"}.'
)


@dataclass
class TurnRecord:
    turn: int
    open_question: str
    why_this_next: str
    decision_so_far: str
    action: str  # "tool_name(args)" or "final"


@dataclass
class AgentRun:
    report: str
    status: str  # "final" | "cap_reached" | "unparseable" | "model_error"
    turns_used: int
    model: str
    trail: list[TurnRecord] = field(default_factory=list)


def get_model() -> str:
    return os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL


def run_coaching_agent(
    store: FactsStore,
    username: str,
    client: OpenAI | None = None,
    max_iterations: int = MAX_ITERATIONS,
    model: str | None = None,
    log: TextIO | None = None,
) -> AgentRun:
    log = log or sys.stderr
    model = model or get_model()
    client = client or OpenAI()
    session = _ModelSession(client, model)

    conversation: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _opening_message(store, username)},
    ]
    trail: list[TurnRecord] = []
    turns_used = 0

    def finish(report: str, status: str) -> AgentRun:
        return AgentRun(report=report, status=status, turns_used=turns_used, model=model, trail=trail)

    try:
        while turns_used < max_iterations:
            parsed = _next_valid_reply(session, conversation)
            if parsed is None:
                return finish(_fallback_report(trail, "model output never parsed after retries"), "unparseable")
            turns_used += 1
            _log_turn(log, turns_used, max_iterations, parsed)
            trail.append(_trail_entry(turns_used, parsed))

            if parsed["type"] == "final":
                return finish(parsed["report"], "final")

            conversation.append({"role": "user", "content": _run_tool(store, parsed)})

        conversation.append({"role": "user", "content": FORCED_FINAL_MESSAGE})
        print("[agent] iteration cap reached; forcing a final report", file=log)
        parsed = _next_valid_reply(session, conversation, final_only=True)
        if parsed is None:
            return finish(_fallback_report(trail, "iteration cap reached and the forced report never parsed"), "unparseable")
        turns_used += 1
        trail.append(_trail_entry(turns_used, parsed))
        return finish(parsed["report"], "cap_reached")
    except openai.OpenAIError as exc:
        print(f"[agent] model call failed: {exc}", file=log)
        return finish(_fallback_report(trail, f"model call failed: {exc}"), "model_error")


def _opening_message(store: FactsStore, username: str) -> str:
    records = store.records
    as_white = sum(1 for r in records if r.player_color == "white")
    return (
        f"Player: {username}. Data loaded: {len(records)} recent rapid/blitz games "
        f"({as_white} as White, {len(records) - as_white} as Black). "
        "Produce the coaching report."
    )


def _run_tool(store: FactsStore, parsed: dict) -> str:
    name = parsed["name"]
    try:
        result = call_tool(store, name, parsed.get("args") or {})
    except Exception as exc:  # surfaced to the model as a fact, not swallowed
        result = {"error": str(exc)}
    return f"TOOL RESULT ({name}): {json.dumps(result, separators=(',', ':'))}"


def _next_valid_reply(session: "_ModelSession", conversation: list[dict], final_only: bool = False) -> dict | None:
    """Ask the model until it sends a well-shaped reply; malformed replies get one corrective
    message each and do not count as investigation turns."""
    failures = 0
    while failures <= MAX_FORMAT_RETRIES:
        reply = session.call(conversation)
        conversation.append({"role": "assistant", "content": reply})
        parsed, problem = _parse_reply(reply, final_only)
        if parsed is not None:
            return parsed
        failures += 1
        conversation.append(
            {"role": "user", "content": f"Your last reply was rejected: {problem} Reply with exactly one JSON object as instructed."}
        )
    return None


def _parse_reply(reply: str, final_only: bool = False) -> tuple[dict | None, str]:
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, "it was not valid JSON."
    if not isinstance(data, dict):
        return None, "it was not a JSON object."

    kind = data.get("type")
    if kind == "final":
        if not _is_text(data.get("report")):
            return None, 'a "final" reply needs a non-empty string "report".'
        if not _is_text(data.get("decision_so_far")):
            return None, 'a "final" reply needs a non-empty string "decision_so_far".'
        return data, ""
    if kind == "tool":
        if final_only:
            return None, 'no tool calls are allowed now; reply with {"type": "final", ...}.'
        if not _is_text(data.get("name")):
            return None, 'a "tool" reply needs a string "name".'
        if "args" in data and not isinstance(data["args"], dict):
            return None, '"args" must be a JSON object.'
        missing = [k for k in TURN_REASONING_KEYS if not _is_text(data.get(k))]
        if missing:
            return None, f"a tool call must also include non-empty string field(s): {missing}."
        return data, ""
    return None, 'the "type" field must be "tool" or "final".'


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _trail_entry(turn: int, parsed: dict) -> TurnRecord:
    if parsed["type"] == "final":
        action = "final"
    else:
        action = f"{parsed['name']}({json.dumps(parsed.get('args') or {}, separators=(',', ':'))})"
    return TurnRecord(
        turn=turn,
        open_question=parsed.get("open_question", ""),
        why_this_next=parsed.get("why_this_next", ""),
        decision_so_far=parsed.get("decision_so_far", ""),
        action=action,
    )


def _log_turn(log: TextIO, turn: int, cap: int, parsed: dict) -> None:
    entry = _trail_entry(turn, parsed)
    print(f"\n[turn {turn}/{cap}] {entry.action}", file=log)
    if entry.open_question:
        print(f"  open_question:  {entry.open_question}", file=log)
        print(f"  why_this_next:  {entry.why_this_next}", file=log)
    print(f"  decision_so_far: {entry.decision_so_far}", file=log)


def _fallback_report(trail: list[TurnRecord], reason: str) -> str:
    """Report body for runs where the model never produced a usable final answer."""
    lines = [
        f"**No model-written report: {reason}.** What follows is the agent's recorded reasoning trail.",
        "",
    ]
    if not trail:
        lines.append("The agent did not complete a single valid turn.")
    for t in trail:
        lines.append(f"- Turn {t.turn}: `{t.action}`")
        if t.open_question:
            lines.append(f"  - Question: {t.open_question}")
        lines.append(f"  - Decision so far: {t.decision_so_far}")
    return "\n".join(lines)


class _ModelSession:
    """One OpenAI chat call at a time. Drops optional parameters a model rejects."""

    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model
        self._optional = {"response_format": {"type": "json_object"}, "temperature": TEMPERATURE}

    def call(self, conversation: list[dict]) -> str:
        while True:
            try:
                response = self._client.chat.completions.create(
                    model=self._model, messages=conversation, **self._optional
                )
                return response.choices[0].message.content or ""
            except openai.BadRequestError as exc:
                rejected = [k for k in self._optional if k in str(exc)]
                if not rejected:
                    raise
                for key in rejected:
                    del self._optional[key]

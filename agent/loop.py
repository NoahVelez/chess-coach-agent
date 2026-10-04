"""The agent loop: send conversation to the model, parse tool call vs. final
answer, run the tool myself, feed the result back. Repeat up to a hard cap.

This is the only place in the project that calls the OpenAI API, and the
only place that decides *what a mistake means*. Everything it reads comes
from `FactsStore`, which only reports numbers.
"""

from __future__ import annotations

import json

from openai import OpenAI

from agent.facts_store import TOOL_SCHEMA, FactsStore, call_tool

MAX_ITERATIONS = 8
MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = f"""You are a chess coach. You have access to objective engine facts about a \
player's recent games (eval swings in centipawns, engine best moves, ratings, results). \
You do NOT see any of this directly — you must request it with tools.

Your job is the one thing the facts cannot tell you: which mistake(s) are most worth coaching \
on, what category of lesson they represent (e.g. calculation discipline, piece safety, opening \
principle, tactical motif, time management, or another category you identify), and how to \
explain that lesson usefully for THIS player given their rating and recent pattern of mistakes. \
Two reasonable coaches could pick different lessons from the same facts — that judgment is \
your job, not a formula.

Available tools:
{json.dumps(TOOL_SCHEMA, indent=2)}

Respond with EXACTLY ONE JSON object per turn, no other text:
- To call a tool: {{"type": "tool", "name": "<tool_name>", "args": {{...}}}}
- To finish:      {{"type": "final", "report": "<markdown coaching report>"}}

Call tools as many times as you need to form a real opinion, but do not stall — once you have \
enough to make a defensible coaching call, finish. You have at most {MAX_ITERATIONS} turns total."""


def run_coaching_agent(store: FactsStore, username: str, client: OpenAI | None = None) -> str:
    client = client or OpenAI()
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Player: {username}. Build a coaching report. "
                "Start by requesting the game summaries."
            ),
        },
    ]

    for turn in range(1, MAX_ITERATIONS + 1):
        reply = _call_model(client, conversation)
        conversation.append({"role": "assistant", "content": reply})

        parsed = _parse_reply(reply)
        if parsed is None:
            conversation.append(
                {
                    "role": "user",
                    "content": "Your last reply was not valid JSON. Respond with exactly one JSON object as instructed.",
                }
            )
            continue

        if parsed["type"] == "final":
            return parsed["report"]

        if parsed["type"] == "tool":
            try:
                result = call_tool(store, parsed["name"], parsed.get("args", {}))
                tool_output = json.dumps(result)
            except Exception as exc:  # surfaced to the model as a fact, not swallowed
                tool_output = json.dumps({"error": str(exc)})
            conversation.append({"role": "user", "content": f"TOOL RESULT: {tool_output}"})
            continue

    return (
        "FINAL (forced — iteration cap reached before the agent concluded):\n"
        "The agent could not settle on a coaching takeaway within the allotted turns. "
        "Re-run with a smaller game count or investigate the conversation log."
    )


def _call_model(client: OpenAI, conversation: list[dict]) -> str:
    response = client.chat.completions.create(model=MODEL, messages=conversation, temperature=0.4)
    return response.choices[0].message.content or ""


def _parse_reply(reply: str) -> dict | None:
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if data.get("type") not in ("tool", "final"):
        return None
    return data

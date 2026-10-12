---
name: redesign-agent-decisive-coach
description: Rework the chess coach agent from a scripted summarizer into a goal-driven agent that chooses its own next question, makes explicit coaching decisions about the player's openings and off-script play, and writes exactly one Markdown report per run to reports/.
disable-model-invocation: true
argument-hint: "Optional: Chess.com username and game count to use for the verification run (default: ask the user)"
---
Rework the existing agent in [agent/loop.py](../../agent/loop.py), [agent/facts_store.py](../../agent/facts_store.py), [tools/](../../tools) and [main.py](../../main.py) so it behaves like a coach making decisions, not a pipeline summarizing numbers. Stay inside the constraints of [what_counts_as_an_agent.md](../../requirements/what_counts_as_an_agent.md) and [mini_project_brief.md](../../requirements/mini_project_brief.md), and keep the problem framing from [build-chess-coach-agent.prompt.md](./build-chess-coach-agent.prompt.md).

## What is wrong today

- `run_coaching_agent` is effectively scripted: the user message says "Start by requesting the game summaries", every run does the same first move, and the model's job collapses into summarizing the flagged mistakes.
- `main.py` runs Stockfish on **every** game up front, so the agent never chooses what is worth analyzing.
- The facts store has no **opening** facts. It cannot answer "what does this player open with?" or "what did the opponent play when they left the usual line?", because moves, ECO codes and opening names are never exposed.
- The only output is printed to the terminal; there is no durable artifact.
- The iteration cap (8) is too small for real investigation, and an invalid JSON reply burns a turn.

## Goal (the agent's single objective)

Given a Chess.com username, produce one coaching report that tells the player, with evidence:

1. **What they typically play**: their habitual openings and structures as White and as Black.
2. **When things go wrong**: where games tend to turn against them, especially when the opponent leaves the player's usual (prepared) lines, and whether the player responds well.
3. **What the opponent actually plays**: the recurring off-script moves and systems the player faces.
4. **What to do about it**: what to study, what to review, what to consider changing, including alternative openings or lines that would naturally fit this player's demonstrated style.

The agent must reach **decisions** (rank, pick, recommend, reject), not a tour of the data.

## Hard requirement: the agent chooses the next question

The questions are **not** pre-picked, enumerated, or hard-coded anywhere (not in the system prompt, not in a Python list, not as a fixed sequence of tool calls). The system prompt states the goal and the standard of evidence, and nothing else. The four goal points above are the destination; how to get there, and in what order, is the model's call.

The questions below are **acceptance examples only**, used to judge whether the design is flexible enough. They must not appear as a checklist in the code or prompt:

- What are the user's standard openings as White and as Black?
- When the opponent goes off script, does the user respond well?
- What are the common off-script moves they face?
- What alternative openings or lines would fit the player's style?

Implement "chooses its next question" concretely:

- Every model turn is one JSON object that includes, alongside the tool call: `open_question` (what it is trying to resolve now), `why_this_next` (why this beats the other questions it could ask), and `decision_so_far` (its current working conclusion, which it may revise). The loop logs these each turn and keeps them in the conversation so the agent's reasoning trail is visible and auditable.
- A turn that calls a tool must also say what result would change its mind. The loop does not enforce the content, only the shape.
- The model may abandon a line of inquiry, go deeper on one color, or skip a whole area if the data says it doesn't matter. Nothing in the loop assumes a fixed order or that every area is covered.
- The agent decides when it has enough to finish. Finishing early on a clear picture is fine; finishing without any decision is not (see "Decisiveness" below).

## Tools: facts only, richer, and on demand

Tools stay facts-only: they measure, count, group and look up. They never rank, label a move "bad opening choice", name a "style", or recommend anything. Decide what a fact means is the model's job. Add or reshape tools so the agent *can* ask the questions above, without any tool pre-answering them:

- **Games + moves without the engine.** `fetch_recent_games` should keep PGN and also expose per-game opening facts: ECO code and opening name from the PGN headers (`ECO`, `ECOUrl`) when present, the SAN move list, result, color, ratings, time class, and clock/termination data when available. Opening facts need no Stockfish, so build them from PGN parsing only.
- **Aggregation tools** (counts and rates only), for example: the player's first-N-ply sequences grouped by color with frequency and score; for a given position prefix and color, the distribution of moves the opponent played and the resulting score; the first ply at which a game left a given prefix and who left it. Parameterize them (color, prefix, depth in plies, minimum sample) so the model decides what to ask for rather than the tool returning a canned report.
- **On-demand engine tools.** Move `analyze_game` out of `main.py`'s upfront loop. Expose it (and a cheaper "evaluate this position/line" tool, using the engine to return the eval and best move for a given move sequence at the existing fixed depth) so the agent decides which games, plies or candidate lines deserve engine time. Cache results in the facts store so repeated requests are free. Keep [MISTAKE_THRESHOLD_CP](../../tools/stockfish_tool.py) documented and fixed per run.
- **Style-relevant facts, not style verdicts.** Provide raw measurements that let the model *infer* style (e.g. game length, which side castles, piece-trade counts by move 20, frequency of early queen moves, average eval swing by phase). Never return a label like "aggressive".
- Every tool result must be size-bounded (a documented cap on rows or plies, with a `truncated: true` flag) so a long investigation does not overflow the context window.
- Update `TOOL_SCHEMA` so the model sees accurate argument descriptions. Keep `call_tool` as the single router. Unknown tools or bad args come back to the model as a `{"error": ...}` fact, as they do now.

Do not add an opening book, an ECO-to-advice table, or any hard-coded "good openings for style X" mapping. If the model recommends an alternative, it must justify it from this player's own facts (and, where useful, engine evaluation of the line via the tool above).

## Decisiveness (make it commit)

- The system prompt must tell the model it is an opinionated coach who is graded on clear decisions, and that hedged summaries ("it seems", "might want to consider") with no ranking fail the task.
- The final report must **rank** its recommendations and say what to do first, and for each major finding give: the claim, the evidence (game indexes, move numbers, counts or rates from tool results), a confidence level, and the concrete action (what to study, what to review, what to try instead).
- The report must state at least one thing the agent considered and **rejected** (and why), and note where the sample is too small to conclude, using the counts from the tools.
- Claims must be traceable to tool results actually seen in the conversation. The prompt must forbid inventing games, moves, or statistics.

## Output: exactly one report per run in `reports/`

- Each run writes **one** Markdown file to `reports/` (create the folder if missing) and prints its path. Suggested name: `reports/<username>_<YYYYMMDD-HHMMSS>.md`. No run may produce zero reports or more than one.
- The file is written by deterministic code in `main.py`, not by a model tool. The model returns the report body in its `final` message.
- The **sections are chosen by the agent** based on what it found. The code must not impose a section template. The only code-generated part is a short header (username, number of games analyzed, date, model name, number of agent turns used) placed above the model's body.
- If the iteration cap is reached, do not return a canned failure string. Make one last forced call that tells the model to write the best report it can from what it has already learned, mark that report clearly as "cap reached", and write it to `reports/` like any other. Also write a report if the model produces output that never parses after retries, containing the raw transcript summary, so the single-report guarantee holds.
- Do not gitignore `reports/` contents (a sample report may be committed), but add `reports/.gitkeep` so the folder exists.

## Loop changes

Keep it a hand-rolled loop with direct OpenAI calls, conversation history, a hard cap, and a parser for tool calls vs. final answer. No agent framework.

- Raise the iteration cap to something that allows real investigation (propose ~20) and make it a named constant.
- A malformed JSON reply should get one corrective message but not consume an investigation turn (use a separate small retry counter, and `response_format={"type": "json_object"}` if supported by the chosen model).
- Make the model configurable via `OPENAI_MODEL` in `.env` / [.env.example](../../.env.example), defaulting to the current model. Note in the README if a stronger model gives noticeably better decisions.
- Remove the scripted opening instruction from the first user message. Tell the agent only the username, the available data volume (number of games and colors), and the goal.
- Default `--games` should rise (propose 40), because openings need sample size. Keep it a CLI argument.
- Log each turn's `open_question` / `decision_so_far` to stderr so a human can watch the agent choose its path.

## Constraints that still apply

- Own Python code calls the OpenAI API directly. No LangChain/LangGraph/CrewAI or similar.
- Tools return facts only. All interpretation stays with the model.
- The path must genuinely vary with what the model finds (which color it digs into, which lines, how many engine calls). If two different players' runs would produce the same call sequence, the design has regressed into a script.
- No secrets in code; `OPENAI_API_KEY` stays in `.env`. Use only the player's public Chess.com data.
- Preserve the existing structure (`agent/`, `tools/`, `main.py`). Keep `requirements.txt` pinned; add no new dependency unless unavoidable.
- Make real, incremental commits (tools, then store/schema, then loop, then CLI/report writing, then docs). Don't make unrelated changes.

## Before writing code

Confirm with me, in one short message: the default game count, the iteration cap, and the model to use. Then proceed in this order: opening/aggregation tools with offline tests, on-demand engine tools, loop and prompt changes, report writing in `main.py`, docs.

## Verify before finishing

- Offline tests (fixture PGNs, no network, no engine where possible) cover each new aggregation tool, including truncation flags and empty-result cases.
- Grep the system prompt and tools to confirm there is no hard-coded question list, no opening-advice table, and no verdict words in tool output.
- Do a real run for a username (ask me if not supplied) and confirm: exactly one new file in `reports/`, the section headings are model-chosen, the report ranks recommendations with cited evidence, and the stderr log shows `open_question` values that change based on earlier results.
- Run it for a second player or a different game count and confirm the sequence of tool calls differs.
- Force the cap with a tiny value and confirm a "cap reached" report is still written (and only one).
- Update [README.md](../../README.md) and run the [update-docs.prompt.md](./update-docs.prompt.md) workflow so `docs/` (agent loop, tools, data flow, design decisions) matches the new behavior.

Finish with a brief summary: what changed, what the agent now decides, and anything you left out or want my call on.

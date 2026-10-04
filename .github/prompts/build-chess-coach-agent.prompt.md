---
description: "Scaffold the BUAN 6V99 mini-project: a hand-rolled Python agent that pulls a player's Chess.com games, gets objective facts from Stockfish, and uses an LLM to judge the coaching takeaway for each mistake."
agent: "agent"
argument-hint: "Chess.com username and number of recent games to analyze (defaults: ask the user)"
---

Build the mini-project described in [mini_project_brief.md](../../requirements/mini_project_brief.md), constrained by [what_counts_as_an_agent.md](../../requirements/what_counts_as_an_agent.md), and motivated by the problem framed in [discussion_with_professor.md](../../requirements/discussion_with_professor.md).

## Problem

A chess coach for the player, not the position. Stockfish can say a move lost 2.5 points of evaluation; it cannot say whether the lesson is calculation discipline, piece safety, an opening principle, or a tactical motif the player keeps missing. That judgment — picking the most useful coaching takeaway and explaining it for *this* player — is the one decision that must be made by the model, not a rule.

## Non-negotiable constraints (from the course guide)

- My own Python code calls the OpenAI API directly. No LangChain/LangGraph/CrewAI or similar framework.
- The agent is a real loop (not one single prompt-and-done call): conversation history, a hard cap of N iterations, a parser for tool calls vs. a final answer. Model the loop on the ~90-line pattern in [what_counts_as_an_agent.md](../../requirements/what_counts_as_an_agent.md).
- Tools return facts only (eval numbers, best moves, blunder flags, game metadata). They must never decide what a fact means or which mistake matters most — that interpretation stays with the model.
- The path must genuinely vary based on what the model finds (e.g., how many moves/games it digs into, which mistake it chooses to focus on, whether it pulls more surrounding context before concluding) — not a fixed "for each move do X" script wearing an LLM call as a hat.
- No secrets committed: `OPENAI_API_KEY` goes in `.env`, `.env` is in `.gitignore` from the first commit.
- Use only the player's own public Chess.com data (non-sensitive).

## Data flow

1. **Input**: a Chess.com username and a number of recent games to look back on (both provided by the user at runtime — ask for or accept as CLI args, don't hardcode).
2. **Tool — `fetch_recent_games(username, count)`**: calls the public Chess.com API to pull the player's N most recent games as PGN. Returns raw facts (PGN text, opponent rating, result, color played, date). No interpretation.
3. **Tool — `analyze_game(pgn)`**: runs the game through a local Stockfish engine (via `python-chess`'s engine interface) move by move. Returns per-move facts only: centipawn eval before/after, best move per engine, and an eval-swing number. Pick one sensible, documented threshold to flag a move as a "mistake" candidate (e.g., swing beyond X centipawns) — this flag is still just a fact ("this move lost N points"), not a verdict on what it means.
4. **Agent loop**: given the flagged moves across the requested games, the model decides — not a fixed rule — which mistake(s) are most worth coaching on, what category the lesson falls into (calculation discipline, piece safety, opening principle, tactical motif, or another category it identifies), and how to phrase the takeaway for this player (it may use rating and recent-mistake patterns across the fetched games as context, per the professor's note that the right lesson depends on who's playing). The loop can call tools again (e.g., re-fetch/re-analyze a specific game, or look at more moves of context) before producing a `FINAL:` coaching report.
5. **Output**: a readable coaching report (terminal or Markdown) per analyzed game: the position/mistake, the engine facts, the chosen lesson category, and a plain-English explanation of why that's the useful takeaway for this player.

## Repository requirements

- Sensible structure: e.g. `agent/` (loop + prompt building), `tools/` (chess.com fetch, stockfish analysis), `main.py` or CLI entry point. Not one monolithic file.
- `requirements.txt` (or `pyproject.toml`) pinning `python-chess`, `requests`, `openai`, `python-dotenv`.
- `README.md`: the problem this solves, how the agent decides (loop + judgment split), setup (Stockfish binary install/path, `.env` with `OPENAI_API_KEY`), and exact run instructions.
- `.gitignore` covering `.env`, `__pycache__/`, `.venv/`.
- Real incremental commits as the project is built, not one "upload" commit.

## Before writing code

Confirm with me: the Stockfish binary location/how it'll be installed on this machine, and the eval-swing threshold for flagging a mistake candidate. Then scaffold the repo structure, implement the tools first (facts only, testable independently), then the agent loop, then wire up the CLI entry point.

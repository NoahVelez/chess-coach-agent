# Chess Coach Agent

Mini-project for BUAN 6V99 — Agentic AI & Process Automation.

## Problem

Stockfish can tell you that a move lost 2.5 points of evaluation. It cannot tell you
*what the player should learn from it*. The same blunder deserves a different lesson
depending on who made it: "check what's attacked before you move" is the right takeaway
for one player and condescending to another who miscalculated a deeper line. Picking the
most useful coaching lesson — calculation discipline, piece safety, an opening principle,
a tactical motif, or something else — is a judgment call that two good coaches could make
differently from identical engine output. That's the one decision this agent exists to make.

## How it decides (the agent vs. the facts)

- **Facts (deterministic, no judgment)**: `tools/chess_com.py` pulls a player's recent
  games from the public Chess.com API. `tools/stockfish_tool.py` runs each game through a
  local Stockfish engine and reports, per move: the eval before/after, the swing in
  centipawns, and whether that swing crosses a fixed threshold (100 cp). These modules
  never decide what a mistake *means* — they only measure.
- **Judgment (the model)**: `agent/loop.py` runs a real loop against the OpenAI API. The
  model is handed tool access to those facts — game summaries, full move lists, player
  rating/record — and decides for itself which games to inspect, which mistake(s) are
  worth coaching on, what category of lesson they represent, and how to phrase that for
  this specific player. It can call tools multiple times (e.g. pull full move context
  around a specific mistake) before it commits to a final report. The path it takes
  depends entirely on what it finds — nothing here is scripted.
- The loop is hand-rolled (`agent/loop.py`): send conversation → parse a JSON reply as
  either a tool call or a final report → run the tool myself → feed the result back.
  Capped at 8 turns so a stuck loop can't run away on API cost.

## Setup

1. Install [Stockfish](https://stockfishchess.org/) (e.g. `winget install Stockfish.Stockfish`
   on Windows), or point `STOCKFISH_PATH` at an existing binary.
2. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in:
   - `OPENAI_API_KEY` — your OpenAI API key
   - `STOCKFISH_PATH` — full path to `stockfish.exe` (optional if it's already on `PATH`)

## Run

```powershell
.venv\Scripts\python main.py <chess.com-username> --games 15
```

Only analyzes rapid and blitz games (bullet games are excluded as too fast to reflect
real decision-making). Uses only the given player's own public Chess.com game history —
no private or third-party data.

## Project layout

```
tools/           facts-only: Chess.com fetch, Stockfish analysis
agent/           the loop, the tool router, the one judgment call
main.py          CLI entry point
```

# Chess Coach Agent

Mini-project for BUAN 6V99 — Agentic AI & Process Automation.

## Problem

Stockfish can tell you that a move lost 2.5 points of evaluation. It cannot tell you
*what the player should do about it*. Whether a player should study the Italian, drop
the Caro-Kann, or just review how they handle early surprises is a judgment call that two
good coaches could make differently from identical numbers. That's the decision this agent
exists to make: given a Chess.com username, it writes one coaching report that says what
the player typically opens with, where games turn against them (especially when the
opponent leaves the player's usual line), what opponents actually play, and what to do
first, with evidence.

## How it decides (the agent vs. the facts)

- **Facts (deterministic, no judgment)**: `tools/` fetches the player's recent games from
  the public Chess.com API (PGN, ECO code, opening name, SAN moves, clocks) and
  offers counting/grouping tools over them (opening sequences by color, what move came
  next after a given line, where and by whom a game left a reference line, raw
  style measurements). Stockfish is an on-demand tool, not an up-front pass: the agent
  asks for a whole-game analysis or a single position evaluation when it wants one.
  Tools never rank, label or recommend.
- **Judgment (the model)**: `agent/loop.py` runs a real loop against the OpenAI API. There
  is no scripted question list. On every turn the model names its `open_question`,
  `why_this_next`, `would_change_my_mind_if` and `decision_so_far`, then calls a tool or
  finishes. The loop logs that reasoning to stderr and keeps it in the conversation. It
  may go deep on one color, drop a line of inquiry, or finish early; the path depends on
  what it finds.
- The loop is hand-rolled (`agent/loop.py`): send conversation -> parse a JSON reply as
  either a tool call or a final report -> run the tool myself -> feed the result back.
  Capped at 20 turns. A malformed reply gets a corrective message without using up a turn.
  If the cap is hit, one last forced call makes the model write the best report it can.
- **Output**: each run writes exactly one Markdown file to `reports/`
  (`<username>_<YYYYMMDD-HHMMSS>.md`). `main.py` adds a short header (username, games,
  date, model, turns); the sections are the agent's own choice.

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
.venv\Scripts\python main.py <chess.com-username> --games 40
```

| Argument | Default | Meaning |
|----------|---------|---------|
| `username` | required | Chess.com username |
| `--games` | 40 | Recent rapid/blitz games to load (openings need sample size) |
| `--threshold` | 100 | Centipawn swing that flags a mistake candidate (fixed for the run) |
| `--max-turns` | 20 | Agent turn cap before a report is forced |

The path of the written report is printed on stdout; the agent's per-turn reasoning goes
to stderr. Run the offline tests (no network, no engine) with
`.venv\Scripts\python -m unittest discover -s tests -t .`.

Only analyzes rapid and blitz games (bullet games are excluded as too fast to reflect
real decision-making). Uses only the given player's own public Chess.com game history —
no private or third-party data.

## Documentation

Detailed docs with diagrams live in [docs/index.md](docs/index.md).

## Project layout

```
tools/           facts-only: Chess.com fetch + PGN facts, opening/style aggregation, Stockfish
agent/           the loop, the facts store and tool router, the judgment calls
main.py          CLI entry point; writes the one report per run
reports/         generated reports (one per run)
tests/           offline unit tests
```

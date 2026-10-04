"""CLI entry point: fetch games, run the coaching agent, write exactly one report.

Usage:
    python main.py <chess.com-username> --games 40

Stockfish is not run up front. The agent asks for engine analysis on the games
and positions it decides are worth the time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.facts_store import FactsStore, GameFacts
from agent.loop import MAX_ITERATIONS, AgentRun, get_model, run_coaching_agent
from tools.chess_com import fetch_recent_games
from tools.stockfish_tool import MISTAKE_THRESHOLD_CP, StockfishSession

DEFAULT_GAMES = 40  # openings need sample size
REPORTS_DIR = Path(__file__).parent / "reports"

STATUS_NOTES = {
    "final": None,
    "cap_reached": "**Cap reached:** the agent used all of its turns and was forced to write this report from what it had learned so far.",
    "unparseable": "**Incomplete run:** the model never produced a parseable answer; the body below is the recorded reasoning trail.",
    "model_error": "**Incomplete run:** a model call failed; the body below is the recorded reasoning trail.",
}


def find_stockfish() -> str:
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    found = shutil.which("stockfish")
    if found:
        return found

    raise SystemExit(
        "Could not find a Stockfish binary. Install it (e.g. `winget install Stockfish.Stockfish`) "
        "and set STOCKFISH_PATH in your .env to the full path of stockfish.exe."
    )


def build_header(username: str, store: FactsStore, run: AgentRun, now: dt.datetime) -> str:
    """The only code-generated part of the report. Sections are chosen by the agent."""
    profile = store.get_player_profile()
    lines = [
        f"# Coaching report: {username}",
        "",
        f"- Date: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Games analyzed: {profile['games_loaded']} loaded, {profile['games_with_engine_analysis']} with engine analysis",
        f"- Model: {run.model}",
        f"- Agent turns used: {run.turns_used}",
    ]
    note = STATUS_NOTES.get(run.status)
    if note:
        lines += ["", f"> {note}"]
    return "\n".join(lines)


def write_report(username: str, store: FactsStore, run: AgentRun, reports_dir: Path = REPORTS_DIR, now: dt.datetime | None = None) -> Path:
    now = now or dt.datetime.now()
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", username)
    stem = f"{safe_name}_{now.strftime('%Y%m%d-%H%M%S')}"
    content = build_header(username, store, run, now) + "\n\n---\n\n" + run.report.strip() + "\n"

    # Exclusive creation: never overwrite an earlier run's report.
    for attempt in range(1, 100):
        path = reports_dir / (f"{stem}.md" if attempt == 1 else f"{stem}-{attempt}.md")
        try:
            with open(path, "x", encoding="utf-8") as handle:
                handle.write(content)
            return path
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not find a free report filename for {stem}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI chess coach: facts from tools, decisions from an LLM.")
    parser.add_argument("username", help="Chess.com username to analyze")
    parser.add_argument("--games", type=int, default=DEFAULT_GAMES, help="Number of recent games to look back on")
    parser.add_argument(
        "--threshold", type=int, default=MISTAKE_THRESHOLD_CP, help="Centipawn swing to flag a mistake candidate"
    )
    parser.add_argument("--max-turns", type=int, default=MAX_ITERATIONS, help="Cap on agent turns before a report is forced")
    args = parser.parse_args()

    load_dotenv()
    engine_path = find_stockfish()

    print(f"Fetching last {args.games} rapid/blitz games for '{args.username}'...", file=sys.stderr)
    records = fetch_recent_games(args.username, args.games)
    if not records:
        raise SystemExit(f"No rapid/blitz games found for '{args.username}'.")

    engine = StockfishSession(engine_path, threshold_cp=args.threshold)
    store = FactsStore([GameFacts(index=i, record=r) for i, r in enumerate(records)], engine)
    print(f"Loaded {len(records)} games. Starting the agent (model: {get_model()}).", file=sys.stderr)

    try:
        run = run_coaching_agent(store, args.username, max_iterations=args.max_turns)
        path = write_report(args.username, store, run)
    finally:
        store.close()

    print(path)
    if run.status not in ("final", "cap_reached"):
        print(f"Run ended with status '{run.status}'; the report contains the reasoning trail only.", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

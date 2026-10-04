"""CLI entry point: fetch games, get engine facts, run the coaching agent.

Usage:
    python main.py <chess.com-username> --games 15
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.facts_store import FactsStore, GameFacts
from agent.loop import run_coaching_agent
from tools.chess_com import fetch_recent_games
from tools.stockfish_tool import MISTAKE_THRESHOLD_CP, analyze_game


def find_stockfish() -> str:
    import os

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


def main() -> None:
    parser = argparse.ArgumentParser(description="AI chess coach: facts from Stockfish, judgment from an LLM.")
    parser.add_argument("username", help="Chess.com username to analyze")
    parser.add_argument("--games", type=int, default=15, help="Number of recent games to look back on")
    parser.add_argument(
        "--threshold", type=int, default=MISTAKE_THRESHOLD_CP, help="Centipawn swing to flag a mistake candidate"
    )
    args = parser.parse_args()

    load_dotenv()
    engine_path = find_stockfish()

    print(f"Fetching last {args.games} rapid/blitz games for '{args.username}'...", file=sys.stderr)
    records = fetch_recent_games(args.username, args.games)
    if not records:
        raise SystemExit(f"No rapid/blitz games found for '{args.username}'.")

    print(f"Running Stockfish analysis on {len(records)} games...", file=sys.stderr)
    games = []
    for i, record in enumerate(records):
        moves = analyze_game(record.pgn, engine_path, threshold_cp=args.threshold)
        games.append(GameFacts(index=i, record=record, moves=moves))
        print(
            f"  game {i}: {record.player_color} vs {record.opponent_username} "
            f"({len(moves)} moves, {sum(m.is_mistake_candidate for m in moves)} flagged)",
            file=sys.stderr,
        )

    store = FactsStore(games)

    print("Asking the agent to form a coaching judgment...", file=sys.stderr)
    report = run_coaching_agent(store, args.username)

    print("\n" + report)


if __name__ == "__main__":
    main()

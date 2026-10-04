"""In-memory facts store + tool router for the agent loop.

Everything here returns facts already computed by `tools.chess_com` and
`tools.stockfish_tool`. No function here judges which mistake matters,
what it means, or what the player should do about it.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.chess_com import GameRecord
from tools.stockfish_tool import MoveFact


@dataclass
class GameFacts:
    index: int
    record: GameRecord
    moves: list[MoveFact]

    def mistake_moves(self) -> list[MoveFact]:
        return [m for m in self.moves if m.is_mistake_candidate]


class FactsStore:
    """Holds the fetched+analyzed games and answers the agent's fact queries."""

    def __init__(self, games: list[GameFacts]):
        self._games = games

    def get_game_summaries(self) -> list[dict]:
        """One row per game: metadata + flagged mistake moves. No ranking or commentary."""
        summaries = []
        for game in self._games:
            summaries.append(
                {
                    "game_index": game.index,
                    "date": game.record.end_time,
                    "time_class": game.record.time_class,
                    "player_color": game.record.player_color,
                    "player_rating": game.record.player_rating,
                    "opponent_rating": game.record.opponent_rating,
                    "result": game.record.result,
                    "mistake_candidates": [
                        {
                            "move_number": m.move_number,
                            "san": m.san,
                            "eval_swing_cp": m.eval_swing_cp,
                            "engine_best_move_san": m.engine_best_move_san,
                        }
                        for m in game.mistake_moves()
                    ],
                }
            )
        return summaries

    def get_game_moves(self, game_index: int, around_move_number: int | None = None, window: int = 3) -> list[dict]:
        """Full per-move facts for one game, optionally windowed around a move number."""
        game = self._games[game_index]
        moves = game.moves
        if around_move_number is not None:
            lo, hi = around_move_number - window, around_move_number + window
            moves = [m for m in moves if lo <= m.move_number <= hi]
        return [
            {
                "move_number": m.move_number,
                "mover_color": m.mover_color,
                "san": m.san,
                "eval_before_cp": m.eval_before_cp,
                "eval_after_cp": m.eval_after_cp,
                "eval_swing_cp": m.eval_swing_cp,
                "engine_best_move_san": m.engine_best_move_san,
                "is_mistake_candidate": m.is_mistake_candidate,
            }
            for m in moves
        ]

    def get_player_profile(self) -> dict:
        """Aggregated facts across all fetched games: no interpretation, just numbers."""
        records = [g.record for g in self._games]
        if not records:
            return {}
        ratings = [r.player_rating for r in records]
        return {
            "games_analyzed": len(records),
            "earliest_rating": ratings[-1],
            "latest_rating": ratings[0],
            "wins": sum(1 for r in records if r.result == "win"),
            "losses": sum(1 for r in records if r.result not in ("win", "agreed", "repetition", "stalemate")),
            "total_mistake_candidates": sum(len(g.mistake_moves()) for g in self._games),
        }


TOOL_SCHEMA = {
    "get_game_summaries": "No arguments. Returns per-game metadata and flagged mistake candidates.",
    "get_game_moves": "Args: game_index (int, required), around_move_number (int, optional), window (int, optional, default 3). Returns full move-by-move facts for one game.",
    "get_player_profile": "No arguments. Returns aggregated rating/record/mistake-count facts across fetched games.",
}


def call_tool(store: FactsStore, name: str, args: dict):
    if name == "get_game_summaries":
        return store.get_game_summaries()
    if name == "get_game_moves":
        return store.get_game_moves(
            game_index=args["game_index"],
            around_move_number=args.get("around_move_number"),
            window=args.get("window", 3),
        )
    if name == "get_player_profile":
        return store.get_player_profile()
    raise ValueError(f"Unknown tool: {name}")

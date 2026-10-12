"""Facts-only raw measurements a coach could use to *infer* playing style.

Nothing here returns a style label. It counts castling sides, captures,
queen moves and game length from the move lists, and (for games the engine
has already analyzed) averages eval swings per phase. What those numbers say
about the player is the model's call.
"""

from __future__ import annotations

from typing import Sequence

import chess

from tools.chess_com import GameRecord
from tools.opening_facts import COLORS, MAX_ROWS, mover_of_ply
from tools.stockfish_tool import MoveFact

TRADE_WINDOW_MOVES = 20  # captures and queens are counted as of this move number
EARLY_QUEEN_WINDOW_MOVES = 10  # "early queen move" = a queen move within the player's first N moves

# Fixed measurement buckets for eval swings (by move number); not a claim about where phases "really" start.
OPENING_END_MOVE = 10
MIDDLEGAME_END_MOVE = 30


def measure_game(game: GameRecord, game_index: int) -> dict:
    board = chess.Board()
    color = game.player_color
    castled: dict[str, dict | None] = {"player": None, "opponent": None}
    captures = {"player": 0, "opponent": 0}
    first_queen_ply: int | None = None
    queen_moves_early = 0
    queens_after_window: int | None = None
    window_plies = TRADE_WINDOW_MOVES * 2

    for ply_index, san in enumerate(game.moves_san):
        move = board.parse_san(san)
        mover = mover_of_ply(color, ply_index)
        ply = ply_index + 1

        if ply <= window_plies and board.is_capture(move):
            captures[mover] += 1
        if board.is_castling(move) and castled[mover] is None:
            castled[mover] = {"side": "kingside" if board.is_kingside_castling(move) else "queenside", "ply": ply}
        piece = board.piece_at(move.from_square)
        if mover == "player" and piece is not None and piece.piece_type == chess.QUEEN:
            if first_queen_ply is None:
                first_queen_ply = ply
            if ply <= EARLY_QUEEN_WINDOW_MOVES * 2:
                queen_moves_early += 1

        board.push(move)
        if ply == window_plies:
            queens_after_window = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(
                board.pieces(chess.QUEEN, chess.BLACK)
            )

    return {
        "game_index": game_index,
        "player_color": color,
        "result": game.result,
        "total_plies": len(game.moves_san),
        "player_castled": castled["player"],
        "opponent_castled": castled["opponent"],
        f"captures_by_move_{TRADE_WINDOW_MOVES}": captures,
        f"queens_on_board_after_move_{TRADE_WINDOW_MOVES}": queens_after_window,
        "player_first_queen_move_ply": first_queen_ply,
        f"player_queen_moves_in_first_{EARLY_QUEEN_WINDOW_MOVES}_moves": queen_moves_early,
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    cap_key = f"captures_by_move_{TRADE_WINDOW_MOVES}"
    queen_key = f"queens_on_board_after_move_{TRADE_WINDOW_MOVES}"
    early_key = f"player_queen_moves_in_first_{EARLY_QUEEN_WINDOW_MOVES}_moves"
    reached = [r[queen_key] for r in rows if r[queen_key] is not None]

    def castle_count(who: str, side: str | None) -> int:
        return sum(1 for r in rows if (r[who]["side"] if r[who] else None) == side)

    return {
        "games": n,
        "mean_total_plies": _mean([r["total_plies"] for r in rows]),
        "games_ending_before_move_20": n - len(reached),
        "player_castling": {
            "kingside": castle_count("player_castled", "kingside"),
            "queenside": castle_count("player_castled", "queenside"),
            "never": castle_count("player_castled", None),
            "mean_ply": _mean([r["player_castled"]["ply"] for r in rows if r["player_castled"]]),
        },
        "opponent_castling": {
            "kingside": castle_count("opponent_castled", "kingside"),
            "queenside": castle_count("opponent_castled", "queenside"),
            "never": castle_count("opponent_castled", None),
        },
        f"mean_player_captures_by_move_{TRADE_WINDOW_MOVES}": _mean([r[cap_key]["player"] for r in rows]),
        f"mean_opponent_captures_by_move_{TRADE_WINDOW_MOVES}": _mean([r[cap_key]["opponent"] for r in rows]),
        f"games_with_both_queens_off_by_move_{TRADE_WINDOW_MOVES}": sum(1 for q in reached if q == 0),
        f"games_with_player_queen_move_by_move_{EARLY_QUEEN_WINDOW_MOVES}": sum(1 for r in rows if r[early_key] > 0),
    }


def style_measurements(games: Sequence[GameRecord], color: str | None = None) -> dict:
    """Raw per-game rows plus per-color aggregates. `color` limits to games where the player had it."""
    if color is not None and color not in COLORS:
        raise ValueError(f"color must be one of {list(COLORS)} or omitted, got {color!r}")

    rows = [measure_game(g, i) for i, g in enumerate(games) if color is None or g.player_color == color]
    by_color = {
        c: _aggregate([r for r in rows if r["player_color"] == c]) for c in COLORS if color in (None, c)
    }
    return {
        "by_color": by_color,
        "rows": rows[:MAX_ROWS],
        "truncated": len(rows) > MAX_ROWS,
    }


def phase_of(move_number: int) -> str:
    if move_number <= OPENING_END_MOVE:
        return "moves_1_10"
    if move_number <= MIDDLEGAME_END_MOVE:
        return "moves_11_30"
    return "moves_31_plus"


def eval_swing_by_phase(analyzed: Sequence[tuple[str, list[MoveFact]]]) -> dict:
    """Mean eval swing (cp lost per move) bucketed by move number, for already-analyzed games only.

    `analyzed` holds (player_color, moves) per analyzed game.
    """
    buckets: dict[str, dict[str, list[MoveFact]]] = {}
    for player_color, moves in analyzed:
        for m in moves:
            who = "player" if m.mover_color == player_color else "opponent"
            buckets.setdefault(phase_of(m.move_number), {"player": [], "opponent": []})[who].append(m)

    result = {}
    for phase in ("moves_1_10", "moves_11_30", "moves_31_plus"):
        sides = buckets.get(phase, {"player": [], "opponent": []})
        result[phase] = {
            who: {
                "moves": len(ms),
                "mean_eval_swing_cp": _mean([m.eval_swing_cp for m in ms]),
                "mistake_candidates": sum(1 for m in ms if m.is_mistake_candidate),
            }
            for who, ms in sides.items()
        }
    return {"analyzed_games": len(analyzed), "by_phase": result}

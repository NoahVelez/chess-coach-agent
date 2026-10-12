"""Builders for offline test games: no network, no engine."""

from __future__ import annotations

import chess

from tools.chess_com import GameRecord


def make_record(
    color: str,
    sans: list[str],
    result: str = "win",
    eco: str | None = None,
    opening_name: str | None = None,
) -> GameRecord:
    """Replay `sans` to make sure they are legal and to get canonical SAN (with +/#)."""
    board = chess.Board()
    canonical = []
    for san in sans:
        move = board.parse_san(san)
        canonical.append(board.san(move))
        board.push(move)
    pgn = " ".join(f"{i // 2 + 1}. {m}" if i % 2 == 0 else m for i, m in enumerate(canonical))
    return GameRecord(
        pgn=pgn,
        end_time=0,
        time_class="rapid",
        player_color=color,
        player_rating=1200,
        opponent_username="opp",
        opponent_rating=1200,
        result=result,
        eco=eco,
        opening_name=opening_name,
        moves_san=canonical,
    )


def two_ply_games(count: int, color: str = "white") -> list[GameRecord]:
    """`count` games that all differ within the first two plies."""
    board = chess.Board()
    firsts = list(board.legal_moves)
    games = []
    for first in firsts:
        board.push(first)
        for reply in list(board.legal_moves):
            games.append(make_record(color, [chess.Board().san(first), board.san(reply)]))
            if len(games) == count:
                return games
        board.pop()
    return games


def branching_games(prefix: list[str], color: str = "white") -> list[GameRecord]:
    """One game per legal move available after `prefix`."""
    board = chess.Board()
    for san in prefix:
        board.push(board.parse_san(san))
    return [make_record(color, prefix + [board.san(move)]) for move in list(board.legal_moves)]


RUY_MAIN = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]

SAMPLE_GAMES = [
    make_record("white", RUY_MAIN, "win", "C60", "Ruy Lopez"),
    make_record("white", ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6"], "checkmated", "C60", "Ruy Lopez"),
    make_record("white", ["e4", "c5", "Nf3", "d6", "d4", "cxd4"], "agreed", "B50", "Sicilian Defense"),
    make_record("white", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"], "win", "C50", "Italian Game"),
    make_record("black", ["d4", "d5", "c4", "e6", "Nc3", "Nf6"], "resigned", "D30", "Queens Gambit Declined"),
    make_record("black", ["d4", "Nf6", "c4", "e6"], "win", "E00", "Indian Defense"),
]

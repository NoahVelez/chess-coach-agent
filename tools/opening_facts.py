"""Facts-only aggregation over fetched games' move lists. No engine involved.

Every function here counts, groups and looks things up. None of them labels a
line as good or bad, names a style, or recommends anything. All inputs that
select data (color, line, depth, minimum sample) come from the caller, and every
result is size-bounded with a `truncated` flag.

Lines are matched by move order (SAN), not by resulting position, so
transpositions are not merged.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Sequence

from tools.chess_com import GameRecord

MAX_ROWS = 25  # cap on rows returned by any aggregation tool
MAX_EXAMPLE_GAMES = 8  # cap on game indexes listed per row
MAX_DEPTH_PLIES = 30
MAX_PLIES_PER_CALL = 60  # cap on plies returned by one `get_game_moves` call

COLORS = ("white", "black")
_MOVE_NUMBER = re.compile(r"^\d+\.+")


def normalize_san(san: str) -> str:
    return san.strip().rstrip("+#!?")


def normalize_line(line: str | Sequence[str] | None) -> list[str]:
    """Accept ["e4", "e5"] or "1. e4 e5 2. Nf3" and return comparable SAN tokens."""
    if line is None:
        return []
    tokens = line.split() if isinstance(line, str) else [str(t) for t in line]
    cleaned = []
    for token in tokens:
        token = _MOVE_NUMBER.sub("", token.strip())
        if token:
            cleaned.append(normalize_san(token))
    return cleaned


def annotate_line(color: str, moves: Sequence[str]) -> str:
    """Numbered line with each move tagged by who played it: "1.e4(player) c6(opponent) 2.d4(player)"."""
    parts = []
    for p, move in enumerate(moves):
        tag = mover_of_ply(color, p)
        prefix = f"{p // 2 + 1}." if p % 2 == 0 else ""
        parts.append(f"{prefix}{move}({tag})")
    return " ".join(parts)


def split_by_mover(color: str, moves: Sequence[str]) -> tuple[list[str], list[str]]:
    player = [m for p, m in enumerate(moves) if mover_of_ply(color, p) == "player"]
    opponent = [m for p, m in enumerate(moves) if mover_of_ply(color, p) == "opponent"]
    return player, opponent


def require_color(color: str | None) -> str:
    if color not in COLORS:
        raise ValueError(f"color must be one of {list(COLORS)}, got {color!r}")
    return color


def select_games(
    games: Sequence[GameRecord], color: str | None
) -> list[tuple[int, GameRecord, list[str]]]:
    """(game_index, record, normalized moves) for games the player had `color` in."""
    return [
        (i, g, [normalize_san(m) for m in g.moves_san])
        for i, g in enumerate(games)
        if color is None or g.player_color == color
    ]


def tally(records: Sequence[GameRecord]) -> dict:
    wins = sum(1 for r in records if r.outcome == "win")
    draws = sum(1 for r in records if r.outcome == "draw")
    losses = len(records) - wins - draws
    n = len(records)
    return {
        "games": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score": round((wins + 0.5 * draws) / n, 3) if n else None,
    }


def mover_of_ply(color: str, ply_index: int) -> str:
    white_moves = ply_index % 2 == 0
    return "player" if (color == "white") == white_moves else "opponent"


def _check_min_games(min_games: int) -> int:
    if not isinstance(min_games, int) or min_games < 1:
        raise ValueError("min_games must be an integer >= 1")
    return min_games


def list_games(games: Sequence[GameRecord], color: str | None = None, offset: int = 0, limit: int = MAX_ROWS) -> dict:
    """One row per game: metadata and opening headers. Newest game is index 0."""
    if color is not None:
        require_color(color)
    selected = select_games(games, color)
    limit = max(1, min(int(limit), MAX_ROWS))
    offset = max(0, int(offset))
    page = selected[offset : offset + limit]
    rows = [
        {
            "game_index": i,
            "date": g.end_time,
            "time_class": g.time_class,
            "time_control": g.time_control,
            "player_color": g.player_color,
            "player_rating": g.player_rating,
            "opponent_rating": g.opponent_rating,
            "result": g.result,
            "termination": g.termination,
            "eco": g.eco,
            "opening_name": g.opening_name,
            "total_plies": len(moves),
            "first_moves": moves[:6],
            "first_moves_annotated": annotate_line(g.player_color, moves[:6]),
        }
        for i, g, moves in page
    ]
    return {
        "games_matching": len(selected),
        "offset": offset,
        "rows": rows,
        "truncated": offset + limit < len(selected),
    }


def get_game_moves(game: GameRecord, game_index: int, from_ply: int = 1, to_ply: int | None = None) -> dict:
    """SAN moves (and clocks when available) for plies [from_ply, to_ply], 1-based inclusive."""
    total = len(game.moves_san)
    from_ply = max(1, int(from_ply))
    requested_to = total if to_ply is None else min(int(to_ply), total)
    to_ply = min(requested_to, from_ply + MAX_PLIES_PER_CALL - 1)

    plies = []
    for ply in range(from_ply, to_ply + 1):
        clock = game.clocks_sec[ply - 1] if ply - 1 < len(game.clocks_sec) else None
        plies.append(
            {
                "ply": ply,
                "move_number": (ply - 1) // 2 + 1,
                "mover_color": "white" if ply % 2 == 1 else "black",
                "mover": mover_of_ply(game.player_color, ply - 1),
                "san": game.moves_san[ply - 1],
                "clock_sec_after_move": clock,
            }
        )
    return {
        "game_index": game_index,
        "player_color": game.player_color,
        "total_plies": total,
        "plies": plies,
        "truncated": to_ply < requested_to,
    }


def opening_sequences(
    games: Sequence[GameRecord],
    color: str,
    depth_plies: int = 6,
    min_games: int = 1,
    perspective: str = "full_line",
) -> dict:
    """Group the first `depth_plies` plies of the player's games of one color.

    perspective "full_line" groups by both sides' moves; "player_moves_only" groups
    by just the player's own moves in that window, merging different opponent replies.
    """
    require_color(color)
    min_games = _check_min_games(min_games)
    if not isinstance(depth_plies, int) or not 1 <= depth_plies <= MAX_DEPTH_PLIES:
        raise ValueError(f"depth_plies must be an integer between 1 and {MAX_DEPTH_PLIES}")
    if perspective not in ("full_line", "player_moves_only"):
        raise ValueError("perspective must be 'full_line' or 'player_moves_only'")

    selected = select_games(games, color)
    groups: dict[tuple[str, ...], list[tuple[int, GameRecord]]] = defaultdict(list)
    too_short = 0
    for i, g, moves in selected:
        if len(moves) < depth_plies:
            too_short += 1
            continue
        window = moves[:depth_plies]
        if perspective == "player_moves_only":
            window = [m for p, m in enumerate(window) if mover_of_ply(color, p) == "player"]
        groups[tuple(window)].append((i, g))

    kept = {k: v for k, v in groups.items() if len(v) >= min_games}
    ordered = sorted(kept.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = []
    for sequence, members in ordered[:MAX_ROWS]:
        records = [g for _, g in members]
        row = {"player_color": color, "sequence": list(sequence)}
        if perspective == "full_line":
            row["line_annotated"] = annotate_line(color, sequence)
            row["player_moves"], row["opponent_moves"] = split_by_mover(color, sequence)
        else:
            row["player_moves"] = list(sequence)
            row["opponent_moves"] = "not part of this grouping (any reply)"
        rows.append(
            {
                **row,
                **tally(records),
                "game_indexes": [i for i, _ in members][:MAX_EXAMPLE_GAMES],
                "eco_codes": sorted({g.eco for g in records if g.eco}),
                "opening_names": sorted({g.opening_name for g in records if g.opening_name})[:3],
            }
        )
    below = {k: v for k, v in groups.items() if len(v) < min_games}
    return {
        "color": color,
        "player_color": color,
        "depth_plies": depth_plies,
        "perspective": perspective,
        "min_games": min_games,
        "games_of_color": len(selected),
        "games_shorter_than_depth": too_short,
        "groups_total": len(groups),
        "groups_below_min_games": len(below),
        "games_in_groups_below_min_games": sum(len(v) for v in below.values()),
        "rows": rows,
        "truncated": len(ordered) > MAX_ROWS,
    }


def move_distribution(games: Sequence[GameRecord], color: str, prefix, min_games: int = 1) -> dict:
    """After a move-order prefix, which move was played next, by whom, and how those games ended."""
    require_color(color)
    min_games = _check_min_games(min_games)
    line = normalize_line(prefix)
    depth = len(line)

    matching = [(i, g, m) for i, g, m in select_games(games, color) if m[:depth] == line]
    ended_here = [(i, g) for i, g, m in matching if len(m) == depth]
    groups: dict[str, list[tuple[int, GameRecord]]] = defaultdict(list)
    for i, g, moves in matching:
        if len(moves) > depth:
            groups[moves[depth]].append((i, g))

    kept = {k: v for k, v in groups.items() if len(v) >= min_games}
    ordered = sorted(kept.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    next_mover = mover_of_ply(color, depth)
    rows = [
        {
            "next_move": move,
            "played_by": next_mover,
            "line_annotated": annotate_line(color, line + [move]),
            **tally([g for _, g in members]),
            "game_indexes": [i for i, _ in members][:MAX_EXAMPLE_GAMES],
        }
        for move, members in ordered[:MAX_ROWS]
    ]
    below = {k: v for k, v in groups.items() if len(v) < min_games}
    return {
        "color": color,
        "player_color": color,
        "prefix": line,
        "prefix_annotated": annotate_line(color, line),
        "next_ply": depth + 1,
        "next_mover": mover_of_ply(color, depth),
        "games_matching_prefix": len(matching),
        "games_ending_at_prefix": len(ended_here),
        "min_games": min_games,
        "moves_below_min_games": len(below),
        "games_in_moves_below_min_games": sum(len(v) for v in below.values()),
        "rows": rows,
        "truncated": len(ordered) > MAX_ROWS,
    }


def departure_points(games: Sequence[GameRecord], color: str, line, min_games: int = 1) -> dict:
    """Compare each game of one color against a reference line: where did it first leave it, and who left?"""
    require_color(color)
    min_games = _check_min_games(min_games)
    reference = normalize_line(line)
    if not reference:
        raise ValueError("line must contain at least one move")

    selected = select_games(games, color)
    followed: list[GameRecord] = []
    ended_inside = 0
    departures: dict[tuple[int, str, str, str], list[tuple[int, GameRecord]]] = defaultdict(list)
    by_side: dict[str, list[GameRecord]] = {"player": [], "opponent": []}

    for i, g, moves in selected:
        for p, expected in enumerate(reference):
            if p >= len(moves):
                ended_inside += 1
                break
            if moves[p] != expected:
                side = mover_of_ply(color, p)
                departures[(p + 1, side, moves[p], expected)].append((i, g))
                by_side[side].append(g)
                break
        else:
            followed.append(g)

    kept = {k: v for k, v in departures.items() if len(v) >= min_games}
    ordered = sorted(kept.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = [
        {
            "player_color": color,
            "ply": ply,
            "move_number": (ply - 1) // 2 + 1,
            "departed_by": side,
            "line_annotated": annotate_line(color, reference[: ply - 1] + [played]),
            "move_played": played,
            "reference_move": expected,
            **tally([g for _, g in members]),
            "game_indexes": [i for i, _ in members][:MAX_EXAMPLE_GAMES],
        }
        for (ply, side, played, expected), members in ordered[:MAX_ROWS]
    ]
    below = {k: v for k, v in departures.items() if len(v) < min_games}
    return {
        "color": color,
        "player_color": color,
        "line": reference,
        "line_annotated": annotate_line(color, reference),
        "games_of_color": len(selected),
        "followed_whole_line": tally(followed),
        "ended_inside_line": ended_inside,
        "departed_by_player": tally(by_side["player"]),
        "departed_by_opponent": tally(by_side["opponent"]),
        "min_games": min_games,
        "departure_groups_below_min_games": len(below),
        "games_in_departure_groups_below_min_games": sum(len(v) for v in below.values()),
        "rows": rows,
        "truncated": len(ordered) > MAX_ROWS,
    }

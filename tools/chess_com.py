"""Facts-only tool: fetch a player's recent Chess.com games as PGN.

This module does no interpretation. It returns raw game records
(PGN text + metadata) exactly as Chess.com reports them, plus the opening
and move facts that can be read straight out of the PGN (no engine needed).
"""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field

import chess
import chess.pgn
import requests

CHESS_COM_API = "https://api.chess.com/pub/player/{username}/games/{year}/{month:02d}"
USER_AGENT = "buan6v99-mini-project-chess-coach (contact: student project, non-commercial)"


@dataclass
class GameRecord:
    pgn: str
    end_time: int
    time_class: str  # "bullet" | "blitz" | "rapid" | "daily"
    player_color: str  # "white" | "black"
    player_rating: int
    opponent_username: str
    opponent_rating: int
    result: str  # e.g. "win", "checkmated", "resigned", "agreed", "timeout", ...
    eco: str | None = None  # PGN [ECO] header, when present
    eco_url: str | None = None  # PGN [ECOUrl] header, when present
    opening_name: str | None = None  # name slug taken from the ECOUrl, when present
    moves_san: list[str] = field(default_factory=list)  # mainline in SAN, from move 1
    termination: str | None = None  # PGN [Termination] header, when present
    time_control: str | None = None  # PGN [TimeControl] header, e.g. "600" or "180+2"
    clocks_sec: list[float | None] = field(default_factory=list)  # remaining clock after each ply

    @property
    def outcome(self) -> str:
        """Chess.com result code collapsed to "win" | "draw" | "loss"."""
        if self.result == "win":
            return "win"
        if self.result in DRAW_RESULTS:
            return "draw"
        return "loss"


DRAW_RESULTS = frozenset({"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"})


def fetch_recent_games(
    username: str,
    count: int,
    allowed_time_classes: tuple[str, ...] = ("rapid", "blitz"),
) -> list[GameRecord]:
    """Return the player's `count` most recent games (newest first) as facts.

    Walks backwards month-by-month through the Chess.com public archive API
    until enough games matching `allowed_time_classes` are collected, or
    there is no more history. Raises `requests.HTTPError` on API failure.
    """
    username = username.strip().lower()
    games: list[GameRecord] = []

    cursor = dt.datetime.now(dt.timezone.utc)
    months_checked = 0
    max_months_to_check = 24  # safety bound: don't walk back forever for sparse accounts

    while len(games) < count and months_checked < max_months_to_check:
        url = CHESS_COM_API.format(username=username, year=cursor.year, month=cursor.month)
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        months_checked += 1

        if response.status_code == 404:
            cursor = _previous_month(cursor)
            continue
        response.raise_for_status()

        month_games = response.json().get("games", [])
        for raw in reversed(month_games):  # newest first within the month
            if raw.get("rules") != "chess":
                continue
            record = _to_game_record(raw, username)
            if record is None or record.time_class not in allowed_time_classes:
                continue
            games.append(record)
            if len(games) >= count:
                break

        cursor = _previous_month(cursor)

    return games[:count]


def _previous_month(moment: dt.datetime) -> dt.datetime:
    if moment.month == 1:
        return moment.replace(year=moment.year - 1, month=12)
    return moment.replace(month=moment.month - 1)


def _to_game_record(raw: dict, username: str) -> GameRecord | None:
    white = raw.get("white", {})
    black = raw.get("black", {})
    if white.get("username", "").lower() == username:
        player, opponent, color = white, black, "white"
    elif black.get("username", "").lower() == username:
        player, opponent, color = black, white, "black"
    else:
        return None

    pgn = raw.get("pgn")
    if not pgn:
        return None

    pgn_facts = parse_pgn_facts(pgn)
    return GameRecord(
        pgn=pgn,
        end_time=raw.get("end_time", 0),
        time_class=raw.get("time_class", "unknown"),
        player_color=color,
        player_rating=player.get("rating", 0),
        opponent_username=opponent.get("username", "unknown"),
        opponent_rating=opponent.get("rating", 0),
        result=player.get("result", "unknown"),
        **pgn_facts,
    )


def parse_pgn_facts(pgn_text: str) -> dict:
    """Read opening headers, SAN moves and clocks out of a PGN. Returns {} if unparseable."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
    except (ValueError, KeyError):
        return {}
    if game is None:
        return {}

    board = game.board()
    moves_san: list[str] = []
    clocks_sec: list[float | None] = []
    for node in game.mainline():
        moves_san.append(board.san(node.move))
        board.push(node.move)
        clocks_sec.append(node.clock())

    headers = game.headers
    eco_url = headers.get("ECOUrl")
    return {
        "eco": headers.get("ECO"),
        "eco_url": eco_url,
        "opening_name": _opening_name_from_url(eco_url),
        "moves_san": moves_san,
        "termination": headers.get("Termination"),
        "time_control": headers.get("TimeControl"),
        "clocks_sec": clocks_sec,
    }


def _opening_name_from_url(eco_url: str | None) -> str | None:
    if not eco_url:
        return None
    slug = eco_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    # Chess.com appends the deciding moves to the slug, e.g. "... 3...c5"; drop them.
    return re.sub(r"\s+\d+\.{1,3}\S*.*$", "", slug).strip() or None

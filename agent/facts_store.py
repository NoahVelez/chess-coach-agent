"""In-memory facts store + tool router for the agent loop.

Everything here returns facts computed by `tools.*`: counts, groupings, lookups
and engine measurements. No function here ranks lines, labels a move or a style,
or says what the player should do. Engine work happens only when the agent asks
for it, and each result is cached so repeating a request is free.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from tools import opening_facts, style_facts
from tools.chess_com import GameRecord
from tools.opening_facts import MAX_ROWS, mover_of_ply, normalize_line, tally
from tools.stockfish_tool import ANALYSIS_DEPTH, MoveFact, StockfishSession


@dataclass
class GameFacts:
    index: int
    record: GameRecord
    moves: list[MoveFact] | None = None  # filled only when the agent asks for engine analysis

    @property
    def analyzed(self) -> bool:
        return self.moves is not None

    def mistake_moves(self) -> list[MoveFact]:
        return [m for m in (self.moves or []) if m.is_mistake_candidate]


class FactsStore:
    """Holds the fetched games and answers the agent's fact queries."""

    def __init__(self, games: list[GameFacts], engine: StockfishSession | None = None):
        self._games = games
        self._engine = engine
        self._position_cache: dict[str, dict] = {}

    @property
    def records(self) -> list[GameRecord]:
        return [g.record for g in self._games]

    @property
    def engine_analyzed_games(self) -> int:
        return sum(1 for g in self._games if g.analyzed)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()

    # ---- game facts (no engine) -------------------------------------------------

    def get_player_profile(self) -> dict:
        """Data volume and aggregate record. Counts only."""
        records = self.records
        if not records:
            return {"games_loaded": 0}
        by_color = {c: [r for r in records if r.player_color == c] for c in opening_facts.COLORS}
        time_classes: dict[str, int] = {}
        for r in records:
            time_classes[r.time_class] = time_classes.get(r.time_class, 0) + 1
        return {
            "games_loaded": len(records),
            "games_as_white": len(by_color["white"]),
            "games_as_black": len(by_color["black"]),
            "record_overall": tally(records),
            "record_as_white": tally(by_color["white"]),
            "record_as_black": tally(by_color["black"]),
            "time_classes": time_classes,
            "latest_rating": records[0].player_rating,
            "earliest_rating": records[-1].player_rating,
            "index_order": "game_index 0 is the newest game",
            "games_with_engine_analysis": self.engine_analyzed_games,
            "engine_depth": ANALYSIS_DEPTH,
            "mistake_threshold_cp": self._engine.threshold_cp if self._engine else None,
        }

    def list_games(self, color: str | None = None, offset: int = 0, limit: int = MAX_ROWS) -> dict:
        result = opening_facts.list_games(self.records, color, offset, limit)
        for row in result["rows"]:
            row["engine_analyzed"] = self._games[row["game_index"]].analyzed
        return result

    def get_game_moves(self, game_index: int, from_ply: int = 1, to_ply: int | None = None) -> dict:
        game = self._game(game_index)
        result = opening_facts.get_game_moves(game.record, game.index, from_ply, to_ply)
        result["engine_analyzed"] = game.analyzed
        if game.moves:
            for row in result["plies"]:
                row.update(_move_fact_dict(game.moves[row["ply"] - 1]))
        return result

    def opening_sequences(
        self, color: str, depth_plies: int = 6, min_games: int = 1, perspective: str = "full_line"
    ) -> dict:
        return opening_facts.opening_sequences(self.records, color, depth_plies, min_games, perspective)

    def move_distribution(self, color: str, prefix, min_games: int = 1) -> dict:
        return opening_facts.move_distribution(self.records, color, prefix, min_games)

    def departure_points(self, color: str, line, min_games: int = 1) -> dict:
        return opening_facts.departure_points(self.records, color, line, min_games)

    def get_style_measurements(self, color: str | None = None) -> dict:
        result = style_facts.style_measurements(self.records, color)
        analyzed = [
            (g.record.player_color, g.moves)
            for g in self._games
            if g.moves is not None and color in (None, g.record.player_color)
        ]
        result["eval_swing_by_phase"] = style_facts.eval_swing_by_phase(analyzed)
        return result

    # ---- engine facts (on demand, cached) ---------------------------------------

    def analyze_game(self, game_index: int) -> dict:
        """Run Stockfish over one whole game (cached) and report the flagged moves."""
        game = self._game(game_index)
        cached = game.analyzed
        if not cached:
            game.moves = self._require_engine().analyze_game(game.record.pgn)

        flagged = game.mistake_moves()
        player_color = game.record.player_color
        rows = []
        for m in flagged[:MAX_ROWS]:
            ply = (m.move_number - 1) * 2 + (1 if m.mover_color == "white" else 2)
            rows.append({"ply": ply, "mover": mover_of_ply(player_color, ply - 1), **_move_fact_dict(m)})
        return {
            "game_index": game.index,
            "player_color": player_color,
            "result": game.record.result,
            "cached": cached,
            "plies_analyzed": len(game.moves),
            "mistake_threshold_cp": self._engine.threshold_cp if self._engine else None,
            "player_mistake_candidates": sum(1 for m in flagged if m.mover_color == player_color),
            "opponent_mistake_candidates": sum(1 for m in flagged if m.mover_color != player_color),
            "mistake_candidates": rows,
            "truncated": len(flagged) > MAX_ROWS,
        }

    def evaluate_position(self, moves=None, game_index: int | None = None, after_ply: int | None = None) -> dict:
        """Engine eval and best move for a position given as a move list, optionally after a game's first N plies."""
        applied: list[str] = []
        if game_index is not None:
            game = self._game(game_index)
            if after_ply is None:
                raise ValueError("after_ply is required when game_index is given")
            if not isinstance(after_ply, int) or not 0 <= after_ply <= len(game.record.moves_san):
                raise ValueError(f"after_ply must be an integer between 0 and {len(game.record.moves_san)} for game {game_index}")
            applied += game.record.moves_san[:after_ply]
        elif after_ply is not None:
            raise ValueError("after_ply only applies together with game_index")
        elif moves is None:
            raise ValueError("give `moves`, or `game_index` with `after_ply`")
        applied += normalize_line(moves)

        board = chess.Board()
        for ply, san in enumerate(applied, start=1):
            try:
                board.push(board.parse_san(san))
            except ValueError as exc:
                raise ValueError(f"illegal or unparseable move {san!r} at ply {ply}: {exc}") from exc
        if board.is_game_over():
            raise ValueError(f"position is already game over ({board.result()})")

        key = board.epd()
        cached = key in self._position_cache
        if not cached:
            fact = self._require_engine().evaluate_board(board)
            self._position_cache[key] = {
                "side_to_move": fact.side_to_move,
                "eval_cp_side_to_move": fact.eval_cp_side_to_move,
                "eval_cp_white": fact.eval_cp_white,
                "engine_best_move_san": fact.engine_best_move_san,
                "pv_san": fact.pv_san,
            }
        return {
            **self._position_cache[key],
            "fen": board.fen(),
            "depth": ANALYSIS_DEPTH,
            "plies_applied": len(applied),
            "cached": cached,
        }

    # ---- helpers -----------------------------------------------------------------

    def _game(self, game_index) -> GameFacts:
        if not isinstance(game_index, int) or isinstance(game_index, bool):
            raise ValueError("game_index must be an integer")
        if not 0 <= game_index < len(self._games):
            raise ValueError(f"game_index {game_index} out of range (0..{len(self._games) - 1})")
        return self._games[game_index]

    def _require_engine(self) -> StockfishSession:
        if self._engine is None:
            raise ValueError("engine unavailable in this run")
        return self._engine


def _move_fact_dict(m: MoveFact) -> dict:
    return {
        "move_number": m.move_number,
        "mover_color": m.mover_color,
        "san": m.san,
        "eval_before_cp": m.eval_before_cp,
        "eval_after_cp": m.eval_after_cp,
        "eval_swing_cp": m.eval_swing_cp,
        "engine_best_move_san": m.engine_best_move_san,
        "is_mistake_candidate": m.is_mistake_candidate,
    }


COLOR_ARG = "'white' or 'black': the color the player had in the games to look at."
MIN_GAMES_ARG = "int, optional, default 1: groups with fewer games are left out of rows but counted in the *_below_min_games fields."
LINE_NOTE = "SAN moves from move 1, as a list (['e4','e5','Nf3']) or a string ('1. e4 e5 2. Nf3'). Matching is by move order, so transpositions are not merged."

TOOL_SCHEMA = {
    "get_player_profile": {
        "description": "Data volume and overall record: games loaded per color, W/D/L counts, time classes, rating range, how many games already have engine analysis. Counts only.",
        "args": {},
    },
    "list_games": {
        "description": f"One row per game with metadata, ECO code, opening name, total plies and first six plies (also as `first_moves_annotated`, each move tagged player or opponent). No engine. game_index 0 is the newest game. Rows are capped at {MAX_ROWS}; check `truncated` and page with offset.",
        "args": {
            "color": "'white' or 'black', optional: only games where the player had that color.",
            "offset": "int, optional, default 0: rows to skip.",
            "limit": f"int, optional, default {MAX_ROWS}, max {MAX_ROWS}.",
        },
    },
    "get_game_moves": {
        "description": f"SAN moves of one game by ply (1-based), with remaining clock after each move when Chess.com recorded it, and engine fields on plies of games already analyzed. At most {opening_facts.MAX_PLIES_PER_CALL} plies per call; check `truncated`.",
        "args": {
            "game_index": "int, required.",
            "from_ply": "int, optional, default 1.",
            "to_ply": "int, optional, default end of game.",
        },
    },
    "opening_sequences": {
        "description": f"Groups the player's games of one color by their first N plies and reports games, W/D/L, score (wins + half draws over games), example game indexes and ECO codes per group. Each row has `line_annotated`, `player_moves` and `opponent_moves` so you can tell whose move is whose (the player's color is `player_color`). Rows capped at {MAX_ROWS}; check `truncated`.",
        "args": {
            "color": COLOR_ARG,
            "depth_plies": f"int, optional, default 6, 1..{opening_facts.MAX_DEPTH_PLIES}: how many plies from move 1 define a group.",
            "min_games": MIN_GAMES_ARG,
            "perspective": "'full_line' (default): group by both sides' moves. 'player_moves_only': group by only the player's own moves in the window, merging different opponent replies.",
        },
    },
    "move_distribution": {
        "description": "For games of one color that start with a given move sequence, counts which move was played next, who played it (`played_by`: player or opponent), and how those games ended. Rows carry `line_annotated`.",
        "args": {
            "color": COLOR_ARG,
            "prefix": f"required; an empty list means the first move of the game. {LINE_NOTE}",
            "min_games": MIN_GAMES_ARG,
        },
    },
    "departure_points": {
        "description": "Compares every game of one color against a reference line and reports the first ply where each game left it, who left it (`departed_by`: player or opponent), the move played instead, the annotated line up to that move, and W/D/L for those games. Also counts games that followed the whole line or ended inside it.",
        "args": {
            "color": COLOR_ARG,
            "line": f"required, at least one move. {LINE_NOTE}",
            "min_games": MIN_GAMES_ARG,
        },
    },
    "get_style_measurements": {
        "description": "Raw measurements per game and aggregated per color: game length, castling side and ply for each side, captures by move 20, queens left after move 20, queen moves in the player's first 10 moves; plus mean eval swing per move-number bucket for games already engine-analyzed. Numbers only, no labels.",
        "args": {"color": "'white' or 'black', optional: limit to games where the player had that color."},
    },
    "analyze_game": {
        "description": "Runs Stockfish (fixed depth) over every ply of one game and returns the moves whose eval swing met the run's fixed centipawn threshold. Slow; the result is cached on the game, so asking again is free.",
        "args": {"game_index": "int, required."},
    },
    "evaluate_position": {
        "description": "Stockfish eval (centipawns, from the side to move and from White's view), best move and a short principal variation for one position at fixed depth. Cached per position. Position = `moves` from the start, or the first `after_ply` plies of a game, optionally followed by `moves`.",
        "args": {
            "moves": f"list or string, optional: {LINE_NOTE}",
            "game_index": "int, optional: start from this game's moves.",
            "after_ply": "int, required with game_index: how many plies of that game to play first (0 = start position).",
        },
    },
}

# tool name -> required argument names; every tool is a FactsStore method of the same name.
_REQUIRED_ARGS = {
    "get_player_profile": (),
    "list_games": (),
    "get_game_moves": ("game_index",),
    "opening_sequences": ("color",),
    "move_distribution": ("color", "prefix"),
    "departure_points": ("color", "line"),
    "get_style_measurements": (),
    "analyze_game": ("game_index",),
    "evaluate_position": (),
}


def call_tool(store: FactsStore, name: str, args: dict):
    """Single router. Raises ValueError for unknown tools or bad arguments."""
    if name not in TOOL_SCHEMA:
        raise ValueError(f"Unknown tool: {name}. Available: {sorted(TOOL_SCHEMA)}")
    if not isinstance(args, dict):
        raise ValueError("args must be a JSON object")

    missing = [a for a in _REQUIRED_ARGS[name] if a not in args]
    if missing:
        raise ValueError(f"Missing required argument(s) for {name}: {missing}")
    allowed = set(TOOL_SCHEMA[name]["args"])
    unexpected = sorted(set(args) - allowed)
    if unexpected:
        raise ValueError(f"Unexpected argument(s) for {name}: {unexpected}. Allowed: {sorted(allowed)}")
    return getattr(store, name)(**args)

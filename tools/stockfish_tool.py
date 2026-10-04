"""Facts-only tool: run a game through Stockfish and report per-move numbers.

No tool in this module decides what a mistake *means*. It only measures
centipawn swings against a documented threshold and reports the engine's
best move. Interpretation (which mistake matters, why) is the agent's job.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

# A 1.0 pawn swing flags a move as a mistake candidate. Fixed for the whole run
# (set once from the CLI --threshold) so every game is measured with the same ruler.
MISTAKE_THRESHOLD_CP = 100
ANALYSIS_DEPTH = 14  # fixed engine depth: same effort for every position, no judgment
MATE_SCORE_CP = 10000  # large finite stand-in so mate scores sort/compare sanely


@dataclass
class MoveFact:
    move_number: int
    mover_color: str  # "white" | "black"
    san: str
    eval_before_cp: int
    eval_after_cp: int
    eval_swing_cp: int  # positive = the mover lost this many centipawns
    engine_best_move_san: str
    is_mistake_candidate: bool


class StockfishSession:
    """One lazily started Stockfish process shared by every on-demand engine call in a run."""

    def __init__(self, engine_path: str, threshold_cp: int = MISTAKE_THRESHOLD_CP):
        self.engine_path = engine_path
        self.threshold_cp = threshold_cp
        self._engine: chess.engine.SimpleEngine | None = None

    def _get_engine(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def analyze_game(self, pgn_text: str) -> list[MoveFact]:
        return analyze_game(pgn_text, self.engine_path, self.threshold_cp, engine=self._get_engine())

    def evaluate_board(self, board: chess.Board, pv_plies: int = 6) -> PositionFact:
        return evaluate_board(self._get_engine(), board, pv_plies)


@dataclass
class PositionFact:
    side_to_move: str  # "white" | "black"
    eval_cp_side_to_move: int
    eval_cp_white: int
    engine_best_move_san: str
    pv_san: list[str]  # engine's principal variation from this position


def analyze_game(
    pgn_text: str,
    engine_path: str,
    threshold_cp: int = MISTAKE_THRESHOLD_CP,
    engine: chess.engine.SimpleEngine | None = None,
) -> list[MoveFact]:
    """Return per-move facts for every ply in the game. Pure measurement, no verdicts."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return []

    if engine is not None:
        return _analyze_with_engine(game, engine, threshold_cp)
    with chess.engine.SimpleEngine.popen_uci(engine_path) as owned_engine:
        return _analyze_with_engine(game, owned_engine, threshold_cp)


def _analyze_with_engine(
    game: chess.pgn.Game, engine: chess.engine.SimpleEngine, threshold_cp: int
) -> list[MoveFact]:
    facts: list[MoveFact] = []
    board = game.board()
    for ply_index, move in enumerate(game.mainline_moves()):
        mover_color = "white" if board.turn == chess.WHITE else "black"
        move_number = ply_index // 2 + 1

        eval_before_cp = _score_cp(engine, board)
        best_move = engine.play(board, chess.engine.Limit(depth=ANALYSIS_DEPTH)).move
        best_move_san = board.san(best_move) if best_move else "n/a"

        san = board.san(move)
        board.push(move)

        # After the move it's the opponent's turn; negate to keep the mover's perspective.
        eval_after_cp = -_score_cp(engine, board)
        swing = eval_before_cp - eval_after_cp

        facts.append(
            MoveFact(
                move_number=move_number,
                mover_color=mover_color,
                san=san,
                eval_before_cp=eval_before_cp,
                eval_after_cp=eval_after_cp,
                eval_swing_cp=swing,
                engine_best_move_san=best_move_san,
                is_mistake_candidate=swing >= threshold_cp,
            )
        )
    return facts


def evaluate_board(engine: chess.engine.SimpleEngine, board: chess.Board, pv_plies: int = 6) -> PositionFact:
    """Eval and best move for one position at the fixed depth. No judgment about the result."""
    info = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
    side_cp = info["score"].relative.score(mate_score=MATE_SCORE_CP)
    white_cp = side_cp if board.turn == chess.WHITE else -side_cp

    pv_san: list[str] = []
    walker = board.copy()
    for move in info.get("pv", [])[:pv_plies]:
        pv_san.append(walker.san(move))
        walker.push(move)

    return PositionFact(
        side_to_move="white" if board.turn == chess.WHITE else "black",
        eval_cp_side_to_move=side_cp,
        eval_cp_white=white_cp,
        engine_best_move_san=pv_san[0] if pv_san else "n/a",
        pv_san=pv_san,
    )


def _score_cp(engine: chess.engine.SimpleEngine, board: chess.Board) -> int:
    """Evaluation in centipawns from the perspective of the side to move."""
    info = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
    score = info["score"].relative
    return score.score(mate_score=MATE_SCORE_CP)

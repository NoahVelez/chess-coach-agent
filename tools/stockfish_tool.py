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

MISTAKE_THRESHOLD_CP = 100  # a 1.0 pawn swing flags a move as a mistake candidate
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


def analyze_game(pgn_text: str, engine_path: str, threshold_cp: int = MISTAKE_THRESHOLD_CP) -> list[MoveFact]:
    """Return per-move facts for every ply in the game. Pure measurement, no verdicts."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return []

    facts: list[MoveFact] = []
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
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


def _score_cp(engine: chess.engine.SimpleEngine, board: chess.Board) -> int:
    """Evaluation in centipawns from the perspective of the side to move."""
    info = engine.analyse(board, chess.engine.Limit(depth=ANALYSIS_DEPTH))
    score = info["score"].relative
    return score.score(mate_score=MATE_SCORE_CP)

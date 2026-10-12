import unittest

from tests.fixtures import SAMPLE_GAMES, make_record, two_ply_games
from tools import opening_facts as of
from tools import style_facts as sf
from tools.stockfish_tool import MoveFact

KNIGHT_SHUFFLE_40 = ["Nf3", "Nf6", "Ng1", "Ng8"] * 10
EARLY_QUEEN = ["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"]
KINGSIDE = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "O-O", "Nf6"]
BOTH_QUEENSIDE = ["d4", "d5", "Nc3", "Nc6", "Bf4", "Bf5", "Qd2", "Qd7", "O-O-O", "O-O-O"]


class MeasureGameTests(unittest.TestCase):
    def test_early_queen_move_and_capture_counts(self):
        row = sf.measure_game(make_record("white", EARLY_QUEEN, "win"), 3)
        self.assertEqual(row["game_index"], 3)
        self.assertEqual(row["player_first_queen_move_ply"], 3)
        self.assertEqual(row["player_queen_moves_in_first_10_moves"], 2)
        self.assertEqual(row["captures_by_move_20"], {"player": 1, "opponent": 0})
        self.assertIsNone(row["queens_on_board_after_move_20"])
        self.assertIsNone(row["player_castled"])

    def test_castling_sides_and_plies(self):
        row = sf.measure_game(make_record("white", KINGSIDE), 0)
        self.assertEqual(row["player_castled"], {"side": "kingside", "ply": 7})
        self.assertIsNone(row["opponent_castled"])

        black = sf.measure_game(make_record("black", BOTH_QUEENSIDE), 0)
        self.assertEqual(black["player_castled"], {"side": "queenside", "ply": 10})
        self.assertEqual(black["opponent_castled"], {"side": "queenside", "ply": 9})

    def test_queens_counted_after_move_20(self):
        row = sf.measure_game(make_record("white", KNIGHT_SHUFFLE_40), 0)
        self.assertEqual(row["queens_on_board_after_move_20"], 2)
        self.assertEqual(row["total_plies"], 40)


class StyleMeasurementsTests(unittest.TestCase):
    def test_aggregates_by_color_hold_counts_not_labels(self):
        games = [
            make_record("white", EARLY_QUEEN),
            make_record("white", KINGSIDE),
            make_record("black", BOTH_QUEENSIDE),
        ]
        result = sf.style_measurements(games)
        white = result["by_color"]["white"]
        self.assertEqual(white["games"], 2)
        self.assertEqual(white["player_castling"]["kingside"], 1)
        self.assertEqual(white["player_castling"]["never"], 1)
        self.assertEqual(white["games_with_player_queen_move_by_move_10"], 1)
        self.assertEqual(white["games_ending_before_move_20"], 2)
        self.assertEqual(result["by_color"]["black"]["player_castling"]["queenside"], 1)
        self.assertFalse(result["truncated"])

    def test_color_filter_and_empty(self):
        only_black = sf.style_measurements(SAMPLE_GAMES, color="black")
        self.assertEqual(list(only_black["by_color"]), ["black"])
        self.assertEqual(len(only_black["rows"]), 2)
        empty = sf.style_measurements([])
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["by_color"]["white"]["games"], 0)
        self.assertIsNone(empty["by_color"]["white"]["mean_total_plies"])

    def test_truncation_flag(self):
        result = sf.style_measurements(two_ply_games(40))
        self.assertEqual(len(result["rows"]), of.MAX_ROWS)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["by_color"]["white"]["games"], 40)

    def test_bad_color_raises(self):
        with self.assertRaises(ValueError):
            sf.style_measurements(SAMPLE_GAMES, color="grey")


def fact(move_number, mover_color, swing, mistake=False):
    return MoveFact(move_number, mover_color, "x", 0, -swing, swing, "y", mistake)


class EvalSwingByPhaseTests(unittest.TestCase):
    def test_buckets_by_move_number_and_side(self):
        moves = [
            fact(2, "white", 10),
            fact(2, "black", 30),
            fact(15, "white", 200, True),
            fact(40, "black", 0),
        ]
        result = sf.eval_swing_by_phase([("white", moves)])
        self.assertEqual(result["analyzed_games"], 1)
        early = result["by_phase"]["moves_1_10"]
        self.assertEqual(early["player"]["mean_eval_swing_cp"], 10)
        self.assertEqual(early["opponent"]["mean_eval_swing_cp"], 30)
        mid = result["by_phase"]["moves_11_30"]
        self.assertEqual(mid["player"]["mistake_candidates"], 1)
        self.assertEqual(mid["opponent"]["moves"], 0)
        self.assertIsNone(mid["opponent"]["mean_eval_swing_cp"])
        self.assertEqual(result["by_phase"]["moves_31_plus"]["opponent"]["moves"], 1)

    def test_no_analyzed_games(self):
        result = sf.eval_swing_by_phase([])
        self.assertEqual(result["analyzed_games"], 0)
        self.assertEqual(result["by_phase"]["moves_1_10"]["player"]["moves"], 0)


if __name__ == "__main__":
    unittest.main()

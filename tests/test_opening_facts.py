import unittest

from tests.fixtures import RUY_MAIN, SAMPLE_GAMES, branching_games, make_record, two_ply_games
from tools import opening_facts as of


class NormalizeTests(unittest.TestCase):
    def test_accepts_string_with_move_numbers_and_check_marks(self):
        self.assertEqual(of.normalize_line("1. e4 e5 2.Nf3 Nc6 3. Bb5+"), ["e4", "e5", "Nf3", "Nc6", "Bb5"])

    def test_accepts_list_and_none(self):
        self.assertEqual(of.normalize_line(["e4", "e5"]), ["e4", "e5"])
        self.assertEqual(of.normalize_line(None), [])


class ListGamesTests(unittest.TestCase):
    def test_rows_carry_opening_facts_without_engine(self):
        result = of.list_games(SAMPLE_GAMES)
        self.assertEqual(result["games_matching"], 6)
        self.assertFalse(result["truncated"])
        first = result["rows"][0]
        self.assertEqual(first["eco"], "C60")
        self.assertEqual(first["opening_name"], "Ruy Lopez")
        self.assertEqual(first["first_moves"], ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"])

    def test_color_filter_and_empty_result(self):
        self.assertEqual(of.list_games(SAMPLE_GAMES, color="black")["games_matching"], 2)
        empty = of.list_games([], color="white")
        self.assertEqual(empty["rows"], [])
        self.assertFalse(empty["truncated"])

    def test_truncation_flag_and_offset(self):
        games = two_ply_games(40)
        page = of.list_games(games)
        self.assertEqual(len(page["rows"]), of.MAX_ROWS)
        self.assertTrue(page["truncated"])
        rest = of.list_games(games, offset=of.MAX_ROWS)
        self.assertEqual(len(rest["rows"]), 40 - of.MAX_ROWS)
        self.assertFalse(rest["truncated"])
        self.assertEqual(rest["rows"][0]["game_index"], of.MAX_ROWS)


class GetGameMovesTests(unittest.TestCase):
    def test_returns_requested_window(self):
        result = of.get_game_moves(SAMPLE_GAMES[0], 0, from_ply=3, to_ply=4)
        self.assertEqual([p["san"] for p in result["plies"]], ["Nf3", "Nc6"])
        self.assertEqual(result["plies"][0]["mover"], "player")
        self.assertEqual(result["plies"][1]["mover"], "opponent")
        self.assertFalse(result["truncated"])

    def test_long_game_is_truncated(self):
        shuffle = ["Nf3", "Nf6", "Ng1", "Ng8"] * 20
        game = make_record("white", shuffle)
        result = of.get_game_moves(game, 0)
        self.assertEqual(len(result["plies"]), of.MAX_PLIES_PER_CALL)
        self.assertTrue(result["truncated"])


class OpeningSequencesTests(unittest.TestCase):
    def test_groups_by_full_line_with_counts_and_score(self):
        result = of.opening_sequences(SAMPLE_GAMES, "white", depth_plies=6)
        rows = {tuple(r["sequence"]): r for r in result["rows"]}
        self.assertEqual(len(rows), 4)
        self.assertEqual(result["games_of_color"], 4)
        sicilian = rows[tuple(["e4", "c5", "Nf3", "d6", "d4", "cxd4"])]
        self.assertEqual((sicilian["draws"], sicilian["score"]), (1, 0.5))

    def test_player_moves_only_merges_opponent_replies(self):
        result = of.opening_sequences(SAMPLE_GAMES, "white", depth_plies=5, perspective="player_moves_only")
        top = result["rows"][0]
        self.assertEqual(top["sequence"], ["e4", "Nf3", "Bb5"])
        self.assertEqual(top["games"], 2)
        self.assertEqual(top["wins"], 1)
        self.assertEqual(top["losses"], 1)
        self.assertEqual(top["game_indexes"], [0, 1])

    def test_min_games_hides_small_groups_but_reports_them(self):
        result = of.opening_sequences(SAMPLE_GAMES, "white", depth_plies=6, min_games=2)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["groups_below_min_games"], 4)
        self.assertEqual(result["games_in_groups_below_min_games"], 4)

    def test_games_shorter_than_depth_are_counted(self):
        result = of.opening_sequences(SAMPLE_GAMES, "black", depth_plies=6)
        self.assertEqual(result["games_shorter_than_depth"], 1)
        self.assertEqual(len(result["rows"]), 1)

    def test_empty_when_no_games_of_color(self):
        result = of.opening_sequences([SAMPLE_GAMES[0]], "black", depth_plies=4)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["games_of_color"], 0)
        self.assertFalse(result["truncated"])

    def test_truncation_flag(self):
        result = of.opening_sequences(two_ply_games(40), "white", depth_plies=2)
        self.assertEqual(len(result["rows"]), of.MAX_ROWS)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["groups_total"], 40)

    def test_bad_arguments_raise(self):
        with self.assertRaises(ValueError):
            of.opening_sequences(SAMPLE_GAMES, "green")
        with self.assertRaises(ValueError):
            of.opening_sequences(SAMPLE_GAMES, "white", depth_plies=0)
        with self.assertRaises(ValueError):
            of.opening_sequences(SAMPLE_GAMES, "white", depth_plies=of.MAX_DEPTH_PLIES + 1)
        with self.assertRaises(ValueError):
            of.opening_sequences(SAMPLE_GAMES, "white", min_games=0)
        with self.assertRaises(ValueError):
            of.opening_sequences(SAMPLE_GAMES, "white", perspective="vibes")


class SideAttributionTests(unittest.TestCase):
    def test_annotate_line_tags_each_move_for_both_colors(self):
        self.assertEqual(of.annotate_line("white", ["e4", "c6", "d4"]), "1.e4(player) c6(opponent) 2.d4(player)")
        self.assertEqual(of.annotate_line("black", ["e4", "c6"]), "1.e4(opponent) c6(player)")
        self.assertEqual(of.annotate_line("white", []), "")

    def test_opening_rows_separate_player_and_opponent_moves(self):
        games = [make_record("white", ["e4", "c6", "d4", "d5"], "loss")]
        row = of.opening_sequences(games, "white", 4)["rows"][0]
        self.assertEqual(row["player_color"], "white")
        self.assertEqual(row["player_moves"], ["e4", "d4"])
        self.assertEqual(row["opponent_moves"], ["c6", "d5"])
        self.assertIn("c6(opponent)", row["line_annotated"])

    def test_player_moves_only_does_not_claim_opponent_moves(self):
        row = of.opening_sequences(SAMPLE_GAMES, "white", 4, perspective="player_moves_only")["rows"][0]
        self.assertNotIn("line_annotated", row)
        self.assertIsInstance(row["opponent_moves"], str)

    def test_distribution_and_departure_rows_name_the_mover(self):
        dist = of.move_distribution(SAMPLE_GAMES, "white", ["e4"])
        self.assertEqual({r["played_by"] for r in dist["rows"]}, {"opponent"})
        self.assertEqual(dist["prefix_annotated"], "1.e4(player)")
        dep = of.departure_points(SAMPLE_GAMES, "white", RUY_MAIN)
        row = next(r for r in dep["rows"] if r["move_played"] == "Nf6")
        self.assertEqual(row["line_annotated"], "1.e4(player) e5(opponent) 2.Nf3(player) Nc6(opponent) 3.Bb5(player) Nf6(opponent)")
        self.assertEqual(row["player_color"], "white")

    def test_list_games_first_moves_annotated(self):
        row = of.list_games(SAMPLE_GAMES, color="black")["rows"][0]
        self.assertTrue(row["first_moves_annotated"].startswith("1.d4(opponent) d5(player)"))


class MoveDistributionTests(unittest.TestCase):
    def test_player_move_after_prefix(self):
        result = of.move_distribution(SAMPLE_GAMES, "white", ["e4", "e5", "Nf3", "Nc6"])
        self.assertEqual(result["next_mover"], "player")
        self.assertEqual(result["games_matching_prefix"], 3)
        moves = {r["next_move"]: r for r in result["rows"]}
        self.assertEqual(moves["Bb5"]["games"], 2)
        self.assertEqual(moves["Bc4"]["games"], 1)
        self.assertEqual(result["rows"][0]["next_move"], "Bb5")

    def test_opponent_move_after_prefix_as_string(self):
        result = of.move_distribution(SAMPLE_GAMES, "white", "1. e4")
        self.assertEqual(result["next_mover"], "opponent")
        moves = {r["next_move"]: r["games"] for r in result["rows"]}
        self.assertEqual(moves, {"e5": 3, "c5": 1})

    def test_empty_prefix_gives_first_moves(self):
        result = of.move_distribution(SAMPLE_GAMES, "black", [])
        self.assertEqual(result["next_mover"], "opponent")
        self.assertEqual({r["next_move"] for r in result["rows"]}, {"d4"})

    def test_no_match_and_games_ending_at_prefix(self):
        none = of.move_distribution(SAMPLE_GAMES, "white", ["d4"])
        self.assertEqual(none["rows"], [])
        self.assertEqual(none["games_matching_prefix"], 0)
        ends = of.move_distribution(SAMPLE_GAMES, "black", ["d4", "Nf6", "c4", "e6"])
        self.assertEqual(ends["games_ending_at_prefix"], 1)
        self.assertEqual(ends["rows"], [])

    def test_min_games_and_truncation(self):
        result = of.move_distribution(SAMPLE_GAMES, "white", ["e4", "e5", "Nf3", "Nc6"], min_games=2)
        self.assertEqual([r["next_move"] for r in result["rows"]], ["Bb5"])
        self.assertEqual(result["moves_below_min_games"], 1)

        wide = of.move_distribution(branching_games(["e4", "e5"]), "white", ["e4", "e5"])
        self.assertEqual(len(wide["rows"]), of.MAX_ROWS)
        self.assertTrue(wide["truncated"])
        narrow = of.move_distribution(two_ply_games(400), "white", ["a3"])
        self.assertEqual(len(narrow["rows"]), 20)
        self.assertFalse(narrow["truncated"])


class DepartureTests(unittest.TestCase):
    def test_who_left_the_line_and_where(self):
        result = of.departure_points(SAMPLE_GAMES, "white", RUY_MAIN)
        self.assertEqual(result["followed_whole_line"]["games"], 1)
        self.assertEqual(result["departed_by_opponent"]["games"], 2)
        self.assertEqual(result["departed_by_player"]["games"], 1)
        rows = {(r["ply"], r["departed_by"], r["move_played"]): r for r in result["rows"]}
        nf6 = rows[(6, "opponent", "Nf6")]
        self.assertEqual(nf6["reference_move"], "a6")
        self.assertEqual(nf6["losses"], 1)
        self.assertEqual(nf6["move_number"], 3)
        self.assertEqual(rows[(5, "player", "Bc4")]["game_indexes"], [3])
        self.assertIn((2, "opponent", "c5"), rows)

    def test_games_ending_inside_line(self):
        result = of.departure_points(SAMPLE_GAMES, "black", ["d4", "Nf6", "c4", "e6", "Nc3"])
        self.assertEqual(result["ended_inside_line"], 1)
        self.assertEqual(result["followed_whole_line"]["games"], 0)
        self.assertEqual(result["followed_whole_line"]["score"], None)

    def test_empty_and_invalid(self):
        empty = of.departure_points([], "white", ["e4"])
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["games_of_color"], 0)
        with self.assertRaises(ValueError):
            of.departure_points(SAMPLE_GAMES, "white", [])

    def test_min_games_and_truncation(self):
        result = of.departure_points(SAMPLE_GAMES, "white", RUY_MAIN, min_games=2)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["departure_groups_below_min_games"], 3)

        games = two_ply_games(400)
        narrow = of.departure_points(games, "white", ["e4"])
        self.assertEqual(len(narrow["rows"]), 19)
        self.assertFalse(narrow["truncated"])
        wide = of.departure_points(games, "white", ["a3", "a5"])
        self.assertEqual(len(wide["rows"]), of.MAX_ROWS)
        self.assertTrue(wide["truncated"])


if __name__ == "__main__":
    unittest.main()

import unittest

from tools.chess_com import GameRecord, _to_game_record, parse_pgn_facts

PGN = """[Event "Live Chess"]
[White "me"]
[Black "them"]
[ECO "B12"]
[ECOUrl "https://www.chess.com/openings/Caro-Kann-Defense-Advance-Variation-3...c5"]
[TimeControl "600"]
[Termination "them won by resignation"]

1. e4 {[%clk 0:09:58.3]} 1... c6 {[%clk 0:09:57.1]} 2. d4 {[%clk 0:09:55]} 2... d5 {[%clk 0:09:50.9]} 3. e5 {[%clk 0:09:40]} 3... Bf5 {[%clk 0:09:30]} 0-1
"""


class ParsePgnFactsTests(unittest.TestCase):
    def test_reads_opening_headers_moves_and_clocks(self):
        facts = parse_pgn_facts(PGN)
        self.assertEqual(facts["eco"], "B12")
        self.assertEqual(facts["opening_name"], "Caro Kann Defense Advance Variation")
        self.assertEqual(facts["moves_san"], ["e4", "c6", "d4", "d5", "e5", "Bf5"])
        self.assertEqual(facts["termination"], "them won by resignation")
        self.assertEqual(facts["time_control"], "600")
        self.assertAlmostEqual(facts["clocks_sec"][0], 598.3)
        self.assertAlmostEqual(facts["clocks_sec"][3], 590.9)

    def test_missing_headers_and_clocks_are_none(self):
        facts = parse_pgn_facts("1. e4 e5 *")
        self.assertIsNone(facts["eco"])
        self.assertIsNone(facts["opening_name"])
        self.assertEqual(facts["clocks_sec"], [None, None])

    def test_empty_pgn_gives_no_facts(self):
        self.assertEqual(parse_pgn_facts(""), {})

    def test_record_built_from_raw_api_game(self):
        raw = {
            "pgn": PGN,
            "end_time": 5,
            "time_class": "rapid",
            "white": {"username": "Me", "rating": 1100, "result": "resigned"},
            "black": {"username": "them", "rating": 1150, "result": "win"},
        }
        record = _to_game_record(raw, "me")
        self.assertIsInstance(record, GameRecord)
        self.assertEqual(record.player_color, "white")
        self.assertEqual(record.outcome, "loss")
        self.assertEqual(record.eco, "B12")
        self.assertEqual(len(record.moves_san), 6)

    def test_outcome_classification(self):
        def outcome(result):
            return GameRecord("", 0, "rapid", "white", 0, "o", 0, result).outcome

        self.assertEqual(outcome("win"), "win")
        self.assertEqual(outcome("agreed"), "draw")
        self.assertEqual(outcome("stalemate"), "draw")
        self.assertEqual(outcome("timeout"), "loss")


if __name__ == "__main__":
    unittest.main()

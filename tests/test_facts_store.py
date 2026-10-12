import json
import unittest

from agent.facts_store import TOOL_SCHEMA, FactsStore, GameFacts, call_tool
from tests.fixtures import SAMPLE_GAMES, two_ply_games
from tools.chess_com import parse_pgn_facts
from tools.stockfish_tool import PositionFact, MoveFact


class FakeEngine:
    """Stands in for StockfishSession: counts calls, flags every white move 3 as a mistake."""

    threshold_cp = 100

    def __init__(self):
        self.analyze_calls = 0
        self.evaluate_calls = 0

    def analyze_game(self, pgn):
        self.analyze_calls += 1
        sans = parse_pgn_facts(pgn)["moves_san"]
        return [
            MoveFact(i // 2 + 1, "white" if i % 2 == 0 else "black", san, 10, 0, 150 if i == 4 else 10, "Nf3", i == 4)
            for i, san in enumerate(sans)
        ]

    def evaluate_board(self, board, pv_plies=6):
        self.evaluate_calls += 1
        return PositionFact("white" if board.turn else "black", 25, 25 if board.turn else -25, "Nf3", ["Nf3", "Nc6"])

    def close(self):
        self.closed = True


def make_store(records=SAMPLE_GAMES, engine=None):
    return FactsStore([GameFacts(i, r) for i, r in enumerate(records)], engine)


class RouterTests(unittest.TestCase):
    def test_every_schema_tool_is_routable_and_json_serializable(self):
        store = make_store(engine=FakeEngine())
        calls = {
            "get_player_profile": {},
            "list_games": {},
            "get_game_moves": {"game_index": 0},
            "opening_sequences": {"color": "white"},
            "move_distribution": {"color": "white", "prefix": ["e4"]},
            "departure_points": {"color": "white", "line": "1. e4 e5"},
            "get_style_measurements": {},
            "analyze_game": {"game_index": 0},
            "evaluate_position": {"moves": ["e4"]},
        }
        self.assertEqual(set(calls), set(TOOL_SCHEMA))
        for name, args in calls.items():
            json.dumps(call_tool(store, name, args))

    def test_unknown_tool_missing_and_unexpected_args_raise(self):
        store = make_store()
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            call_tool(store, "recommend_opening", {})
        with self.assertRaisesRegex(ValueError, "Missing required"):
            call_tool(store, "opening_sequences", {})
        with self.assertRaisesRegex(ValueError, "Unexpected argument"):
            call_tool(store, "list_games", {"colour": "white"})
        with self.assertRaisesRegex(ValueError, "JSON object"):
            call_tool(store, "list_games", [])

    def test_bad_game_index_and_color(self):
        store = make_store()
        for bad in (-1, 99, "0", True):
            with self.assertRaises(ValueError):
                store.get_game_moves(bad)
        with self.assertRaises(ValueError):
            store.list_games(color="green")


class ProfileTests(unittest.TestCase):
    def test_counts(self):
        profile = make_store().get_player_profile()
        self.assertEqual(profile["games_loaded"], 6)
        self.assertEqual(profile["games_as_white"], 4)
        self.assertEqual(profile["record_as_white"]["wins"], 2)
        self.assertEqual(profile["games_with_engine_analysis"], 0)

    def test_empty_store(self):
        self.assertEqual(make_store([]).get_player_profile(), {"games_loaded": 0})


class EngineToolsTests(unittest.TestCase):
    def test_analyze_game_is_on_demand_and_cached(self):
        engine = FakeEngine()
        store = make_store(engine=engine)
        self.assertEqual(engine.analyze_calls, 0)
        first = store.analyze_game(0)
        second = store.analyze_game(0)
        self.assertEqual(engine.analyze_calls, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["player_mistake_candidates"], 1)
        row = first["mistake_candidates"][0]
        self.assertEqual((row["ply"], row["mover"], row["move_number"]), (5, "player", 3))
        self.assertEqual(store.get_player_profile()["games_with_engine_analysis"], 1)

    def test_analysis_shows_up_in_moves_list_and_phase_measurements(self):
        store = make_store(engine=FakeEngine())
        self.assertFalse(store.get_game_moves(0)["engine_analyzed"])
        store.analyze_game(0)
        moves = store.get_game_moves(0, from_ply=5, to_ply=5)
        self.assertTrue(moves["engine_analyzed"])
        self.assertTrue(moves["plies"][0]["is_mistake_candidate"])
        phases = store.get_style_measurements()["eval_swing_by_phase"]
        self.assertEqual(phases["analyzed_games"], 1)
        self.assertEqual(store.get_style_measurements(color="black")["eval_swing_by_phase"]["analyzed_games"], 0)

    def test_evaluate_position_caches_by_position(self):
        engine = FakeEngine()
        store = make_store(engine=engine)
        a = store.evaluate_position(moves=["e4", "e5"])
        b = store.evaluate_position(game_index=0, after_ply=2)  # same position, reached via a game
        self.assertFalse(a["cached"])
        self.assertTrue(b["cached"])
        self.assertEqual(engine.evaluate_calls, 1)
        self.assertEqual(a["engine_best_move_san"], "Nf3")
        c = store.evaluate_position(game_index=0, after_ply=2, moves="2. Nf3")
        self.assertEqual(c["plies_applied"], 3)
        self.assertEqual(engine.evaluate_calls, 2)

    def test_evaluate_position_errors(self):
        store = make_store(engine=FakeEngine())
        for kwargs in (
            {},
            {"game_index": 0},
            {"after_ply": 2},
            {"game_index": 0, "after_ply": 99},
            {"moves": ["e4", "e4"]},
            {"moves": ["f3", "e5", "g4", "Qh4#"]},
        ):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                store.evaluate_position(**kwargs)

    def test_engine_tools_report_when_engine_missing(self):
        store = make_store()
        with self.assertRaisesRegex(ValueError, "engine unavailable"):
            store.analyze_game(0)
        with self.assertRaisesRegex(ValueError, "engine unavailable"):
            store.evaluate_position(moves=["e4"])

    def test_analysis_truncation_flag(self):
        class ManyFlags(FakeEngine):
            def analyze_game(self, pgn):
                return [MoveFact(i // 2 + 1, "white" if i % 2 == 0 else "black", "x", 0, -200, 200, "y", True) for i in range(60)]

        store = make_store(two_ply_games(1), ManyFlags())
        result = store.analyze_game(0)
        self.assertEqual(len(result["mistake_candidates"]), 25)
        self.assertTrue(result["truncated"])


class SchemaTests(unittest.TestCase):
    def test_every_arg_of_every_method_is_described(self):
        import inspect

        for name, spec in TOOL_SCHEMA.items():
            params = set(inspect.signature(getattr(FactsStore, name)).parameters) - {"self"}
            self.assertEqual(params, set(spec["args"]), name)


if __name__ == "__main__":
    unittest.main()

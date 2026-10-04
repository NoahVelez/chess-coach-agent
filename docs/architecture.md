# Architecture

Three layers: `tools/` measures and counts, `agent/` routes tool calls and runs the model loop, `main.py` wires them together and writes the report. Interpretation lives only in the model.

## Modules

```mermaid
flowchart TD
    subgraph CLI["main.py"]
        M1["argparse, find_stockfish"]
        M2["build_header, write_report"]
    end
    subgraph AGENT["agent/"]
        L["loop.py<br/>run_coaching_agent"]
        F["facts_store.py<br/>FactsStore, TOOL_SCHEMA, call_tool"]
    end
    subgraph TOOLS["tools/ (facts only)"]
        C["chess_com.py<br/>fetch_recent_games, parse_pgn_facts"]
        O["opening_facts.py<br/>list, group, distribution, departure"]
        S["style_facts.py<br/>raw style measurements"]
        K["stockfish_tool.py<br/>StockfishSession, MoveFact"]
    end
    M1 --> C
    M1 --> L
    L --> F
    F --> O
    F --> S
    F --> K
    M2 --> L
    O --> C
    S --> C
    S --> K
```

| Module | Responsibility |
|--------|----------------|
| [main.py](../main.py) | CLI, loads games, creates the engine session and store, writes the single report |
| [agent/loop.py](../agent/loop.py) | Only code that calls OpenAI; checks turn shape, logs reasoning, caps turns |
| [agent/facts_store.py](../agent/facts_store.py) | Holds games, caches engine results, validates arguments, routes tool calls |
| [tools/chess_com.py](../tools/chess_com.py) | Chess.com API fetch and PGN parsing (headers, SAN moves, clocks) |
| [tools/opening_facts.py](../tools/opening_facts.py) | Counting/grouping over move lists |
| [tools/style_facts.py](../tools/style_facts.py) | Raw measurements a model can infer style from |
| [tools/stockfish_tool.py](../tools/stockfish_tool.py) | Fixed-depth engine measurements |

## Key types

```mermaid
classDiagram
    class GameRecord {
        pgn
        player_color
        result
        eco
        opening_name
        moves_san
        clocks_sec
        outcome
    }
    class GameFacts {
        index
        record
        moves
        analyzed
    }
    class MoveFact {
        move_number
        mover_color
        san
        eval_swing_cp
        engine_best_move_san
        is_mistake_candidate
    }
    class FactsStore {
        records
        analyze_game()
        evaluate_position()
        opening_sequences()
        close()
    }
    class StockfishSession {
        threshold_cp
        analyze_game()
        evaluate_board()
        close()
    }
    class AgentRun {
        report
        status
        turns_used
        model
        trail
    }
    GameFacts --> GameRecord
    GameFacts --> MoveFact
    FactsStore --> GameFacts
    FactsStore --> StockfishSession
```

## Facts vs. judgment

```mermaid
flowchart LR
    subgraph FACTS["Code: measures, counts, looks up"]
        A["Moves, ECO, clocks"]
        B["Counts, W/D/L, score"]
        C["Who left a line, at which ply"]
        D["Engine eval at fixed depth 14"]
    end
    subgraph JUDGE["Model: decides"]
        E["Which question next"]
        F["What a pattern means"]
        G["Ranking and recommendations"]
        H["What to reject or call too small"]
    end
    FACTS -->|"JSON tool results"| JUDGE
```

No tool ranks lines, names a style, or recommends anything, and there is no opening book or ECO-to-advice table.

## See also

- [agent-loop.md](agent-loop.md)
- [tools.md](tools.md)
- [design-decisions.md](design-decisions.md)
- [index.md](index.md)

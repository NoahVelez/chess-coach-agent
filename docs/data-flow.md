# Data Flow

From CLI input to one Markdown report: games are fetched once, everything else is computed on demand when the agent asks, and engine results are cached for the rest of the run.

## End to end

```mermaid
sequenceDiagram
    actor User
    participant CLI as main.py
    participant CC as Chess.com API
    participant FS as FactsStore
    participant AG as Agent loop
    participant LLM as OpenAI
    participant SF as Stockfish
    participant FSYS as Reports folder
    User->>CLI: python main.py USERNAME --games 40
    CLI->>CC: monthly archives (newest first)
    CC-->>CLI: games (PGN)
    CLI->>CLI: parse PGN facts, build GameFacts (no engine yet)
    CLI->>AG: run_coaching_agent(store, username)
    loop up to 20 turns
        AG->>LLM: conversation
        LLM-->>AG: tool turn with open_question, why_this_next, decision_so_far
        AG->>FS: call_tool(name, args)
        opt analyze_game or evaluate_position
            FS->>SF: depth-14 analysis (first request only)
            SF-->>FS: evals, best moves
        end
        FS-->>AG: facts or error
    end
    LLM-->>AG: first final (draft report)
    AG->>LLM: audit message
    LLM-->>AG: final (checked report body)
    AG-->>CLI: AgentRun
    CLI->>FSYS: header + report body, one new file
    CLI->>FSYS: full conversation to logs/ (gitignored)
    CLI-->>User: report path on stdout
```

## How facts are stored and reused

```mermaid
flowchart TD
    A["GameRecord<br/>PGN, SAN moves, ECO, clocks"] --> B["GameFacts.moves = None"]
    B -->|"analyze_game"| C["GameFacts.moves = MoveFact list"]
    C --> D["get_game_moves adds eval fields"]
    C --> E["get_style_measurements adds eval swing by phase"]
    F["evaluate_position"] --> G["position cache keyed by EPD"]
    G -->|"same position again"| H["free, cached: true"]
    C -->|"same game again"| H
    A --> I["aggregation tools recompute from moves each call<br/>(no engine, cheap)"]
```

## Report writing

```mermaid
flowchart TD
    A["AgentRun: report, status, turns_used, model"] --> B["build_header<br/>username, date, games, model, turns"]
    A --> C{"status"}
    C -->|"cap_reached"| D["Add Cap reached note"]
    C -->|"unparseable or model_error"| E["Add Incomplete run note;<br/>body is the reasoning trail"]
    C -->|"final"| F["No note"]
    B --> G["header + separator + body"]
    D --> G
    E --> G
    F --> G
    G --> H["write_report: reports/USERNAME_YYYYMMDD-HHMMSS.md<br/>exclusive create, never overwrites"]
```

The only code-generated part of the file is the short header. Section headings in the body are the model's. `reports/.gitkeep` keeps the folder in git; reports themselves are not ignored.

## See also

- [agent-loop.md](agent-loop.md)
- [tools.md](tools.md)
- [setup-and-usage.md](setup-and-usage.md)
- [index.md](index.md)

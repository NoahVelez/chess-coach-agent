# How the Chess Coach Agent Works

The chess coach turns a player's recent Chess.com games into a short, evidence-backed coaching report. It combines ordinary Python code, an AI model, and Stockfish, with a different job for each:

- **Python** collects game data, calculates facts, checks tool requests, and saves the report.
- **The AI model** decides what to investigate next and what the evidence means for the player.
- **Stockfish** evaluates moves and positions when the agent asks for chess-engine evidence.

This separation matters: a score or move count is a fact; deciding what the player should practice is a coaching judgment.

## From username to report

```mermaid
flowchart TD
    U["User enters Chess.com username"] --> P["Python fetches recent public rapid/blitz games"]
    P --> F["Python prepares game facts"]
    F --> A["Agent sends conversation to OpenAI API"]
    A --> D{"What should I investigate next?"}
    D --> T["Agent requests a facts tool"]
    T --> R["Python checks the request and returns facts"]
    R --> Q{"Need engine evidence?"}
    Q -->|"Yes"| S["Stockfish analyzes a game or position"]
    Q -->|"No"| C["Facts return to the agent"]
    S --> C
    C --> A
    D -->|"Enough evidence"| V["Agent drafts and self-audits its report"]
    V --> O["Python adds run details and saves one Markdown report"]
```

## How the agent investigates

Before analysis, Python fetches the player's recent public rapid and blitz games from the Chess.com API. It parses information such as moves, openings, game results, and player color. These game facts are available to the agent through tools.

The agent then calls the OpenAI API with the task, the conversation so far, and descriptions of the available tools. On each turn, the model chooses a question and either requests facts or finishes its report. It may, for example, compare opening choices, look at what happened after a familiar line changed, or ask Stockfish to evaluate a position. The next step depends on the answers it has already received; the investigation is not a fixed list of questions.

```mermaid
sequenceDiagram
    participant App as Python app
    participant Model as OpenAI model
    participant Tools as Facts tools
    participant Engine as Stockfish
    App->>Model: Task, conversation, and available tools
    loop Until report is ready or turn limit is reached
        Model-->>App: A question and requested tool, or a final report
        opt Model requested facts
            App->>Tools: Check and run the requested query
            opt Engine analysis was requested
                Tools->>Engine: Evaluate game or position
                Engine-->>Tools: Evaluation facts
            end
            Tools-->>App: Facts or a clear error result
            App->>Model: Add the result to the conversation
        end
    end
    Model-->>App: Draft, then one audit response when possible
    App-->>App: Save report and conversation log
```

The tools return measurements and game details, not coaching verdicts. For example, Stockfish can report that a move changed the evaluation; the model decides whether that evidence supports a useful lesson. Engine results are cached during a run, so a repeated request for the same analysis can reuse the earlier result.

## How the project is organized

The program is split into parts with clear jobs. This overview connects the workflow to the main folders and files:

```mermaid
flowchart LR
    U["Player"] --> M["main.py<br/>starts a run and saves its output"]
    M --> C["tools/chess_com.py<br/>loads and reads games"]
    C --> M
    M --> L["agent/loop.py<br/>talks to the AI model"]
    L <-->|"questions and facts"| F["agent/facts_store.py<br/>checks and routes requests"]
    F --> O["Opening and style tools<br/>count and measure"]
    F -.->|"when requested"| S["tools/stockfish_tool.py<br/>asks Stockfish to evaluate"]
    L <-->|"API conversation"| A["OpenAI API"]
    L --> M
    M --> R["reports/ and logs/"]
```

| Part | Responsibility |
|---|---|
| `main.py` | Starts the run, connects the parts, and saves the report and conversation. |
| `agent/loop.py` | Calls the OpenAI API and runs the model's bounded question-and-answer loop. |
| `agent/facts_store.py` | Keeps the game's facts available and checks and routes the model's tool requests. |
| `tools/chess_com.py` | Gets recent public games and reads their moves and details. |
| Opening and style tools | Count and measure game patterns; they do not choose coaching recommendations. |
| `tools/stockfish_tool.py` | Gets engine evaluations when requested by the agent. |

In short, Python and its tools establish **what happened**, while the model judges **what it means and what to recommend**. Stockfish contributes chess evaluations, not coaching advice.

## What information can the agent request?

All nine tools return facts, not ratings of a player's skill or coaching advice. Most summarize the games already loaded; two ask Stockfish for an evaluation when the model needs engine evidence.

```mermaid
flowchart LR
    G["Recent game facts"] --> F["Player record, game list, and move details"]
    G --> O["Opening choices, next moves, and line departures"]
    G --> S["Style measurements"]
    P["Agent requests engine evidence"] --> E["Stockfish analyzes a game or position"]
    F --> A["Facts returned to the agent"]
    O --> A
    S --> A
    E --> A
```

| Tool | What it can tell the agent |
|---|---|
| `get_player_profile` | How many games were loaded, results by color, and basic game and engine-analysis counts. |
| `list_games` | Game details such as color, result, opening, and moves played. |
| `get_game_moves` | The moves in one game, who played them, and clocks; engine details if that game was analyzed. |
| `opening_sequences` | Which opening move sequences appear in the selected games and their results. |
| `move_distribution` | What moves followed a chosen opening line and how often each occurred. |
| `departure_points` | Where games first left a chosen line, which side left it, and what happened in those games. |
| `get_style_measurements` | Raw counts such as castling, captures, and early queen moves; evaluation averages are included for games already analyzed. |
| `analyze_game` | Stockfish findings for a whole game, including candidate mistakes and the engine's suggested moves. |
| `evaluate_position` | A position's engine evaluation and best move after a supplied move sequence or part of a game. |

Stockfish uses depth 14. By default, `analyze_game` flags moves where the evaluation dropped by at least 100 centipawns; `--threshold` changes that cutoff for a run. The flag means “worth checking,” not “definitely a mistake.” The two engine tools run only when requested, and repeated analysis can use cached results.

Tool results are kept to a manageable size. When a result is shortened, it says so; groups too small to meet a requested minimum are not silently treated as strong evidence. Opening lines are compared by move order, so different move orders that reach the same chess position may remain separate. If a request is invalid or the engine cannot answer, the program sends an error back to the agent rather than presenting it as a chess fact.

## Decisions, checks, and limits

The agent must make its reasoning path visible on tool turns: it states the question it is pursuing, why it chose that question, what could change its mind, and its current conclusion. The program checks that these fields and the requested tool arguments have the expected format. It does not decide whether the reasoning itself is good.

The report must connect its claims to facts the agent actually received, account for sample sizes, rank recommendations, explain confidence, and mention an idea it considered but rejected. When the model first submits a report and turns remain, it gets one opportunity to check its claims, numbers, move attribution, arithmetic, and recommendations against the tool results.

These checks improve traceability, but they are not a guarantee that every claim is true. The self-audit is performed by the same model, and the program does not independently prove the quality of a coaching judgment. A person should still review the report and its evidence.

| Check or limit | What it means |
|---|---|
| Reply format | The program expects a JSON response in the agreed format and gives malformed replies a limited number of retries. |
| Tool requests | Python validates each tool request. Errors are returned to the model rather than treated as evidence. |
| Investigation limit | The default cap is 20 valid turns. If reached, the agent is asked for its best report using the facts gathered so far. |
| Evidence | The report should cite observed game facts and engine results; game outcomes alone do not prove why a move was good or bad. |
| Self-audit | One model review may catch unsupported details, but it cannot guarantee correctness. |
| External services | A full run needs Chess.com access, an OpenAI API key, and Stockfish installed. |

## What the run produces

At the end of an agent run, the program writes one Markdown file in `reports/`. Python writes the report header with the username, date, number of games, model, turn count, and audit status. The model writes the report's coaching sections. The conversation, including tool results, is also saved under `logs/` so a reader can trace its evidence.

The report should help the player answer: **What should I work on first, why does the evidence support it, and what other approach did the agent consider but reject?**

## How to explain or assess this project

The project connects to the course criteria in these concrete ways:

| Course criterion | Evidence to point to |
|---|---|
| **Working agent** | Run `main.py` with a Chess.com username and show the generated report and saved conversation. |
| **Understanding** | Explain what Python, the OpenAI model, and Stockfish each do, and describe one investigation choice the model made. |
| **Clear explanation** | Walk through the workflow diagram: API call, decision loop, evidence checks, and report output. |
| **Real problem** | Show how a player can use evidence from their own recent games to prioritize what to study. |

For the five-minute class presentation, a simple path is: explain the player's problem, show one model decision and the facts behind it, then open the generated report and describe its first recommendation.

The key agentic decision is not simply which tool to call: it is what coaching lesson and next action best fit the evidence for this player. To verify the program's deterministic behavior without external services, run the offline tests described in [Setup and Usage](setup-and-usage.md).

For installation and run instructions, see [Setup and Usage](setup-and-usage.md).

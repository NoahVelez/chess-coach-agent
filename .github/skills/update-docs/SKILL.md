---
name: update-docs
description: Create or refresh the project documentation in docs/ as Markdown, using Mermaid diagrams extensively to visualize workflows, architecture, and data flow.
disable-model-invocation: true
argument-hint: "Optional: specific doc(s) or area to update (default: all docs, synced to the current code)"
---
Update the documentation in `docs/` so it accurately reflects the **current code** in this repository. Create `docs/` and any missing files if they don't exist. If the user supplied an argument, limit updates to that doc or area; otherwise refresh everything.

## Ground rules

- **Code is the source of truth.** Before writing, read [main.py](../../main.py), [agent/](../../agent), [tools/](../../tools), [requirements.txt](../../requirements.txt), [.env.example](../../.env.example), and [README.md](../../README.md). Never document behavior, flags, thresholds, tool names, or env vars you haven't verified in code.
- Use the [requirements/](../../requirements) folder (brief, "what counts as an agent", professor discussion) for intent and constraints, but do not edit anything in it.
- **Format**: Markdown only (`.md`), GitHub-renderable. No images, no binary files, no other doc formats.
- **Mermaid everywhere it helps.** Every doc must contain at least one fenced ```` ```mermaid ```` diagram, and any process, flow, lifecycle, or relationship described in prose should be paired with a diagram. Prefer the diagram type that fits:
  - `flowchart` — control flow, decision logic, data flow
  - `sequenceDiagram` — interactions between CLI, agent loop, LLM, tools, and external services (Chess.com, Stockfish, OpenAI)
  - `stateDiagram-v2` — agent loop states and termination conditions
  - `classDiagram` / `erDiagram` — module structure and data shapes (e.g., tool return payloads, facts store)
  - `journey` or `gantt` only if they genuinely clarify something
- Keep diagrams valid and renderable: quote labels containing special characters, avoid reserved words as node IDs, keep each diagram focused (split large ones), and add a one-line caption or lead-in sentence above each.
- Keep prose short; let diagrams carry the explanation. Use tables for reference material (tools, env vars, CLI args, thresholds).
- Don't comment on or duplicate secrets. Never include real values from `.env`; reference only `.env.example`.
- Update, don't clobber: preserve accurate existing content, fix stale content, delete content describing code that no longer exists.

## Target docs

Create/refresh these files in `docs/` (adjust only if the code clearly warrants it):

| File | Purpose | Required diagrams |
|------|---------|-------------------|
| `docs/architecture.md` | Modules, responsibilities, and boundaries (agent vs. tools vs. CLI) | Component/flowchart of modules; `classDiagram` of key classes/functions; the "facts vs. judgment" boundary |
| `docs/agent-loop.md` | How the agent loop works: history, iteration cap, parsing tool calls vs. `FINAL:` | `stateDiagram-v2` of loop states; `flowchart` of one iteration; `sequenceDiagram` of a typical multi-step run; early-exit/error paths |
| `docs/tools.md` | Reference for each tool: inputs, outputs, facts-only guarantee, thresholds | Per-tool flowchart; `erDiagram` or `classDiagram` of returned data shapes |
| `docs/data-flow.md` | End-to-end path from CLI input to coaching report | End-to-end `sequenceDiagram` (user → CLI → agent → LLM → tools → Chess.com/Stockfish → report); `flowchart` of how facts are stored and re-used |
| `docs/setup-and-usage.md` | Landing page and setup: project overview, doc map, Stockfish setup, `.env`, run commands, troubleshooting | Setup flowchart; project guide map |
| `docs/design-decisions.md` | Why it's a hand-rolled agent, what's deterministic vs. model-judged, constraints from the course guide | Flowchart contrasting rule-based vs. model-judged decisions; diagram of how the path varies per run |

If the code contains subsystems not covered above (e.g., the facts store), cover them in the most relevant doc or add a new file and link it from `docs/setup-and-usage.md`.

## Conventions for every doc

1. Start with a `#` title and a 1–2 sentence summary.
2. Link to source files with relative paths (e.g., `[loop.py](../agent/loop.py)`), and link sibling docs to each other.
3. End with a short "See also" list of related docs.
4. Cross-check that README.md and `docs/` agree (commands, setup, tool names). Make minimal edits to README.md only to link to `docs/setup-and-usage.md` or to fix contradictions.

## Verify before finishing

- Every Mermaid block parses (check syntax carefully; if a Mermaid CLI such as `npx @mermaid-js/mermaid-cli` is available, validate with it, otherwise review manually).
- Every relative link points to an existing file.
- Every tool name, function, CLI flag, env var, and numeric threshold in the docs matches the code.
- `docs/setup-and-usage.md` links to every other doc.

Finish with a brief summary: which docs were created vs. updated, and any code/README inconsistencies you noticed but did not change.

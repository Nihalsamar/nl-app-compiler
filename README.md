# Natural Language → Application Compiler

A system that behaves like a **compiler for software generation**:

```
Natural language  →  structured config  →  validated  →  executable  →  working app
```

This is not a prompt-engineering demo. It is a multi-stage, schema-constrained
pipeline with a validation + repair engine and a runtime that proves the
generated configuration actually executes.

---

## Why this is a system, not a script

A single prompt to an LLM cannot reliably produce a complete, internally
consistent application spec. This project breaks the problem into controlled
stages, enforces a strict contract between them, and repairs inconsistencies
deterministically before falling back to the model.

```
                ┌─────────────────────────────────────────────┐
  user prompt → │ 1. Intent Extraction      (LLM)             │
                │ 2. System Design          (LLM)             │
                │ 3. Schema Generation      (LLM)             │
                │      db → api → ui → auth  (4 narrow stages) │
                │ 4. Validate (structural + cross-layer)      │
                │ 5. Repair  (deterministic first, LLM second)│
                │ 6. Execute (in-memory runtime smoke test)   │
                └─────────────────────────────────────────────┘
                                  ↓
                 validated AppConfig + execution proof + metrics
```

Schema generation is split into four narrow stages (`db → api → ui → auth`).
Smaller responses stay well within token limits (no truncation) and each layer
is validated and repaired independently — a more compiler-like, reliable design.

---

## The contract (strict schema enforcement)

Every layer is a Pydantic model in [`app/schemas/contracts.py`](app/schemas/contracts.py)
with `extra="forbid"`, so:

- output is always valid JSON or it is rejected,
- required fields must be present,
- field types come from a **closed enum** (the model cannot invent types),
- hallucinated/extra keys are hard errors (which is what makes repair possible).

The final assembled object must parse into `AppConfig` or generation fails.

---

## Validation + repair engine (the core)

[`app/validation/validator.py`](app/validation/validator.py) runs two passes:

1. **Structural** — does each layer parse into its strict contract?
2. **Cross-layer consistency**:
   - every API/UI entity has a DB table,
   - UI components bind to API endpoints that actually exist,
   - UI fields map to API fields,
   - API field types agree with DB column types,
   - roles used in the API/permissions are declared in auth.

[`app/validation/repair.py`](app/validation/repair.py) fixes problems in two passes:

1. **Deterministic repair** — mechanical inconsistencies are fixed *in code*,
   not by re-prompting: align an API field type to its DB column, prune a UI
   field no API exposes, register a role that is used but undeclared, drop a
   dangling endpoint binding. This removes model variance entirely.
2. **Targeted LLM repair** — only issues that need genuine regeneration (e.g. an
   entity with no table) are sent back to the model, **one affected layer at a
   time**, with the exact problems to fix. Never a blind full retry.

---

## Deterministic behaviour

- `temperature = 0`
- closed-vocabulary enums (constrained generation)
- modular per-layer generation
- deterministic repair for all mechanical fixes

Same input → consistent, structured output within reasonable variance.

---

## Execution awareness

[`app/runtime/engine.py`](app/runtime/engine.py) instantiates an in-memory CRUD
application from the validated config and runs a **smoke test** (create → list →
update → delete) against every entity, synthesising a complete sample record
from each table's columns. If any entity cannot be exercised, the config is not
truly executable and the system reports `executable: false`.

---

## Failure handling

- **Vague prompts** (e.g. `"app"`) → the system returns clarifying questions
  instead of hallucinating.
- **Invalid JSON / transient errors** → per-stage retry (not a blind full retry).
- **Inconsistencies** → deterministic + targeted LLM repair.
- Open questions surfaced by the model are returned to the user.

---

## Evaluation framework

[`eval/`](eval) contains 10 realistic product prompts + 10 edge cases (vague,
conflicting, underspecified). The runner reports **real metrics**: success rate,
executable rate, clarification rate, average repair attempts, average/median
latency, and a failure-type histogram.

```bash
python -m eval.run_eval        # writes eval_results/report.json
```

---

## Cost vs quality tradeoff

| Lever | Effect |
|-------|--------|
| Model size (8B vs 70B) | 8B is fast but unreliable at strict JSON; 70B is reliable but slower |
| Split schema stages | smaller responses → no truncation, more reliable, slightly more calls |
| Deterministic repair | fixes mechanical issues for **zero** extra tokens/latency |
| `temperature=0` | consistency over creativity |

On the NVIDIA NIM free tier, a full 70B generation runs ~1–3 minutes (the first
call includes a ~30s cold start). Deterministic repair avoids extra LLM round
trips wherever a fix can be computed.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # then edit .env
```

### Providers (set `LLM_PROVIDER` in `.env`)

- `nvidia` — NVIDIA NIM (OpenAI-compatible). Key from https://build.nvidia.com/
- `gemini` — Google Gemini. Key from https://aistudio.google.com/app/apikey
- `mock`   — deterministic offline mode (no key, no network) for tests/CI/demo

> **Security:** never commit `.env`. It is gitignored. Rotate any key that has
> been shared in plaintext.

---

## Run

```bash
# Web UI + API (the live interface)
python -m uvicorn app.server:app --reload
#  → open http://127.0.0.1:8000

# Tests (offline, deterministic)
python -m pytest -q

# Evaluation suite
python -m eval.run_eval
```

### API

```
GET  /                -> web UI
GET  /api/health      -> provider/model info
POST /api/generate    -> { "prompt": "..." } -> config + validation + runtime + metrics
```

---

## Project structure

```
app/
  schemas/contracts.py     # strict typed contract for every layer
  llm/                     # provider abstraction
    base.py                #   protocol + JSON extraction
    nim_client.py          #   NVIDIA NIM (OpenAI-compatible)
    gemini_client.py       #   Google Gemini
    mock_client.py         #   deterministic offline provider
  pipeline/
    prompts.py             # per-stage, schema-constrained prompts
    stages.py              # one function per stage (+ retry)
    orchestrator.py        # end-to-end flow + metrics
  validation/
    validator.py           # structural + cross-layer checks
    repair.py              # deterministic + targeted LLM repair
  runtime/engine.py        # in-memory runtime + execution smoke test
  server.py                # FastAPI app
  static/index.html        # web UI
eval/                      # dataset (10 real + 10 edge) + metrics runner
tests/                     # offline tests against the mock provider
```

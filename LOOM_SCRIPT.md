# Loom Script — AI Engineer Demo Task (5–10 min)

Goal: show this is an **engineered system**, not a prompt trick. Hit the five
graded criteria: system thinking, reliability, control over LLMs, execution
awareness, depth of thinking.

---

## 0:00 — The problem (45s)
> "The task is a compiler for software generation: natural language goes in, and
> a validated, executable application config comes out. The naive approach — one
> big prompt — fails because LLMs drift, hallucinate fields, and break JSON. So I
> built a multi-stage pipeline with a strict contract and a repair engine."

Show the diagram in `README.md`.

## 1:00 — Architecture (2 min)
Open `app/pipeline/orchestrator.py`.
> "Six stages: intent → design → then schema generation split into db, api, ui,
> auth. I split schemas into four narrow stages so each response is small —
> that killed the JSON-truncation failures I saw with one giant call, and lets me
> validate and repair each layer independently."

Open `app/schemas/contracts.py`.
> "Every layer is a strict Pydantic model. Types are closed enums, so the model
> can't invent a field type, and `extra='forbid'` turns any hallucinated key into
> a hard error — which is what makes repair possible."

## 3:00 — The core: validation + repair (2.5 min)
Open `app/validation/validator.py`.
> "Two passes: structural — does it parse the contract — and cross-layer — does
> the API entity have a DB table, do UI components bind to real endpoints, do API
> field types match DB columns, are roles declared."

Open `app/validation/repair.py`.
> "Repair is also two passes, and this is the key design decision. Mechanical
> problems — a field type that disagrees with the DB, a UI field no API exposes,
> an undeclared role — are fixed deterministically in code. Zero tokens, zero
> variance. Only genuinely structural problems go back to the model, one layer at
> a time, with the exact errors to fix. Never a blind full retry."

## 5:30 — Execution awareness (1 min)
Open `app/runtime/engine.py`.
> "I don't just claim the output is usable — I instantiate an in-memory CRUD app
> from the config and run create/list/update/delete on every entity. If any
> entity can't be exercised, it reports executable=false."

## 6:30 — Live demo (1.5 min)
Run the server, open the UI, paste:
> "Build a CRM with login, contacts, dashboard, role-based access, and a premium
> plan with payments. Admins can see analytics."

Point at the badges: success / valid / executable, latency, repair attempts.
Expand the generated config.

## 8:00 — Reliability + tradeoffs (1 min)
Run `python -m eval.run_eval`.
> "10 real prompts, 10 edge cases — vague, conflicting, underspecified. Vague
> prompts get clarifying questions instead of hallucination. The metrics are
> measured, not claimed."

> "Tradeoff: the 70B model is reliable but slow on the free tier — about a minute
> per generation, plus cold start. The 8B model was fast but failed strict JSON.
> Deterministic repair avoids extra LLM round trips wherever a fix is computable."

## 9:00 — Close (30s)
> "So: strict contracts for control, deterministic repair for reliability, a
> runtime for execution proof, and a measured eval harness. The model does the
> reasoning; the system keeps it on rails."

---

### Pre-record checklist
- [ ] `.env` has a working `NVIDIA_API_KEY` (with quota)
- [ ] `python -m pytest -q` passes
- [ ] server runs: `uvicorn app.server:app --reload`
- [ ] one warm generation done first (avoids cold-start dead air on camera)

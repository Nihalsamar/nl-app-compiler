# Submission — AI Engineer Demo Task

## Links
- **GitHub:** https://github.com/Nihalsamar/nl-app-compiler
- **Live URL:** https://nl-app-compiler-qi1g.onrender.com
- **Loom:** _record using `LOOM_SCRIPT.md`, paste link here_

## One-paragraph summary
A natural-language → application "compiler". A user prompt flows through a
multi-stage LLM pipeline (intent → design → db → api → ui → auth), is checked by
a structural + cross-layer validator, and is then repaired — mechanical
inconsistencies deterministically in code, structural ones via targeted,
single-layer LLM regeneration (never a blind retry). Output is enforced by
strict Pydantic contracts (closed enums, no extra keys) and proven executable by
an in-memory runtime that runs full CRUD on every entity. Reliability and cost
tradeoffs are measured by an eval harness over 10 real + 10 edge-case prompts.

## How it maps to the brief
- Multi-stage pipeline (not single prompt) ✔
- Strict schema enforcement (Pydantic, closed enums, extra=forbid) ✔
- Validation + repair engine (deterministic + targeted LLM) ✔
- Deterministic behaviour (temp 0, enums, modular generation) ✔
- Execution awareness (runtime CRUD smoke test) ✔
- Failure handling (clarifying questions, per-stage retry) ✔
- Evaluation framework (real metrics) ✔
- Cost vs quality tradeoff (documented in README) ✔

## IMPORTANT — before recording / submitting
1. **Make the live URL use the real model.** The deploy currently runs in
   offline `mock` mode (no key set on the host). In the Render dashboard →
   Environment, add:
   - `LLM_PROVIDER = nvidia`
   - `NVIDIA_API_KEY = <a key WITH quota>`
   - (optional) `NVIDIA_MODEL = meta/llama-3.3-70b-instruct`
   Save → it redeploys. `/api/health` should then show `provider: nvidia`.
2. **Rotate the keys** pasted earlier (NVIDIA + Gemini) — they were exposed.
3. Render free tier sleeps when idle; the first request after idle takes ~30–50s
   (the UI now shows a "waking up" message and auto-retries once).

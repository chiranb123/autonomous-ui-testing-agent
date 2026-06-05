# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Agent

```bash
# Run the full pipeline (fetch GitHub issues → generate scenarios → execute)
python main.py

# Force regeneration, bypassing all caches
FRESH=1 python main.py

# On Windows — force UTF-8 to avoid UnicodeEncodeError with emoji in print()
PYTHONUTF8=1 python main.py
```

## Running Tests

```bash
# All tests
pytest tests/

# Single test file
pytest tests/test_verification_engine.py

# Single test
pytest tests/test_locator.py::test_name -v
```

## Configuration (`.env`)

All runtime behaviour is controlled by `.env`:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_PROJECT_NUMBER` | GitHub Projects v2 source |
| `GITHUB_STATUS_FILTER` | Issue status to pick up (default `Ready For QA`) |
| `GROQ_API_KEY` / `GROQ_MODEL` | Primary LLM (Groq) |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | Fallback LLM (OpenRouter) |
| `START_URL` | Base URL for browser execution |
| `MAX_SCENARIOS` | Cap scenarios per run (`0` = unlimited) |
| `FRESH` | `1` = skip all disk caches and re-generate everything |
| `VALID_USERNAME` / `VALID_PASSWORD` | Login credentials for the app under test (fallback when page doesn't show hints) |
| `INVALID_PASSWORD` | Wrong password used for negative test scenarios |
| `LOCATE_RETRIES` / `LOCATE_BACKOFF` | Self-heal retries for element location |
| `CONTINUE_ON_FAILURE` | `1` = record failures but run all steps (default on) |
| `SOFT_VERIFY` | `1` = verify failures are non-fatal (default on) |
| `STEP_SCREENSHOTS` | `1` = capture screenshot after every step |

## Architecture

### Pipeline (9 steps, all in `main.py`)

```
[0] ProjectReader (GraphQL) → Issue list
[1] RequirementAnalyzer    → RequirementAnalysis   (LLM / cached)
[2] ScenarioGeneratorAgent → ScenarioCollection    (LLM / cached)
[3] FeatureFileWriter      → testscenarios/*.feature
[4] FeatureReader          → load feature dicts
[5] StepInterpreterAgent   → ExecutionPlan         (LLM / cached)
[6] PlaywrightMCPExecutor  → ExecutionResult + screenshots
[7] JsonReporter           → evidence/reports/*.json
[8] TraceabilityManager    → evidence/reports/traceability_issue_N.json
[9] HTML report generator  → evidence/reports/report_TIMESTAMP.html
```

### LLM Provider Pattern

All LLM-calling agents accept a `provider` that implements `llm/provider.py` (`generate(prompt) -> str`). Concrete providers live in `llm/`:

- `GroqProvider` — Groq API with 4-model fallback chain (docstring-intended primary)
- `DeepSeekProvider` — OpenRouter (OpenAI-compatible) with 10-model fallback chain; despite the name, routes to whichever free model is available
- `GeminiProvider`, `NvidiaProvider`, `OllamaProvider` — additional options

`main.py` currently instantiates `DeepSeekProvider`. The `.env` `GROQ_API_KEY`/`DEEPSEEK_API_KEY` control which provider's key is available.

### Browser Automation (MCP Bridge)

`mcp/mcp_session.py` spawns `npx @playwright/mcp` as a subprocess and communicates via JSON-RPC over stdin/stdout. `mcp/playwright_client.py` wraps it with typed methods (`navigate`, `snapshot`, `click`, `type`, `screenshot`, `wait`).

`PlaywrightMCPExecutor` opens **one persistent session** for the whole run (passed `persistent=True` in `main.py`) — call `executor.connect()` once before the issue loop and `executor.disconnect()` in `finally`.

### Element Location & Self-Healing

`ElementLocatorAgent.locate(snapshot_text, target)` returns a `[ref=N]` string from the accessibility snapshot:
1. LLM mode (preferred): sends snapshot + target description to LLM, gets `{"ref": ..., "confidence": ...}`
2. Regex fallback: phrase match → token match → reverse search

On failure, `PlaywrightMCPExecutor._locate_with_retries()` strips filler words from the target and retries up to `LOCATE_RETRIES` times with a fresh snapshot.

### Credential Resolution

Two special `value` tokens handled in `playwright_mcp_executor.py`:
- `__READ_FROM_PAGE__` — regex-scrapes the live page snapshot for username/password hints (handles saucedemo, practicetestautomation, etc.)
- `__INVALID_VALUE__` — substitutes intentionally wrong credentials for negative test scenarios

These are injected by `StepInterpreterAgent` when the Gherkin uses generic phrases like "valid credentials" or "invalid password".

### Caching

Per-issue artifacts in `artifacts/issue_N/`:
- `fingerprint.json` — invalidates `analysis.json`, `scenarios.json`, and `plans/*.json` when the issue body/title changes
- `analysis.json` — cached `RequirementAnalysis`
- `scenarios.json` — cached `ScenarioCollection`
- `plans/<scenario_name>.json` — cached `ExecutionPlan` per scenario

Set `FRESH=1` to bypass all caches.

### GitHub Projects v2 Query

`ProjectReader` uses the GitHub GraphQL API querying `user(login: $login) { projectV2(...) }`. This only works for **user-owned** projects. For org-owned projects, the query must use `organization(login: $login)` instead.

## Known Issues

- **Windows `UnicodeEncodeError`**: `main.py` prints emoji characters (✅, ✗, 📷) that fail on Windows `cp1252` stdout. Fix: run with `PYTHONUTF8=1` or set `$env:PYTHONUTF8=1` in PowerShell before running.
- **`requirements.txt` is incomplete**: Missing `groq`, `openai`, `google-generativeai` — install manually if using those providers.
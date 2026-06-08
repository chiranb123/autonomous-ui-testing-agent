# Test Plan — Autonomous UI Testing Agent

## 1. Executive Summary

This document describes the architecture, strategy, and execution approach of an autonomous UI testing agent that reads GitHub Project issues, generates test scenarios using a Large Language Model, and executes them against a live web application via browser automation — without any hardcoded selectors or manually written test scripts.

**Target application:** SauceDemo (`https://www.saucedemo.com`) — a public e-commerce sandbox  
**GitHub issue tested:** Issue #2 — *Purchase a Product Successfully* (10 Acceptance Criteria)  
**LLM used:** Meta Llama 3.3 70B (served via Groq API; falls back to `llama-3.1-8b-instant` when daily quota is exhausted)

---

## 2. Scope

| In scope | Out of scope |
|---|---|
| Login flows (valid + invalid credentials) | Payment gateway integration |
| Product browsing and cart management | Third-party OAuth / SSO |
| End-to-end checkout (info → overview → confirmation) | Mobile browser testing |
| Negative tests (wrong credentials, empty fields) | Performance / load testing |
| AC-to-execution traceability | Visual regression testing |

---

## 3. Agent Architecture

The agent is a **9-step sequential pipeline** orchestrated by `main.py`:

```
┌─────────────────────────────────────────────────────────────────┐
│                      AUTONOMOUS TEST AGENT                      │
│                                                                  │
│  GitHub Project (GraphQL)                                       │
│        │                                                         │
│        ▼                                                         │
│  [1] RequirementAnalyzer ──────────► RequirementAnalysis model  │
│        │  (LLM: understands ACs,                                │
│        │   user actions, validations)                           │
│        ▼                                                         │
│  [2] ScenarioGeneratorAgent ──────► ScenarioCollection          │
│        │  (LLM: Gherkin scenarios                               │
│        │   from structured analysis)                            │
│        ▼                                                         │
│  [3] FeatureFileWriter ───────────► testscenarios/*.feature     │
│        ▼                                                         │
│  [4] StepInterpreterAgent ────────► ExecutionPlan               │
│        │  (LLM: Gherkin steps →                                 │
│        │   navigate/type/click/verify/wait)                     │
│        ▼                                                         │
│  [5] PlaywrightMCPExecutor                                      │
│        │  ┌─────────────────────────────┐                       │
│        │  │  @playwright/mcp subprocess │                       │
│        │  │  JSON-RPC over stdin/stdout  │                       │
│        │  │  Accessibility snapshots     │                       │
│        │  └─────────────────────────────┘                       │
│        ▼                                                         │
│  [6] ElementLocatorAgent ─────────► ref=eN (from snapshot)      │
│        │  (LLM + regex fallback)                                 │
│        ▼                                                         │
│  [7] VerificationEngine ──────────► PASS / FAIL                 │
│        ▼                                                         │
│  [8] TraceabilityManager + Reports                              │
│        └──► HTML dashboard, JSON reports, traceability matrix   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. How the LLM Interacts with the Browser

The LLM never touches the browser directly. The interaction is strictly separated:

| Component | Role |
|---|---|
| LLM (Groq / llama-3.3-70b) | Reads Acceptance Criteria → generates test intent (Gherkin + execution plan) |
| Playwright MCP subprocess | Controls the actual browser (Chromium) |
| ElementLocatorAgent | Bridges the two: LLM reads the **accessibility snapshot** text and returns a `[ref=N]` identifier which Playwright MCP uses to interact with the element |

**Accessibility snapshot (not DOM):** The browser exposes its current state as a structured accessibility tree (text, roles, refs). The LLM reads this plain text and identifies elements semantically — no CSS selectors, no XPath, no brittle DOM queries.

Example snapshot excerpt:
```
- textbox "Username" [ref=e11]
- textbox "Password" [ref=e13]
- button "Login" [ref=e15]
```

The LLM receives the target description (e.g. `"username field"`) and the snapshot, then returns:
```json
{"ref": "e11", "element_text": "Username", "confidence": "high"}
```

---

## 5. Prompt Engineering Strategy

### Anti-Hallucination Architecture

Four LLM prompt templates are used, each with strict guardrails:

#### 5.1 Requirement Analysis Prompt
- **Grounding Rule:** Every list item must be traceable to a specific sentence in the User Story or ACs. If not → omit.
- **Vocabulary Rule:** Exact page names, button labels, and error messages from the input must be copied verbatim (e.g. if ACs say "Products page", the output must say "Products page" — never "dashboard" or "home").
- **Forbidden:** Generic QA risks (network failures, browser compatibility) unless the ACs mention them.

#### 5.2 Scenario Generation Prompt
- **No invented credentials:** Generic language only (`"a valid username"`, not `"standard_user"`).
- **No invented page names:** Only names present in the Requirement Analysis output.
- **Few-shot examples** showing BAD (invented values) vs GOOD (generic language) Gherkin.
- Maximum 3 scenarios per issue; first must always be the happy path.

#### 5.3 Step Interpreter Prompt
- **Navigate rule:** `value` for navigate steps is always `""` — the executor injects `START_URL` from `.env`.
- **Credential tokens:** Generic Gherkin (`"a valid username"`) → `__READ_FROM_PAGE__`; invalid → `__INVALID_VALUE__`. These are resolved at execution time from the live page.
- **Few-shot example** of a complete login execution plan to anchor the output format.

#### 5.4 Element Locator Prompt
- **Ref verification:** Must scan the snapshot line-by-line for `[ref=XXX]`. May only return refs that exist verbatim in the snapshot.
- **Confidence gating:** Only `high` or `medium` confidence results are accepted. `low` confidence falls back to regex-based search.

#### 5.5 Post-generation validation (code layer)
- `_is_hallucinated_verify()` drops verify steps whose value is a generic description rather than quoted page text.
- Tokens `__READ_FROM_PAGE__` and `__INVALID_VALUE__` are rejected as verify values (they are only valid for type actions).

---

## 6. Element Identification Strategy

Elements are identified in a **three-tier cascade** — no CSS selectors or XPath are used at any tier:

```
Tier 1 — LLM (high/medium confidence)
  Read accessibility snapshot + target description → return ref
  Accept only if confidence = "high" or "medium"
         │
         │ (if low confidence or not found)
         ▼
Tier 2 — Regex (exact text search)
  Pattern: target phrase before [ref=N], or [ref=N] near target
  Three variants: exact phrase → token search → reverse search
         │
         │ (if still not found)
         ▼
Tier 3 — Self-healing retry
  Take fresh snapshot, simplify target (remove filler words),
  try again — up to LOCATE_RETRIES (default: 3) attempts
```

---

## 7. Assertion / Verification Strategy

- **Text-based verification:** The `VerificationEngine` checks whether expected text appears anywhere in the accessibility snapshot (case-insensitive). No element-specific assertions are used.
- **Soft verify (default ON):** Verification failures are recorded in the report but do not abort the scenario flow — the full user journey is always captured.
- **Error detection:** After each action, the snapshot is scanned for error-pattern words (`"invalid"`, `"error"`, `"required"`, etc.). If found, the first matching sentence is reported as the step's context.
- **Traceability:** Each verification is mapped back to its source Acceptance Criterion in the traceability matrix.

---

## 8. Credential Resolution

The agent never hardcodes credentials. Resolution order at runtime:

1. **Page hints** — regex-scans the live page for patterns like `"Accepted usernames are:"` / `"Password for all users:"` (works on demo sites like SauceDemo).
2. **`.env` variables** — `VALID_USERNAME` / `VALID_PASSWORD` (for real applications).
3. **Warning logged** — if neither source provides a value, a clear warning is printed and the field is left empty.

Special tokens in execution plans:
- `__READ_FROM_PAGE__` → resolved to valid credentials at runtime
- `__INVALID_VALUE__` → substituted with deliberately wrong credentials for negative tests

---

## 9. Error Handling

| Failure type | Behaviour |
|---|---|
| LLM quota exhausted | Automatic fallback to next model in chain; final fallback to OpenRouter |
| Element not found | Self-healing retry with simplified target and fresh snapshot (up to 3 attempts) |
| Navigation fails | Step recorded as FAILED; subsequent steps continue if `CONTINUE_ON_FAILURE=1` |
| Verification fails | Recorded as FAILED with expected vs. actual text; flow continues if `SOFT_VERIFY=1` |
| MCP subprocess crash | Exception caught; final screenshot attempted; `ExecutionResult` returned with error |
| JSON parse error from LLM | Model marked as garbage/failed; next model in fallback chain tried |

---

## 10. Test Environment

| Item | Value |
|---|---|
| Target URL | `https://www.saucedemo.com` |
| Browser | Chromium (via `@playwright/mcp`) |
| LLM (primary) | Meta Llama 3.3 70B — served via Groq API |
| LLM (fallback 1) | Meta Llama 3.1 8B Instant — served via Groq API |
| LLM (fallback 2) | Meta Llama 3.3 70B Instruct — served via OpenRouter |
| Python version | 3.11+ |
| Node.js version | 18+ |
| OS tested | Windows 11 |

---

## 11. Entry and Exit Criteria

**Entry criteria:**
- GitHub issue is in "Ready For QA" status
- `START_URL` is accessible
- At least one LLM provider has quota available

**Exit criteria:**
- All scenarios have been executed (PASSED or FAILED)
- HTML dashboard and traceability matrix are generated under `evidence/reports/`
- Each scenario has a final screenshot as visual evidence

---

## 12. Deliverables

| Artifact | Location |
|---|---|
| Test scenarios (Gherkin) | `testscenarios/*.feature` (generated per run) |
| HTML test report | `evidence/reports/report_TIMESTAMP.html` |
| Per-scenario JSON results | `evidence/reports/*.json` |
| Traceability matrix | `evidence/reports/traceability_issue_N.json` |
| Screenshots | `tests/evidence/screenshots/*.png` |
| Cached LLM outputs | `artifacts/issue_N/` (analysis, scenarios, execution plans) |

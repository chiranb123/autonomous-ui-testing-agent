# Autonomous UI Testing Agent

An intelligent, end-to-end UI testing agent that reads **GitHub Project issues**, generates **Gherkin test scenarios** using an LLM, and **executes them autonomously** in a real browser via Playwright MCP — no hardcoded selectors, no manual test writing.

---

## How it works

```
GitHub Project (Ready For QA)
        ↓
[0]  Fetch issues via GraphQL
        ↓
[1]  LLM → Requirement Analysis   (understands ACs, user actions, validations)
        ↓
[2]  LLM → Gherkin Scenarios      (positive, negative, edge cases)
        ↓
[3]  Write .feature files
        ↓
[4]  LLM → Execution Plans        (navigate / type / click / verify / wait)
        ↓
[5]  Playwright MCP → Browser     (accessibility-snapshot-based element location)
        ↓
[6]  HTML Dashboard + JSON Reports + Screenshots
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| Node.js | 18 or later (for `npx @playwright/mcp`) |
| npm / npx | bundled with Node.js |

---

## Quick setup (5 minutes)

### 1. Clone the repository

```bash
git clone https://github.com/chiranb123/autonomous-ui-testing-agent.git
cd autonomous-ui-testing-agent
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
playwright install chromium
```

### 5. Install the Playwright MCP server

```bash
npm install -g @playwright/mcp
```

Verify it works:

```bash
npx @playwright/mcp --version
```

### 6. Create your `.env` file

Copy the template and fill in your keys:

```bash
cp .env.example .env   # or create .env manually
```

Minimum required fields:

```env
# GitHub — must have read access to the project board
GITHUB_TOKEN=ghp_your_token_here
GITHUB_OWNER=your_github_username
GITHUB_PROJECT_NUMBER=1
GITHUB_STATUS_FILTER=Ready For QA

# LLM — Groq is the default (fast, free tier available)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Target application
START_URL=https://www.saucedemo.com/

# Run controls
MAX_SCENARIOS=0    # 0 = all scenarios; 1-N = cap per issue
FRESH=1            # 1 = regenerate everything; 0 = use cached LLM results
```

---

## API keys — where to get them

| Key | Where to get it | Free tier |
|---|---|---|
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens (classic). Scopes needed: `read:project`, `repo` | ✅ Free |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys | ✅ Free |
| `DEEPSEEK_API_KEY` | [openrouter.ai](https://openrouter.ai) → Keys (used as OpenRouter key, despite the name) | ✅ Free models available |

> **Note:** `.env` is in `.gitignore` and will never be committed. Never share your API keys.

---

## Running the agent

```bash
python main.py
```

The agent will:
1. Fetch all issues in your GitHub Project with status `Ready For QA`
2. Analyse their Acceptance Criteria with the LLM
3. Generate Gherkin scenarios
4. Open a browser window and execute the tests
5. Save screenshots, JSON reports, and an HTML dashboard under `evidence/`

### Run with a different LLM provider

```bash
# Use OpenRouter instead of Groq (e.g. if Groq quota is exhausted)
LLM_PROVIDER=openrouter python main.py
```

### Force fresh regeneration (bypass all caches)

```bash
FRESH=1 python main.py
```

### Limit to N scenarios per issue

```bash
MAX_SCENARIOS=1 python main.py
```

### Windows — avoid encoding errors

```bash
set PYTHONUTF8=1 && python main.py
# or add PYTHONUTF8=1 to your .env
```

---

## Application credentials

For **demo sites** (SauceDemo, practicetestautomation.com) the agent reads credentials directly from the login page — no configuration needed.

For **real applications**, set these in `.env`:

```env
VALID_USERNAME=your_test_username
VALID_PASSWORD=your_test_password
INVALID_PASSWORD=wrong_password_!!!
```

---

## Output files

After each run, the following are generated (all excluded from git):

| Path | Description |
|---|---|
| `evidence/reports/report_TIMESTAMP.html` | Self-contained HTML dashboard with embedded screenshots |
| `evidence/reports/traceability_issue_N.json` | AC-to-execution traceability matrix |
| `evidence/reports/*.json` | Per-scenario execution results |
| `tests/evidence/screenshots/*.png` | Final screenshot per scenario |
| `testscenarios/*.feature` | Generated Gherkin feature files |
| `artifacts/issue_N/` | Cached LLM outputs (analysis, scenarios, plans) |

Open the HTML report in any browser — it is fully self-contained (screenshots are base64-embedded).

---

## Configuring your GitHub Project

1. Create a GitHub Project (Projects v2)
2. Add a **Status** field with at least one option: `Ready For QA`
3. Create an issue with a **User Story** section and **Acceptance Criteria** like:

```markdown
## User Story
As a customer, I want to log in to the store so that I can browse products.

## Acceptance Criteria
- AC1 - Valid login: User can log in with valid credentials and sees the Products page
- AC2 - Invalid login: An error message is displayed for wrong credentials
- AC3 - Empty fields: A validation message appears when fields are left blank
```

4. Move the issue card to **Ready For QA**
5. Run `python main.py`

---

## Project structure

```
autonomous-ui-testing-agent/
├── main.py                        # 9-step pipeline orchestrator
├── agents/
│   ├── requirement_analyzer.py    # LLM: AC → RequirementAnalysis
│   ├── scenario_generator_agent.py# LLM: analysis → Gherkin scenarios
│   ├── step_interpreter_agent.py  # LLM: Gherkin → ExecutionPlan
│   ├── element_locator_agent.py   # LLM + regex: target → [ref=N]
│   ├── feature_file_writer.py     # Writes .feature files to disk
│   └── ac_extractor.py            # Extracts ACs from issue body
├── executor/
│   └── playwright_mcp_executor.py # Runs ExecutionPlan in the browser
├── github_integration/
│   └── project_reader.py          # GraphQL: fetches RFQA issues
├── llm/
│   ├── groq_provider.py           # Groq API (primary)
│   ├── deepseek_provider.py       # OpenRouter API (fallback)
│   └── reporting/                 # HTML + JSON report generators
├── mcp/
│   ├── mcp_session.py             # JSON-RPC bridge to @playwright/mcp
│   └── playwright_client.py       # navigate / snapshot / click / type
├── models/                        # Pydantic data models
├── prompts/                       # LLM prompt templates
└── ANTI_HALLUCINATION.md          # Prompt engineering guardrails
```

---

## Self-healing & robustness

The agent handles unstable UIs without failing immediately:

- **Self-healing locator** — if an element isn't found, retries up to `LOCATE_RETRIES` times with progressively simplified target descriptions and fresh page snapshots
- **Confidence gating** — LLM element refs are only trusted at `medium`/`high` confidence; `low` confidence falls back to regex text search
- **Continue on failure** — `CONTINUE_ON_FAILURE=1` records failures but keeps executing, so the full flow appears in the report
- **Soft verify** — `SOFT_VERIFY=1` marks verification failures in the report without aborting the scenario

Tune these in `.env`:

```env
LOCATE_RETRIES=3
LOCATE_BACKOFF=1.0
CONTINUE_ON_FAILURE=1
SOFT_VERIFY=1
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `UnicodeEncodeError` on Windows | Add `PYTHONUTF8=1` to `.env` |
| `All Groq models exhausted` | Add `LLM_PROVIDER=openrouter` to `.env` or wait for daily quota reset |
| `Playwright MCP failed to start` | Run `npx @playwright/mcp --version` to verify the install |
| `GraphQL errors: user not found` | Check `GITHUB_OWNER` matches the account that owns the project |
| Element not found after retries | Increase `LOCATE_RETRIES` or check that `START_URL` is correct |
| No issues returned | Verify the issue status field is exactly `Ready For QA` (case-sensitive) |

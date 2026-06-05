"""
Autonomous UI Testing Agent — End-to-End Pipeline (GitHub Project Source)
=========================================================================

Pipeline
--------
  [0] Fetch "Ready For QA" issues from GitHub Project (GraphQL)
  [1] Requirement Analysis   (Groq LLM / cached per issue)
  [2] Scenario Generation    (Groq LLM / cached per issue)
  [3] Feature File Writing   (disk)
  [4] Feature File Reading   (disk)
  [5] Step Interpretation    (Groq LLM / cached per scenario)
  [6] Browser Execution      (Playwright MCP)
  [7] JSON Reporting         (disk)
  [8] Traceability Matrix    (disk)
  [9] HTML Dashboard Report  (self-contained HTML)

Configuration (.env)
--------------------
  GITHUB_TOKEN=ghp_...
  GITHUB_OWNER=chiranb123
  GITHUB_PROJECT_NUMBER=1
  GITHUB_STATUS_FILTER=Ready For QA

  GROQ_API_KEY=gsk_...
  GROQ_MODEL=llama-3.3-70b-versatile

  START_URL=https://practicetestautomation.com/practice-test-login/
  MAX_SCENARIOS=0    # 0 = all
  FRESH=0            # 1 = bypass all caches
"""

import io
import sys
# Force UTF-8 stdout/stderr on Windows to prevent UnicodeEncodeError with emoji
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

# --- GitHub ---
from github_integration.project_reader import ProjectReader
from agents.ac_extractor import ACExtractor

# --- Agents ---
from agents.requirement_analyzer import RequirementAnalyzer
from agents.scenario_generator_agent import ScenarioGeneratorAgent
from agents.feature_file_writer import FeatureFileWriter
from agents.step_interpreter_agent import StepInterpreterAgent

# --- Executor ---
from executor.feature_reader import FeatureReader
from executor.scenario_parser import ScenarioParser
from executor.playwright_mcp_executor import PlaywrightMCPExecutor

# --- Models ---
from models.execution_plan import ExecutionPlan
from models.issue import Issue
from models.requirement_analysis import RequirementAnalysis
from models.scenario_collection import ScenarioCollection

# --- Reporting / Traceability ---
from llm.reporting.json_reporter import JsonReporter
from llm.reporting.html_reporter import generate as generate_html_report
from traceability.traceability_manager import TraceabilityManager

load_dotenv()

# ---------------------------------------------------------------------------
# Fallback content (used when GitHub is not configured)
# ---------------------------------------------------------------------------

_FALLBACK_STORY = """
As a user,
I want to login to the application,
so that I can access my dashboard.
"""

_FALLBACK_AC = """
- User can login with valid credentials
- User cannot login with invalid password
- Validation message displayed for empty fields
"""

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_TOKEN: str | None          = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER: str | None          = os.getenv("GITHUB_OWNER")
GITHUB_PROJECT_NUMBER: int | None = (
    int(os.getenv("GITHUB_PROJECT_NUMBER"))
    if os.getenv("GITHUB_PROJECT_NUMBER") else None
)
GITHUB_STATUS_FILTER: str = os.getenv("GITHUB_STATUS_FILTER", "Ready For QA")

START_URL: str  = os.getenv("START_URL", "https://practicetestautomation.com/practice-test-login/")
MAX_SCENARIOS   = int(os.getenv("MAX_SCENARIOS", "0"))
FRESH: bool     = os.getenv("FRESH", "0") == "1"

LLM_PROVIDER_NAME: str = os.getenv("LLM_PROVIDER", "groq").lower()

ARTIFACTS_DIR = Path("artifacts")

# ---------------------------------------------------------------------------
# LLM provider factory
# ---------------------------------------------------------------------------

def _make_provider():
    if LLM_PROVIDER_NAME == "groq":
        try:
            from llm.groq_provider import GroqProvider
            return GroqProvider()
        except ImportError:
            print("    [warn] groq package not installed — falling back to OpenRouter")
    from llm.deepseek_provider import DeepSeekProvider
    return DeepSeekProvider()


def _make_provider_with_fallback():
    """
    Try the configured provider. If it raises RuntimeError at call time
    (e.g. all Groq daily quotas exhausted), wrap it so the first generate()
    failure auto-falls-back to OpenRouter.
    """
    from llm.provider import LLMProvider
    from llm.deepseek_provider import DeepSeekProvider

    primary = _make_provider()

    class FallbackProvider(LLMProvider):
        def __init__(self):
            self._primary = primary
            self._fallback: LLMProvider | None = None

        def generate(self, prompt: str) -> str:
            if self._fallback:
                return self._fallback.generate(prompt)
            try:
                return self._primary.generate(prompt)
            except RuntimeError as e:
                print(f"    [provider] Primary failed: {e}")
                print("    [provider] Switching to OpenRouter fallback...")
                self._fallback = DeepSeekProvider()
                return self._fallback.generate(prompt)

    return FallbackProvider()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    [cache] Saved  → {path}")


def _load(path: Path, model_class=None):
    """Load a JSON artifact. Returns model instance or raw dict, or None."""
    if FRESH or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_class(**data) if model_class else data
    except Exception:
        return None


def _extract_section(body: str, heading: str) -> str:
    """Extract text under a markdown or colon-style heading."""
    pattern = re.compile(
        rf'^#{"{0,3}"}\s*{re.escape(heading)}[:\s]*$', re.IGNORECASE
    )
    stop = re.compile(r'^#{1,3}\s+\S', re.IGNORECASE)
    lines = body.splitlines()
    capturing, collected = False, []
    for line in lines:
        if pattern.match(line.strip()):
            capturing = True
            continue
        if capturing:
            if stop.match(line.strip()):
                break
            collected.append(line)
    return "\n".join(collected).strip()


def _parse_issue(issue: Issue) -> tuple[str, str, int]:
    """Extract user story, formatted acceptance criteria, and the AC count."""
    user_story = (
        _extract_section(issue.body, "User Story")
        or _extract_section(issue.body, "Description")
    )
    if not user_story:
        user_story = (
            f"As a user,\n"
            f"I want to {issue.title.lower()},\n"
            f"so that I can complete my goal."
        )

    raw_acs = ACExtractor().extract(issue.body)
    acceptance_criteria = (
        "\n".join(f"- {ac}" for ac in raw_acs)
        if raw_acs else issue.body
    )
    return user_story, acceptance_criteria, len(raw_acs)


# ---------------------------------------------------------------------------
# Step 0 — Fetch "Ready For QA" issues from GitHub Project
# ---------------------------------------------------------------------------

def step_fetch_issues() -> list[Issue]:
    print(f"\n[0] GitHub Project Fetch  (status='{GITHUB_STATUS_FILTER}')")

    if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_PROJECT_NUMBER]):
        missing = [k for k, v in {
            "GITHUB_TOKEN": GITHUB_TOKEN,
            "GITHUB_OWNER": GITHUB_OWNER,
            "GITHUB_PROJECT_NUMBER": GITHUB_PROJECT_NUMBER,
        }.items() if not v]
        print(f"    ⚠  Missing: {missing} — using inline fallback.")
        return [Issue(number=0, title="User Login",
                      body=_FALLBACK_STORY + "\nAcceptance Criteria:\n" + _FALLBACK_AC)]

    try:
        issues = ProjectReader(token=GITHUB_TOKEN).fetch_issues_by_status(
            owner=GITHUB_OWNER,
            project_number=GITHUB_PROJECT_NUMBER,
            status_filter=GITHUB_STATUS_FILTER,
        )
        if not issues:
            print(f"    ⚠  No issues found with '{GITHUB_STATUS_FILTER}' — using fallback.")
            return [Issue(number=0, title="User Login",
                          body=_FALLBACK_STORY + "\nAcceptance Criteria:\n" + _FALLBACK_AC)]

        print(f"    ✅ {len(issues)} issue(s) ready for QA:")
        for i in issues:
            print(f"       #{i.number} — {i.title}")
        return issues

    except Exception as exc:
        print(f"    ✗ Fetch failed: {exc} — using fallback.")
        return [Issue(number=0, title="User Login",
                      body=_FALLBACK_STORY + "\nAcceptance Criteria:\n" + _FALLBACK_AC)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:

    print("=" * 62)
    print(" Autonomous UI Testing Agent")
    print(f" LLM    : {LLM_PROVIDER_NAME.upper()} / {os.getenv('GROQ_MODEL') if LLM_PROVIDER_NAME == 'groq' else os.getenv('DEEPSEEK_MODEL', 'deepseek')}")
    print(f" Target : {START_URL}")
    print(f" Owner  : {GITHUB_OWNER or '(not set)'}")
    print(f" Project: #{GITHUB_PROJECT_NUMBER or '(not set)'}")
    print(f" Filter : {GITHUB_STATUS_FILTER}")
    print(f" Fresh  : {FRESH}")
    print("=" * 62)

    provider    = _make_provider_with_fallback()
    all_results = []

    # Persistent reusable components — created ONCE for the whole run
    # (eliminates per-scenario MCP/browser restart ≈ 3-5s each)
    interpreter = StepInterpreterAgent(provider=provider)
    executor    = PlaywrightMCPExecutor(provider=provider, persistent=True)
    reporter    = JsonReporter()

    # 0. Fetch issues
    issues = step_fetch_issues()

    # Open browser/MCP session ONCE
    executor.connect()

    try:
        for issue in issues:

            print(f"\n{'─'*62}")
            print(f" Issue #{issue.number}: {issue.title}")
            print(f"{'─'*62}")

            # Per-issue artifact directory
            art = ARTIFACTS_DIR / f"issue_{issue.number}"
            art.mkdir(parents=True, exist_ok=True)

            analysis_file  = art / "analysis.json"
            scenarios_file = art / "scenarios.json"
            plans_dir      = art / "plans"
            cache_file     = art / "fingerprint.json"

            # Invalidate caches if issue changed
            fingerprint = {"number": issue.number, "title": issue.title, "body": issue.body}
            if not FRESH and cache_file.exists():
                if json.loads(cache_file.read_text()) != fingerprint:
                    print("    ⚠  Issue changed — clearing per-issue caches...")
                    for f in [analysis_file, scenarios_file]:
                        f.unlink(missing_ok=True)
                    for p in (list(plans_dir.glob("*.json")) if plans_dir.exists() else []):
                        p.unlink(missing_ok=True)
            _save(cache_file, fingerprint)

            user_story, acceptance_criteria, ac_count = _parse_issue(issue)
            print(f"\n    User Story : {user_story.strip()[:80]}...")
            print(f"    ACs found  : {ac_count}")

            # 1. Requirement Analysis
            analysis = _load(analysis_file, RequirementAnalysis)
            if analysis is None:
                print("\n[1] Requirement Analysis (LLM)...")
                analysis = RequirementAnalyzer(provider=provider).analyze(
                    user_story=user_story,
                    acceptance_criteria=acceptance_criteria,
                )
                _save(analysis_file, analysis.model_dump())
            else:
                print(f"\n[1] Requirement Analysis (cached) — {analysis.feature_name}")

            # 2. Scenario Generation
            collection = _load(scenarios_file, ScenarioCollection)
            if collection is None:
                print("\n[2] Scenario Generation (LLM)...")
                collection = ScenarioGeneratorAgent(provider=provider).generate(analysis)
                _save(scenarios_file, collection.model_dump())
            else:
                print(f"\n[2] Scenario Generation (cached) — {len(collection.scenarios)} scenarios")

            # 3. Write feature files
            print("\n[3] Writing Feature Files")
            written_paths = FeatureFileWriter().write(collection.scenarios)

            # 4. Use the just-written files directly — avoids picking up stale files from prior runs
            print("\n[4] Reading Feature Files")
            features = [
                {
                    "name": Path(p).stem,
                    "path": p,
                    "content": Path(p).read_text(encoding="utf-8"),
                }
                for p in written_paths
            ]
            if not features:
                print("    No .feature files generated — skipping.")
                continue
            if MAX_SCENARIOS > 0:
                features = features[:MAX_SCENARIOS]
            print(f"    {len(features)} feature(s) loaded")

            # 5–7. Interpret → Execute → Report
            print("\n[5-7] Interpret → Execute → Report")
            issue_results = []
            plans_dir.mkdir(parents=True, exist_ok=True)

            for feature in features:
                name  = feature["name"]
                print(f"\n  ▶ {name}")

                steps = ScenarioParser().parse(feature["content"])
                if not steps:
                    print("    (no steps, skipping)")
                    continue

                title = name.split("_", 1)[-1].replace("_", " ") if "_" in name else name

                # Load or generate execution plan
                plan_file = plans_dir / f"{name}.json"
                plan = _load(plan_file)
                if plan is None:
                    print("    Interpreting (LLM)...")
                    plan = interpreter.interpret(steps, scenario_name=title)
                    _save(plan_file, plan.model_dump())
                else:
                    plan = ExecutionPlan(**plan)

                if not plan.scenario_name:
                    plan.scenario_name = title

                # Execute (reuses the persistent browser session)
                result = executor.execute(plan, start_url=START_URL)
                issue_results.append(result)
                all_results.append(result)

                icon = "✓" if result.status == "PASSED" else "✗"
                print(f"    {icon} {result.status}  — {result.scenario_name}")
                if result.error_message:
                    print(f"      Error: {result.error_message}")

                reporter.generate(result)

            # 8. Traceability
            if issue_results:
                print("\n[8] Traceability Matrix")
                trace = TraceabilityManager().build(
                    scenarios=collection.scenarios[:len(issue_results)],
                    execution_results=issue_results,
                )
                tp = Path("evidence/reports") / f"traceability_issue_{issue.number}.json"
                tp.parent.mkdir(parents=True, exist_ok=True)
                tp.write_text(json.dumps([t.model_dump() for t in trace], indent=2), encoding="utf-8")
                print(f"    Saved → {tp}")

    finally:
        # Always close browser/MCP session
        executor.disconnect()

    # 9. HTML Dashboard
    print("\n[9] HTML Report...")
    html_path = generate_html_report(
        results=all_results,
        github_issue=issues[0] if len(issues) == 1 else None,
        start_url=START_URL,
    )
    print(f"    📊 → {html_path}")

    passed = sum(1 for r in all_results if r.status == "PASSED")
    failed = len(all_results) - passed
    print("\n" + "=" * 62)
    print(f" {passed} PASSED   {failed} FAILED   {len(all_results)} TOTAL")
    print("=" * 62)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()

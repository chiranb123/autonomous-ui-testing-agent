import os
import re
import time

from executor.evidence_manager import EvidenceManager
from models.execution_result import ExecutionResult
from models.step_result import StepResult
from agents.element_locator_agent import ElementLocatorAgent
from mcp.playwright_client import PlaywrightClient
from verification.verification_engine import VerificationEngine

# Per-step screenshots are expensive (full-page PNG via MCP).
_STEP_SCREENSHOTS = os.getenv("STEP_SCREENSHOTS", "0") == "1"
_STEP_SCREENSHOT_FULLPAGE = os.getenv("STEP_SCREENSHOT_FULLPAGE", "0") == "1"
# Small settle delay after click (most apps need a tiny moment for DOM updates)
_POST_CLICK_DELAY = float(os.getenv("POST_CLICK_DELAY", "0.3"))

# Self-healing controls
_LOCATE_RETRIES = int(os.getenv("LOCATE_RETRIES", "3"))      # tries per type/click
_LOCATE_BACKOFF = float(os.getenv("LOCATE_BACKOFF", "1.0"))  # seconds between tries

# Continue executing remaining steps when a step fails (so the report
# shows the FULL flow, not just the first failure). Default ON.
_CONTINUE_ON_FAILURE = os.getenv("CONTINUE_ON_FAILURE", "1") == "1"

# Verify failures are soft by default — the verification text is often where
# the LLM hallucinates ("dashboard" when AC says "Products"). Soft means:
# record the failure in the report, but DO NOT abort the rest of the flow.
_SOFT_VERIFY = os.getenv("SOFT_VERIFY", "1") == "1"

# Common error-message patterns for dynamic detection
_ERROR_PATTERNS = [
    "invalid", "incorrect", "wrong", "failed", "error",
    "required", "not found", "unauthorized", "forbidden",
    "please", "must", "cannot", "unable",
]


def _snapshot_text(snapshot: dict) -> str:
    try:
        return snapshot["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return ""


def _has_error_on_page(text: str) -> str | None:
    """Return first error-like sentence found, or None."""
    lower = text.lower()
    for pattern in _ERROR_PATTERNS:
        if pattern in lower:
            # Find the line containing the pattern
            for line in text.splitlines():
                if pattern in line.lower() and len(line.strip()) > 3:
                    return line.strip()
    return None


# ---------------------------------------------------------------------------
# Credential resolution — read REAL credentials from page hints instead of
# hallucinating them. Many demo sites (saucedemo, practicetestautomation, etc.)
# display the accepted username/password right on the login page.
# ---------------------------------------------------------------------------

_READ_FROM_PAGE_TOKEN = "__READ_FROM_PAGE__"
_INVALID_TOKEN = "__INVALID_VALUE__"

# Explicit credentials configured in .env — used as fallback when the page
# doesn't display hints (i.e. any real application).
_ENV_USERNAME = os.getenv("VALID_USERNAME", "")
_ENV_PASSWORD = os.getenv("VALID_PASSWORD", "")
_ENV_INVALID_PASSWORD = os.getenv("INVALID_PASSWORD", "wrong_password_!!!")


def _looks_like_password_field(target: str) -> bool:
    t = (target or "").lower()
    return "password" in t or "pwd" in t or "pass " in t or t.endswith(" pass")


def _looks_like_username_field(target: str) -> bool:
    t = (target or "").lower()
    return (
        "username" in t or "user name" in t or "user id" in t
        or "email" in t or "login" in t or t == "user"
    )


def _clean_snap_value(raw: str) -> str:
    """Strip MCP accessibility-tree metadata from a raw snapshot token."""
    # Remove [ref=XX], [level=N], [role=...], [readonly], etc.
    cleaned = re.sub(r'\[[^\]]*\]', '', raw)
    # Remove stray quote/dash/bullet/whitespace left behind
    return cleaned.strip(' "\'`-•')


# Words that appear as accessibility-tree element type annotations in the
# Playwright MCP snapshot (e.g. "- text "Accepted usernames are:" [ref=e5]").
# These must never be mistaken for credential values.
_SNAP_KEYWORDS = {
    "text", "button", "link", "input", "heading", "image", "img",
    "list", "listitem", "item", "ref", "level", "role", "type",
    "name", "value", "label", "group", "region", "main", "nav",
    "footer", "header", "dialog", "alert", "section", "paragraph",
    "span", "div", "form", "table", "row", "cell", "column", "tab",
    "panel", "tree", "grid", "listbox", "combobox", "menu", "menuitem",
    "toolbar", "option", "checkbox", "radio", "generic", "landmark",
    "contentinfo", "complementary", "banner", "navigation", "search",
    "article", "figure", "strong", "emphasis", "code", "pre",
}


def _extract_credentials_from_page(snap_text: str) -> dict:
    """
    Scrape username + password hints from the page snapshot text.

    Playwright MCP accessibility snapshots embed element-type annotations
    inline: e.g. '- text "Accepted usernames are:" [ref=e5]'. A naïve
    regex that captures the next token would pick up 'text' or '[ref=e5]'
    instead of the real value.

    Strategy: find the keyword anchor, then scan the next 15 lines.
    For each line, strip all [..] metadata and the leading element-type
    keyword, then take the first remaining token that is ≥ 4 chars and
    not in _SNAP_KEYWORDS.

    Handles saucedemo.com (multi-line list) and practicetestautomation.com
    (single-line "Username: tomsmith  Password: SuperSecretPassword!").
    """
    creds: dict = {}
    text = snap_text or ""

    def _first_credential_token(keyword_pattern: str) -> str | None:
        m = re.search(keyword_pattern, text, re.IGNORECASE)
        if not m:
            return None
        tail = text[m.end():]
        for line in tail.splitlines()[:15]:
            clean = _clean_snap_value(line)
            tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9_@!#$%^&*.\-]*', clean)
            for tok in tokens:
                # Skip accessibility tree element type keywords and short words
                if len(tok) >= 4 and tok.lower() not in _SNAP_KEYWORDS:
                    return tok
        return None

    # --- Password: "Password for all users: secret_sauce" ---
    pw = _first_credential_token(r"password\s+for\s+all\s+users\s*[:\-]")
    if not pw:
        # Fallback: "Password: SuperSecretPassword!"
        pw = _first_credential_token(r"(?<!\w)password\s*[:\-]")
    if pw:
        creds["password"] = pw.rstrip(".,;:")

    # --- Username (list): "Accepted usernames are: / standard_user" ---
    un = _first_credential_token(r"accepted\s+usernames?\s+are\s*[:\-]?")
    if un:
        creds["username"] = un.rstrip(".,;:")

    # --- Username (single label): "Username: tomsmith" ---
    if "username" not in creds:
        un = _first_credential_token(r"(?<!\w)username\s*[:\-]")
        if un:
            creds["username"] = un.rstrip(".,;:")

    return creds


def _resolve_value(value: str, target: str, snap_text: str) -> str:
    """
    Replace placeholder tokens with real values.

    Resolution order for __READ_FROM_PAGE__:
      1. Page hints (demo sites that display credentials on-screen)
      2. VALID_USERNAME / VALID_PASSWORD from .env  (real applications)
      3. Empty string (logs a warning)
    """
    if not value:
        return value

    if value == _READ_FROM_PAGE_TOKEN:
        # Priority 1 — page hints (SauceDemo, practicetestautomation, etc.)
        creds = _extract_credentials_from_page(snap_text)
        if _looks_like_password_field(target) and "password" in creds:
            return creds["password"]
        if _looks_like_username_field(target) and "username" in creds:
            return creds["username"]

        # Priority 2 — explicit .env credentials (any real application)
        if _looks_like_password_field(target) and _ENV_PASSWORD:
            print(f"    [resolver] Using VALID_PASSWORD from .env")
            return _ENV_PASSWORD
        if _looks_like_username_field(target) and _ENV_USERNAME:
            print(f"    [resolver] Using VALID_USERNAME from .env")
            return _ENV_USERNAME

        print(f"    [resolver] WARNING: no credential found for '{target}' — set VALID_USERNAME/VALID_PASSWORD in .env")
        return ""

    if value == _INVALID_TOKEN:
        if _looks_like_password_field(target):
            return _ENV_INVALID_PASSWORD
        if _looks_like_username_field(target):
            return "definitely_not_a_real_user_!!!"
        return "invalid_value_!!!"

    return value


# ---------------------------------------------------------------------------
# Self-heal target variants — when the original target fails, try these.
# ---------------------------------------------------------------------------

_FILLER_WORDS = {
    "the", "a", "an", "this", "that", "field", "input", "box",
    "button", "link", "area", "section", "label", "control",
}


def _target_variants(target: str) -> list[str]:
    """
    Generate progressively simpler target descriptions for self-heal.
    e.g. "the username text input field" -> ["username text input", "username", ...]
    """
    if not target:
        return []
    variants: list[str] = []
    words = re.findall(r"[A-Za-z0-9]+", target)
    cleaned = [w for w in words if w.lower() not in _FILLER_WORDS]
    if cleaned and " ".join(cleaned).lower() != target.lower():
        variants.append(" ".join(cleaned))
    if cleaned:
        # Last "important" word — usually the noun ("username", "password", "login")
        variants.append(cleaned[-1])
        # First important word
        if cleaned[0] != cleaned[-1]:
            variants.append(cleaned[0])
    # De-duplicate while preserving order
    seen = set()
    unique = []
    for v in variants:
        k = v.lower().strip()
        if k and k not in seen and k != target.lower().strip():
            seen.add(k)
            unique.append(v)
    return unique


class PlaywrightMCPExecutor:

    def __init__(self, provider=None, persistent: bool = True):
        self.client = PlaywrightClient()
        self.locator = ElementLocatorAgent(provider=provider)
        self.evidence = EvidenceManager()
        self.verification_engine = VerificationEngine()
        # When True, caller manages connect/disconnect across many scenarios
        self.persistent = persistent
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management — call once for the whole run
    # ------------------------------------------------------------------

    def connect(self):
        if not self._connected:
            self.client.connect()
            self._connected = True

    def disconnect(self):
        if self._connected:
            self.client.disconnect()
            self._connected = False

    def _take_step_screenshot(self, scenario_name: str, step_index: int, action: str) -> str | None:
        if not _STEP_SCREENSHOTS:
            return None
        try:
            path = self.evidence.screenshot_name(
                f"{scenario_name}_step{step_index:02d}_{action}"
            )
            self.client.screenshot(path, full_page=_STEP_SCREENSHOT_FULLPAGE)
            return path
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Self-healing locator — retries with fresh snapshots and target variants
    # ------------------------------------------------------------------

    def _locate_with_retries(self, target: str) -> tuple[str | None, str, str]:
        """
        Try to locate `target` with up to _LOCATE_RETRIES attempts.
        Each attempt takes a fresh snapshot. After the first failure, also
        tries simplified target variants (self-heal).

        Returns (ref, used_target, last_snapshot_text).
        ref is None if everything failed.
        """
        snap_text = ""
        variants_to_try = [target] + _target_variants(target)

        for attempt in range(1, _LOCATE_RETRIES + 1):
            snapshot = self.client.snapshot()
            snap_text = _snapshot_text(snapshot)

            # On first attempt try just the original target.
            # On later attempts, try variants too.
            for variant in (variants_to_try if attempt > 1 else [target]):
                ref = self.locator.locate(snap_text, variant)
                if ref:
                    if variant != target:
                        print(f"    [self-heal] target '{target}' → '{variant}' worked (ref={ref})")
                    return ref, variant, snap_text

            if attempt < _LOCATE_RETRIES:
                print(
                    f"    [self-heal] '{target}' not found "
                    f"(attempt {attempt}/{_LOCATE_RETRIES}) — waiting {_LOCATE_BACKOFF}s..."
                )
                time.sleep(_LOCATE_BACKOFF)

        return None, target, snap_text

    def execute(self, execution_plan, start_url=None) -> ExecutionResult:

        step_results: list[StepResult] = []
        verification_results = []
        screenshot_path = None
        first_error: str | None = None
        start_time = time.time()

        # Only manage connection lifecycle when not running in persistent mode
        owns_connection = not self._connected
        if owns_connection:
            self.connect()

        # Helper: record a failure and decide whether to continue or abort
        def _fail(message: str):
            nonlocal first_error
            if first_error is None:
                first_error = message
            if not _CONTINUE_ON_FAILURE:
                raise Exception(message)

        try:
            for i, step in enumerate(execution_plan.steps):

                action = step.action
                target = step.target or ""
                value  = step.value  or ""

                print(f"\n  Step {i+1}: {action} | target='{target}' | value='{value}'")

                # ── NAVIGATE ──────────────────────────────────────────
                if action == "navigate":
                    if start_url:
                        try:
                            self.client.navigate(start_url)
                            shot = self._take_step_screenshot(
                                execution_plan.scenario_name, i, "navigate"
                            )
                            step_results.append(StepResult(
                                action=action, target=start_url, value="",
                                status="INFO", message=f"Navigated to {start_url}",
                                screenshot_path=shot
                            ))
                        except Exception as nav_err:
                            step_results.append(StepResult(
                                action=action, target=start_url, value="",
                                status="FAILED",
                                message=f"Navigation failed: {nav_err}",
                            ))
                            _fail(f"Navigation failed: {nav_err}")
                    continue

                # ── WAIT ──────────────────────────────────────────────
                if action == "wait":
                    try:
                        seconds = float(value) if value else 1
                    except (TypeError, ValueError):
                        seconds = 1
                    self.client.wait(seconds)
                    step_results.append(StepResult(
                        action=action, target="", value=str(seconds),
                        status="INFO", message=f"Waited {seconds}s"
                    ))
                    continue

                # ── TYPE ──────────────────────────────────────────────
                if action == "type":
                    ref, used_target, snap_text = self._locate_with_retries(target)

                    # Resolve placeholders BEFORE typing — uses real page hints
                    resolved_value = _resolve_value(value, used_target, snap_text)
                    if resolved_value != value:
                        print(f"    [resolver] '{value}' → '{resolved_value}' (from page)")
                        value = resolved_value

                    if ref:
                        try:
                            self.client.type(ref, value)
                            shot = self._take_step_screenshot(
                                execution_plan.scenario_name, i, "type"
                            )
                            step_results.append(StepResult(
                                action=action, target=target, value=value,
                                status="PASSED",
                                message=f"Typed '{value}' into ref={ref} ({used_target})",
                                screenshot_path=shot
                            ))
                        except Exception as type_err:
                            shot = self._take_step_screenshot(
                                execution_plan.scenario_name, i, "type_failed"
                            )
                            step_results.append(StepResult(
                                action=action, target=target, value=value,
                                status="FAILED",
                                message=f"Type failed on ref={ref}: {type_err}",
                                screenshot_path=shot
                            ))
                            _fail(f"Type failed: {type_err}")
                    else:
                        creds_hint = _has_error_on_page(snap_text)
                        msg = (
                            f"Element not found after {_LOCATE_RETRIES} attempts: '{target}'"
                            + (f" | Page hint: {creds_hint}" if creds_hint else "")
                        )
                        shot = self._take_step_screenshot(
                            execution_plan.scenario_name, i, "type_failed"
                        )
                        step_results.append(StepResult(
                            action=action, target=target, value=value,
                            status="FAILED", message=msg,
                            screenshot_path=shot
                        ))
                        _fail(msg)

                # ── CLICK ─────────────────────────────────────────────
                elif action == "click":
                    ref, used_target, _snap = self._locate_with_retries(target)

                    if ref:
                        try:
                            self.client.click(ref)
                            if _POST_CLICK_DELAY > 0:
                                time.sleep(_POST_CLICK_DELAY)
                            shot = self._take_step_screenshot(
                                execution_plan.scenario_name, i, "click"
                            )
                            step_results.append(StepResult(
                                action=action, target=target, value="",
                                status="PASSED",
                                message=f"Clicked ref={ref} ({used_target})",
                                screenshot_path=shot
                            ))
                        except Exception as click_err:
                            shot = self._take_step_screenshot(
                                execution_plan.scenario_name, i, "click_failed"
                            )
                            step_results.append(StepResult(
                                action=action, target=target, value="",
                                status="FAILED",
                                message=f"Click failed on ref={ref}: {click_err}",
                                screenshot_path=shot
                            ))
                            _fail(f"Click failed: {click_err}")
                    else:
                        msg = f"Clickable element not found after {_LOCATE_RETRIES} attempts: '{target}'"
                        shot = self._take_step_screenshot(
                            execution_plan.scenario_name, i, "click_failed"
                        )
                        step_results.append(StepResult(
                            action=action, target=target, value="",
                            status="FAILED", message=msg,
                            screenshot_path=shot
                        ))
                        _fail(msg)

                # ── VERIFY ────────────────────────────────────────────
                elif action == "verify":
                    expected_text = value or step.expected or target

                    # Take fresh snapshot for verification
                    snapshot = self.client.snapshot()
                    snap_text = _snapshot_text(snapshot)
                    page_error = _has_error_on_page(snap_text)

                    vr = self.verification_engine.verify_text_exists(
                        snap_text, expected_text
                    )
                    verification_results.append(vr)

                    shot = self._take_step_screenshot(
                        execution_plan.scenario_name, i, "verify"
                    )

                    if vr.passed:
                        step_results.append(StepResult(
                            action=action, target=target, value=expected_text,
                            status="PASSED",
                            message=f"Found '{expected_text}' on page",
                            screenshot_path=shot
                        ))
                        print(f"  ✓ Verified: '{expected_text}'")
                    else:
                        extra = (
                            f" | Page shows: '{page_error}'"
                            if page_error else ""
                        )
                        soft_marker = " [SOFT]" if _SOFT_VERIFY else ""
                        msg = f"'{expected_text}' not found.{extra}{soft_marker}"
                        step_results.append(StepResult(
                            action=action, target=target, value=expected_text,
                            status="FAILED",
                            message=msg,
                            screenshot_path=shot
                        ))
                        print(f"  ✗ Failed: {msg}")
                        # Soft verify: record but don't abort the flow.
                        # Hard verify: abort unless _CONTINUE_ON_FAILURE is set.
                        if not _SOFT_VERIFY:
                            _fail(vr.message)
                        elif first_error is None:
                            first_error = msg

            # ── FINAL SCREENSHOT (always) ─────────────────────────────
            screenshot_path = self.evidence.screenshot_name(
                execution_plan.scenario_name
            )
            self.client.screenshot(screenshot_path, full_page=True)
            print(f"\n  📷 Final screenshot: {screenshot_path}")

            duration = round(time.time() - start_time, 2)

            # Final scenario status — PASSED only if every step passed
            any_failed = any(s.status == "FAILED" for s in step_results)
            status = "FAILED" if any_failed else "PASSED"

            return ExecutionResult(
                scenario_name=execution_plan.scenario_name,
                status=status,
                screenshot_path=screenshot_path,
                error_message=first_error,
                verifications=verification_results,
                step_results=step_results,
                duration_seconds=duration,
            )

        except Exception as e:
            try:
                screenshot_path = self.evidence.screenshot_name(
                    execution_plan.scenario_name + "_FAILED"
                )
                self.client.screenshot(screenshot_path, full_page=True)
            except Exception:
                pass

            duration = round(time.time() - start_time, 2)

            return ExecutionResult(
                scenario_name=execution_plan.scenario_name,
                status="FAILED",
                screenshot_path=screenshot_path,
                error_message=str(e),
                verifications=verification_results,
                step_results=step_results,
                duration_seconds=duration,
            )

        finally:
            if owns_connection and not self.persistent:
                self.disconnect()

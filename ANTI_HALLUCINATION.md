
# Anti-Hallucination Rules — Autonomous UI Testing Agent

This document summarises every anti-hallucination safeguard applied across
the four LLM prompts used by this agent. Treat it as the authoritative
reference when tuning prompts or diagnosing test failures.

---

## 1. Requirement Analysis (`requirement_analysis_prompt.txt`)

### Grounding Check
Before writing any list item, the model must confirm there is a specific
sentence in the User Story or Acceptance Criteria that directly justifies
the item. If no such sentence exists, the item must not be included.

### Vocabulary Rule
All page names, button labels, field names, and error messages must use the
EXACT vocabulary from the input:
- ACs say "Products page" → always write "Products page", never "dashboard",
  "home", or "landing page".
- ACs say "Login button" → never rephrase as "submit" or "sign in".
- Quoted error messages must be copied verbatim.

### Forbidden additions
- Generic QA risks (network failures, browser compatibility, performance)
  unless explicitly mentioned in the ACs.
- Invented example values (usernames, passwords, emails, product names).
- Inferred behaviour not stated in the ACs.
- References to other test sites, unrelated systems, or previous sessions.
- Padding of `edge_cases` or `risks` with boilerplate QA wisdom.

---

## 2. Scenario Generation (`scenario_generation_prompt.txt`)

### Credential / Value Rule
When credentials or specific values are needed but not quoted in the input,
use generic plain-English language — never quoted invented values.

BAD:
```gherkin
When the user enters "standard_user"
And the user enters "secret_sauce"
Then the user is redirected to the dashboard
```

GOOD:
```gherkin
When the user enters a valid username
And the user enters a valid password
Then the Products page is displayed
```

If the ACs DO quote a specific value (e.g. `'Thank you for your order!'`),
that exact quoted value must be used in the Gherkin.

### Page / Element Names
Only page names and element labels explicitly present in the Requirement
Analysis output may appear in Gherkin steps.

### Gherkin Format
Every scenario string must start with `Scenario: <title>`, steps must be
2-space indented, and only Given / When / Then / And keywords may be used.
The `Feature:` line must never be included.

---

## 3. Step Interpretation (`step_interpreter_prompt.txt`)

### Navigate Rule (non-negotiable)
The `value` field for every `navigate` action MUST be `""` (empty string).
Never set it to a URL, `__READ_FROM_PAGE__`, or any other text. The executor
reads `START_URL` from the environment and navigates there automatically.

### Type Value Rule
| Gherkin phrasing | `value` to use |
|---|---|
| Quotes a specific value, e.g. `enters "Acme Corp"` | Use that exact value |
| Generic valid, e.g. `a valid username` | `__READ_FROM_PAGE__` |
| Generic invalid, e.g. `an invalid password` | `__INVALID_VALUE__` |

Never invent values such as `standard_user`, `admin`, `Password123`,
`test@test.com`, or any sample data not present in the Gherkin.

### Verify Value Rule
The `value` for a `verify` step must be the exact text expected on screen,
as quoted in the Gherkin. Never invent expected text.

### Wait Steps
- Add `wait` (value `"2"`) after every `navigate`.
- Add `wait` (value `"1"`) before every `verify`.
- Add `wait` (value `"2"`) after every form-submit click.

### Do Not Invent
- No CSS selectors or element refs in `target` (e.g. `#username`, `.btn-primary`).
- No page names not present in the Gherkin.

---

## 4. Element Location (`element_locator_prompt.txt`)

### Ref Must Exist in Snapshot
The `ref` value returned by the model MUST appear verbatim in the PAGE
SNAPSHOT as the text `[ref=XXX]`. The model must scan the snapshot line by
line before answering.

If no matching `[ref=XXX]` is found, the model must return:
```json
{"ref": null, "confidence": "none"}
```

A wrong ref causes a misclick or incorrect interaction. Returning `null`
causes the executor to retry with a fresh snapshot — this is always safer.

### Ranking Criteria
1. Exact label match
2. Semantic similarity to target description
3. Correct element role for the action
4. Proximity to related labels
5. Visibility in snapshot

---

## Why These Rules Exist

Without these guardrails, the LLM exhibits the following failure modes:

| Failure | Example | Effect |
|---|---|---|
| Invents credentials | `"standard_user"` / `"secret_sauce"` | Login fails with wrong credentials |
| Invents page name | `"dashboard"` instead of `"Products page"` | Verify step always fails |
| Puts URL in navigate value | `"https://..."` in navigate `value` | Executor navigates to wrong URL |
| Invents element ref | `ref="e99"` not in snapshot | Click on non-existent element |
| Pads risks with boilerplate | "network failures", "browser compat" | Irrelevant test scenarios generated |

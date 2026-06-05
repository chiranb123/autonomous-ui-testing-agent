"""
HTML Report Generator
Produces a self-contained dashboard.html with:
  - Summary stats (passed/failed/total/duration)
  - Per-scenario cards with status badge
  - Per-step table with status icon and embedded screenshot
"""

import base64
from datetime import datetime
from pathlib import Path


def _b64(path: str | None) -> str | None:
    """Return base64-encoded PNG, or None if path missing."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return base64.b64encode(p.read_bytes()).decode()


def _status_badge(status: str) -> str:
    colours = {
        "PASSED":  "success",
        "FAILED":  "danger",
        "SKIPPED": "secondary",
        "INFO":    "info",
    }
    c = colours.get(status.upper(), "light")
    return f'<span class="badge bg-{c}">{status}</span>'


def _step_icon(status: str) -> str:
    icons = {
        "PASSED":  "✅",
        "FAILED":  "❌",
        "SKIPPED": "⏭",
        "INFO":    "ℹ️",
    }
    return icons.get(status.upper(), "•")


def generate(
    results: list,
    github_issue: object | None = None,
    start_url: str = "",
    output_path: str | None = None,
) -> str:
    """
    Build and write the HTML report.
    Returns the path of the generated file.
    """

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    report_dir = Path("evidence/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        output_path = str(report_dir / f"report_{timestamp}.html")

    total   = len(results)
    passed  = sum(1 for r in results if r.status == "PASSED")
    failed  = total - passed
    duration = sum(getattr(r, "duration_seconds", 0) for r in results)
    pass_rate = round((passed / total * 100) if total else 0, 1)

    # ── Scenario cards ───────────────────────────────────────────────
    scenario_cards = []
    for idx, result in enumerate(results):
        border = "success" if result.status == "PASSED" else "danger"

        # Final screenshot
        final_b64 = _b64(result.screenshot_path)
        final_img = (
            f'<img src="data:image/png;base64,{final_b64}" '
            f'class="img-fluid rounded border mt-2" '
            f'alt="Final screenshot" style="max-height:400px;">'
            if final_b64 else
            '<p class="text-muted small">No screenshot</p>'
        )

        # Step rows
        step_rows = ""
        for si, step in enumerate(getattr(result, "step_results", []), 1):
            shot_b64 = _b64(getattr(step, "screenshot_path", None))
            thumb = (
                f'<img src="data:image/png;base64,{shot_b64}" '
                f'class="img-thumbnail" style="max-height:80px;cursor:pointer;" '
                f'data-bs-toggle="modal" data-bs-target="#modal-{idx}-{si}">'
                if shot_b64 else "—"
            )

            # Modal for full-size step screenshot
            modal = ""
            if shot_b64:
                modal = f"""
                <div class="modal fade" id="modal-{idx}-{si}" tabindex="-1">
                  <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                      <div class="modal-header">
                        <h6 class="modal-title">Step {si}: {step.action} — {step.target}</h6>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                      </div>
                      <div class="modal-body text-center">
                        <img src="data:image/png;base64,{shot_b64}" class="img-fluid">
                      </div>
                    </div>
                  </div>
                </div>"""

            step_rows += f"""
            <tr>
              <td class="text-center">{si}</td>
              <td><code>{step.action}</code></td>
              <td>{step.target}</td>
              <td>{step.value}</td>
              <td>{_step_icon(step.status)} {_status_badge(step.status)}</td>
              <td class="small text-muted">{step.message}</td>
              <td class="text-center">{thumb}</td>
            </tr>
            {modal}
            """

        error_row = ""
        if result.error_message:
            error_row = f"""
            <div class="alert alert-danger py-2 mt-2">
              <strong>Error:</strong> {result.error_message}
            </div>"""

        card = f"""
        <div class="card border-{border} mb-4">
          <div class="card-header d-flex justify-content-between align-items-center">
            <strong>#{idx+1} {result.scenario_name}</strong>
            <div>
              {_status_badge(result.status)}
              <span class="text-muted small ms-2">⏱ {getattr(result,'duration_seconds',0):.1f}s</span>
            </div>
          </div>
          <div class="card-body p-0">
            {error_row}
            <div class="table-responsive">
              <table class="table table-sm table-hover mb-0">
                <thead class="table-light">
                  <tr>
                    <th>#</th><th>Action</th><th>Target</th>
                    <th>Value</th><th>Status</th><th>Message</th><th>Screenshot</th>
                  </tr>
                </thead>
                <tbody>
                  {step_rows}
                </tbody>
              </table>
            </div>
            <div class="p-3">
              <p class="mb-1 fw-semibold small text-muted">Final Screenshot</p>
              {final_img}
            </div>
          </div>
        </div>
        """
        scenario_cards.append(card)

    # ── GitHub issue section ──────────────────────────────────────────
    issue_section = ""
    if github_issue:
        issue_section = f"""
        <div class="card mb-4">
          <div class="card-header"><strong>📋 GitHub Issue</strong></div>
          <div class="card-body">
            <p><strong>#{github_issue.number}</strong> — {github_issue.title}</p>
            <pre class="bg-light p-2 rounded small">{github_issue.body}</pre>
          </div>
        </div>"""

    # ── HTML ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test Report — {now.strftime('%Y-%m-%d %H:%M')}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background:#f8f9fa; }}
  .stat-card {{ border-radius:12px; padding:20px 24px; color:#fff; }}
  .stat-card h2 {{ font-size:2.5rem; font-weight:700; margin:0; }}
  .stat-card p  {{ margin:0; opacity:.85; }}
  pre {{ white-space: pre-wrap; word-break: break-word; }}
</style>
</head>
<body>
<div class="container-fluid py-4">

  <!-- Header -->
  <div class="d-flex justify-content-between align-items-start mb-4">
    <div>
      <h2 class="mb-0">🤖 Autonomous UI Test Report</h2>
      <p class="text-muted mb-0">{now.strftime('%A, %d %B %Y %H:%M:%S')} &nbsp;|&nbsp; Target: <code>{start_url}</code></p>
    </div>
  </div>

  <!-- Dashboard Cards -->
  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <div class="stat-card bg-primary h-100">
        <h2>{total}</h2><p>Total Scenarios</p>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-success h-100">
        <h2>{passed}</h2><p>Passed</p>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-danger h-100">
        <h2>{failed}</h2><p>Failed</p>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-info h-100">
        <h2>{pass_rate}%</h2><p>Pass Rate &nbsp;|&nbsp; {duration:.1f}s total</p>
      </div>
    </div>
  </div>

  <!-- Progress bar -->
  <div class="progress mb-4" style="height:16px;border-radius:8px;">
    <div class="progress-bar bg-success" style="width:{pass_rate}%">{pass_rate}%</div>
    <div class="progress-bar bg-danger"  style="width:{100-pass_rate}%"></div>
  </div>

  {issue_section}

  <!-- Scenario Cards -->
  {''.join(scenario_cards)}

</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


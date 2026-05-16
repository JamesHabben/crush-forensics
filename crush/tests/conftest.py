# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration: fixture corpus integrity + forensic audit report.

Two responsibilities:
  1. Verify SHA-256 checksums of committed test-evidence files before any test
     runs.  If a fixture has been tampered with the entire session is aborted.
  2. Collect results of @pytest.mark.forensic-tagged tests and generate a
     human-readable audit report at reports/forensic_audit.html.
"""
from __future__ import annotations

import datetime
import hashlib
import html as _html
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Forensic category metadata (order + intro text shown in the report)
# ---------------------------------------------------------------------------

_CATEGORY_ORDER = [
    "Source Immutability",
    "No Side Effects",
    "Read-only Media",
    "Known-output Verification",
    "Reproducibility",
]

_CATEGORY_INTROS: dict[str, str] = {
    "Source Immutability": (
        "The tool must never modify digital evidence it reads. "
        "These tests verify that after any VFS read operation the source data is "
        "byte-identical to its pre-examination state."
    ),
    "No Side Effects": (
        "Parsing an artifact must not create additional files next to the evidence. "
        "Sibling files such as SQLite WAL or journal entries would alter the "
        "evidence directory and compromise the examination."
    ),
    "Read-only Media": (
        "The tool must operate correctly when evidence has read-only permissions "
        "(chmod 0o444 / 0o555), simulating examination of write-protected forensic media."
    ),
    "Known-output Verification": (
        "Committed reference artifacts must parse to their exact, pre-computed values. "
        "These are fixed-point checks: if parser output changes for a known input, "
        "the test fails."
    ),
    "Reproducibility": (
        "Parsing the same artifact twice must produce identical results. "
        "Non-deterministic output would undermine the reliability of forensic findings."
    ),
}

# Module-level state populated by the hooks below
_forensic_items: dict[str, dict[str, str]] = {}
_forensic_results: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Corpus integrity check + marker registration
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pytest_configure(config: pytest.Config) -> None:
    """Register the forensic marker and abort if any fixture file was tampered with."""
    config.addinivalue_line(
        "markers",
        "forensic(category, desc): mark test as a forensic integrity check",
    )

    checksums_path = FIXTURES_DIR / "checksums.json"
    if not checksums_path.exists():
        return

    expected: dict[str, str] = json.loads(checksums_path.read_text())
    failures: list[str] = []

    for name, digest in expected.items():
        fpath = FIXTURES_DIR / name
        if not fpath.exists():
            failures.append(f"  MISSING   {name}")
            continue
        actual = _sha256(fpath)
        if actual != digest:
            failures.append(
                f"  TAMPERED  {name}\n"
                f"    expected: {digest}\n"
                f"    actual:   {actual}"
            )

    if failures:
        pytest.exit(
            "Fixture corpus integrity check FAILED — "
            "committed test evidence has been modified:\n" + "\n".join(failures),
            returncode=3,
        )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def realm_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal.realm placed in tmp_path."""
    src = FIXTURES_DIR / "minimal.realm"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def sqlite_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal.sqlite placed in tmp_path."""
    src = FIXTURES_DIR / "minimal.sqlite"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def plist_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal_binary.plist placed in tmp_path."""
    src = FIXTURES_DIR / "minimal_binary.plist"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def zip_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal.zip placed in tmp_path."""
    src = FIXTURES_DIR / "minimal.zip"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def tar_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal.tar.gz placed in tmp_path."""
    src = FIXTURES_DIR / "minimal.tar.gz"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


@pytest.fixture
def segb_fixture(tmp_path: Path) -> Path:
    """Writable copy of minimal.segb2 placed in tmp_path."""
    src = FIXTURES_DIR / "minimal.segb2"
    dst = tmp_path / src.name
    dst.write_bytes(src.read_bytes())
    return dst


# ---------------------------------------------------------------------------
# Forensic report: collect results during the run
# ---------------------------------------------------------------------------

def pytest_collection_finish(session: pytest.Session) -> None:
    for item in session.items:
        marker = item.get_closest_marker("forensic")
        if marker is not None:
            _forensic_items[item.nodeid] = {
                "category": str(marker.kwargs.get("category", "Uncategorized")),
                "desc": str(marker.kwargs.get("desc", item.name)),
                "name": item.name,
            }


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    nodeid = report.nodeid
    if nodeid not in _forensic_items:
        return
    # Skips are reported during setup; everything else at call time
    if report.when == "setup" and report.skipped:
        outcome, reason = "skipped", str(getattr(report, "wasxfail", "")) or "skipped"
    elif report.when == "call":
        if report.passed:
            outcome, reason = "passed", ""
        elif report.skipped:
            outcome, reason = "skipped", ""
        else:
            outcome, reason = "failed", str(report.longrepr) if report.longrepr else ""
    else:
        return

    _forensic_results.append({
        **_forensic_items[nodeid],
        "outcome": outcome,
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# Forensic report: generate HTML on session finish
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    if not _forensic_results:
        return
    output_path = Path(str(session.config.rootdir)) / "reports" / "forensic_audit.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_report(), encoding="utf-8")
    print(f"\n  Forensic audit report -> {output_path}")

    # Write a Markdown summary to the GitHub Actions job summary page when running in CI
    gha_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gha_summary:
        Path(gha_summary).open("a", encoding="utf-8").write(_render_gha_summary())


def _render_gha_summary() -> str:
    passed = sum(1 for r in _forensic_results if r["outcome"] == "passed")
    failed = sum(1 for r in _forensic_results if r["outcome"] == "failed")
    skipped = sum(1 for r in _forensic_results if r["outcome"] == "skipped")
    overall = "PASS" if failed == 0 else "FAIL"
    icon = "white_check_mark" if failed == 0 else "x"

    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in _CATEGORY_ORDER}
    for r in _forensic_results:
        cat = r["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(r)

    rows = ""
    for category in _CATEGORY_ORDER:
        results = by_cat.get(category, [])
        if not results:
            continue
        c_pass = sum(1 for r in results if r["outcome"] == "passed")
        c_fail = sum(1 for r in results if r["outcome"] == "failed")
        c_skip = sum(1 for r in results if r["outcome"] == "skipped")
        cat_icon = ":white_check_mark:" if c_fail == 0 else ":x:"
        counts = f"{c_pass} passed"
        if c_fail:
            counts += f", {c_fail} failed"
        if c_skip:
            counts += f", {c_skip} skipped"
        rows += f"| {cat_icon} {category} | {counts} |\n"

    return (
        f"\n## :{icon}: Forensic Integrity Audit &mdash; {overall}\n\n"
        f"| Category | Result |\n"
        f"|---|---|\n"
        f"{rows}\n"
        f"**{passed} passed &nbsp;·&nbsp; {failed} failed &nbsp;·&nbsp; {skipped} skipped**\n\n"
        f"> Full report available as the `forensic-test-report` CI artifact.\n"
    )


def _render_report() -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    python_ver = sys.version.split()[0]

    passed = sum(1 for r in _forensic_results if r["outcome"] == "passed")
    failed = sum(1 for r in _forensic_results if r["outcome"] == "failed")
    skipped = sum(1 for r in _forensic_results if r["outcome"] == "skipped")
    total = len(_forensic_results)
    overall = "PASS" if failed == 0 else "FAIL"
    ov_cls = "pass" if failed == 0 else "fail"

    # Group by category, preserving defined order
    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in _CATEGORY_ORDER}
    for r in _forensic_results:
        cat = r["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(r)

    sections = ""
    for category in _CATEGORY_ORDER:
        results = by_cat.get(category, [])
        if not results:
            continue
        c_pass = sum(1 for r in results if r["outcome"] == "passed")
        c_fail = sum(1 for r in results if r["outcome"] == "failed")
        c_skip = sum(1 for r in results if r["outcome"] == "skipped")
        badge_cls = "pass" if c_fail == 0 else "fail"
        badge_txt = "PASS" if c_fail == 0 else "FAIL"
        counter = f"{c_pass}&#10003;"
        if c_fail:
            counter += f"&nbsp; {c_fail}&#10007;"
        if c_skip:
            counter += f"&nbsp; {c_skip}&ndash;"
        intro = _html.escape(_CATEGORY_INTROS.get(category, ""))
        rows = ""
        for r in results:
            oc = r["outcome"]
            rows += (
                f'<tr class="row-{oc}">'
                f'<td class="cell-status status-{oc}">{oc.upper()}</td>'
                f'<td class="cell-desc">{_html.escape(r["desc"])}</td>'
                f'<td class="cell-fn">{_html.escape(r["name"])}</td>'
                f"</tr>\n"
            )
        sections += f"""
<section>
  <div class="cat-header">
    <h2>{_html.escape(category)}</h2>
    <span class="badge {badge_cls}">{badge_txt}</span>
    <span class="cat-count">{counter}</span>
  </div>
  <p class="cat-intro">{intro}</p>
  <table>
    <thead><tr>
      <th class="col-status">Result</th>
      <th class="col-desc">Forensic Property Verified</th>
      <th class="col-fn">Test Function</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""

    # Reference corpus section
    checksums_path = FIXTURES_DIR / "checksums.json"
    corpus_rows = ""
    if checksums_path.exists():
        checksums: dict[str, str] = json.loads(checksums_path.read_text())
        for name, digest in sorted(checksums.items()):
            fpath = FIXTURES_DIR / name
            size = fpath.stat().st_size if fpath.exists() else 0
            corpus_rows += (
                f"<tr>"
                f'<td class="cell-fn">{_html.escape(name)}</td>'
                f'<td class="cell-hash">{digest}</td>'
                f'<td class="cell-size">{size:,}&thinsp;B</td>'
                f"</tr>\n"
            )
    corpus = f"""
<section>
  <div class="cat-header">
    <h2>Reference Corpus</h2>
    <span class="badge pass">VERIFIED</span>
  </div>
  <p class="cat-intro">
    SHA-256 checksums of the committed test-evidence files.
    The corpus integrity check runs before the first test and aborts the session
    if any file has been modified.
  </p>
  <table>
    <thead><tr>
      <th class="col-fn">File</th>
      <th class="col-hash">SHA-256</th>
      <th class="col-size" style="text-align:right">Size</th>
    </tr></thead>
    <tbody>{corpus_rows}</tbody>
  </table>
</section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Crush &mdash; Forensic Integrity Audit</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         font-size:14px;color:#1a1a2e;background:#f0f2f5}}
    a{{color:inherit}}
    header{{background:#1a1a2e;color:#fff;padding:24px 32px 20px}}
    header h1{{font-size:20px;font-weight:600;letter-spacing:.3px}}
    .meta{{margin-top:5px;font-size:12px;opacity:.65}}
    .overall{{display:inline-flex;align-items:center;gap:12px;
              margin-top:14px;background:rgba(255,255,255,.08);
              padding:8px 16px;border-radius:6px}}
    .verdict{{font-size:18px;font-weight:700;letter-spacing:1px}}
    .verdict.pass{{color:#4ade80}}.verdict.fail{{color:#f87171}}
    .counts{{font-size:12px;opacity:.75}}
    main{{max-width:960px;margin:0 auto;padding:24px 16px 40px}}
    section{{background:#fff;border-radius:8px;padding:20px 24px;
             margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    .cat-header{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
    .cat-header h2{{font-size:15px;font-weight:600}}
    .cat-count{{font-size:12px;color:#666}}
    .badge{{font-size:11px;font-weight:700;letter-spacing:.4px;
            padding:2px 8px;border-radius:4px}}
    .badge.pass{{background:#dcfce7;color:#166534}}
    .badge.fail{{background:#fee2e2;color:#991b1b}}
    .cat-intro{{font-size:13px;color:#555;line-height:1.55;margin-bottom:14px}}
    table{{width:100%;border-collapse:collapse}}
    th{{text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;
        letter-spacing:.5px;color:#999;padding:6px 10px;
        border-bottom:2px solid #e5e7eb}}
    td{{padding:8px 10px;border-bottom:1px solid #f3f4f6;vertical-align:top}}
    tr:last-child td{{border-bottom:none}}
    .col-status{{width:68px}}.col-fn{{width:260px}}
    .cell-status{{font-weight:700;font-size:11px;letter-spacing:.5px}}
    .status-passed{{color:#16a34a}}.status-failed{{color:#dc2626}}
    .status-skipped{{color:#9ca3af}}
    .cell-fn{{font-family:"SF Mono","Fira Code",monospace;font-size:12px;color:#6366f1}}
    .cell-hash{{font-family:"SF Mono","Fira Code",monospace;font-size:11px;
               color:#888;word-break:break-all}}
    .cell-size{{text-align:right;color:#888;font-size:12px;white-space:nowrap}}
    .row-failed{{background:#fff5f5}}.row-skipped td{{opacity:.55}}
    footer{{text-align:center;font-size:11px;color:#bbb;padding:0 0 24px}}
  </style>
</head>
<body>
<header>
  <h1>Crush &mdash; Forensic Integrity Audit Report</h1>
  <div class="meta">Generated: {now}&nbsp;&nbsp;|&nbsp;&nbsp;Python {python_ver}</div>
  <div class="overall">
    <span class="verdict {ov_cls}">{overall}</span>
    <span class="counts">
      {passed} passed &nbsp;&middot;&nbsp;
      {failed} failed &nbsp;&middot;&nbsp;
      {skipped} skipped &nbsp;&middot;&nbsp;
      {total} total
    </span>
  </div>
</header>
<main>
{sections}
{corpus}
</main>
<footer>crush-forensics &nbsp;&middot;&nbsp; forensic audit report &nbsp;&middot;&nbsp; {now}</footer>
</body>
</html>"""

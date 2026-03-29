#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""
auto_test_after_edit.py — PostToolUse hook
Runs checks after Edit/Write/MultiEdit. Silent on pass — only prints failures/warnings.
Logs test pass/fail to edit log so Stop hook can read result without re-running.

Checks:
  .py   → syntax + lint + mypy + tests + debug code + secrets + coverage gaps + TODOs + large edits
  .sh   → bash -n syntax
  .json → json parse
  .js   → node --check
  other → skip silently
"""

import json
import re as _re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_EDIT_LOG_DIR = Path("/tmp")

_PROJECT = Path.home() / "telegram-claude-bot"
_MODEL_PATTERNS = [
    "MiniMax-M2.5", "MiniMax-M2.7", "kimi-k2", "deepseek-chat",
    "llama-3.3-70b", "gemini-2.0-flash", "qwen3-32b",
]

_DEBUG_RE = _re.compile(
    r'^\s*(print\s*\(|pdb\.set_trace\s*\(\)|breakpoint\s*\(\)|import pdb\b)',
    _re.MULTILINE
)

_SECRET_PATTERNS = [
    (_re.compile(r'(?i)(api[_\-]?key|secret[_\-]?key|password|passwd|auth[_\-]?token)\s*=\s*["\'][^"\']{8,}["\']'), "hardcoded credential"),
    (_re.compile(r'sk-[a-zA-Z0-9]{20,}'), "API key pattern"),
    (_re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub token"),
    (_re.compile(r'xox[bpoa]-[a-zA-Z0-9\-]+'), "Slack token"),
]
_SECRET_SKIP = _re.compile(r'(?i)(example|placeholder|your[_\-]|changeme|xxx|dummy|fake|test_)')


def _edit_log_path(session_id: str | None) -> Path:
    if session_id:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return _EDIT_LOG_DIR / f"claude_edits_{safe}.json"
    return _EDIT_LOG_DIR / "claude_edits_this_turn.json"


def run(cmd, timeout=15, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s"
    except FileNotFoundError:
        return None, f"Command not found: {cmd[0]}"


def _run_tests(test_file: Path, timeout: int = 30) -> tuple[bool, str]:
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        capture_output=True, timeout=5
    )
    if probe.returncode == 0:
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-x", "-q", "--tb=short"]
    else:
        cmd = [sys.executable, "-m", "unittest", "discover",
               "-s", str(test_file.parent), "-p", test_file.name, "-v"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def find_test_file(file_path: Path):
    name = file_path.stem
    parent = file_path.parent
    for c in [
        parent / f"test_{name}.py",
        parent / "tests" / f"test_{name}.py",
        parent.parent / "tests" / f"test_{name}.py",
    ]:
        if c.exists():
            return c
    return None


# ── New checks ─────────────────────────────────────────────────────────────────

def check_debug_code(file_path: Path, content: str) -> list[str]:
    """Detect debug statements left in code."""
    matches = _DEBUG_RE.findall(content)
    unique = list(dict.fromkeys(m.strip() for m in matches))
    if unique:
        return [f"⚠️  Debug code in {file_path.name}: {', '.join(unique[:3])}"]
    return []


def check_secrets(file_path: Path, content: str) -> list[str]:
    """Detect hardcoded credentials. Skips test files and obvious placeholders."""
    if file_path.name.startswith("test_") or "_test.py" in file_path.name:
        return []
    found = []
    for pattern, label in _SECRET_PATTERNS:
        for match in pattern.finditer(content):
            if not _SECRET_SKIP.search(match.group()):
                found.append(label)
                break
    if found:
        return [f"🔐 Possible secret in {file_path.name}: {', '.join(found)}"]
    return []


def check_function_coverage(file_path: Path) -> list[str]:
    """Report functions that exist but have no corresponding test."""
    try:
        from test_helpers import find_test_file as ftf, check_test_coverage, should_require_tests
        if not should_require_tests(file_path):
            return []
        test_file = ftf(file_path)
        if not test_file:
            return []
        coverage = check_test_coverage(file_path, test_file)
        if coverage["missing"]:
            funcs = ", ".join(coverage["missing"][:5])
            extra = f" (+{len(coverage['missing']) - 5} more)" if len(coverage["missing"]) > 5 else ""
            return [f"⚠️  Untested in {file_path.name}: {funcs}{extra}"]
    except Exception:
        pass
    return []


def check_todos_added(file_path: Path) -> list[str]:
    """Flag newly added TODO/FIXME/HACK lines (via git diff)."""
    try:
        ok, out = run(
            ["git", "diff", "HEAD", "--", str(file_path)],
            timeout=5, cwd=str(file_path.parent)
        )
        new_todos = [
            line[1:].strip() for line in out.splitlines()
            if line.startswith("+") and not line.startswith("+++")
            and any(kw in line.upper() for kw in ("# TODO", "# FIXME", "# HACK", "# XXX"))
        ]
        if new_todos:
            first = new_todos[0][:80]
            extra = f" (+{len(new_todos) - 1} more)" if len(new_todos) > 1 else ""
            return [f"📝 New TODO/FIXME in {file_path.name}: {first}{extra}"]
    except Exception:
        pass
    return []


def check_large_edit(file_path: Path) -> list[str]:
    """Warn if a single edit changes > 150 lines."""
    try:
        ok, out = run(
            ["git", "diff", "HEAD", "--", str(file_path)],
            timeout=5, cwd=str(file_path.parent)
        )
        added = sum(1 for l in out.splitlines() if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in out.splitlines() if l.startswith("-") and not l.startswith("---"))
        if added + removed > 150:
            return [f"📏 Large edit: +{added}/-{removed} lines in {file_path.name}"]
    except Exception:
        pass
    return []


# ── Core checks ────────────────────────────────────────────────────────────────

def check_python(file_path: Path) -> tuple[list[str], bool | None]:
    """Returns (warnings/errors, tests_passed). Silent on clean pass."""
    errors = []
    tests_passed = None

    # Hook reload nudge
    hooks_dir = Path.home() / ".claude" / "hooks"
    if file_path.parent == hooks_dir or (
        str(file_path).startswith(str(_PROJECT / "hooks")) and file_path.suffix == ".py"
    ):
        errors.append("⚠️  Hook file edited — /clear or new session to pick up changes.")

    # Hardcoded model names
    if file_path.name != "llm_client.py" and str(file_path).startswith(str(_PROJECT)):
        try:
            content = file_path.read_text()
            found = [m for m in _MODEL_PATTERNS if m in content]
            if found:
                errors.append(f"⚠️  Hardcoded model(s) in {file_path.name}: {', '.join(found)}")
        except Exception:
            pass

    # Syntax — stop on failure
    ok, out = run([sys.executable, "-m", "py_compile", str(file_path)])
    if ok is False:
        errors.append(f"❌ Syntax error in {file_path.name}:\n{out}")
        return errors, False

    try:
        content = file_path.read_text()
    except Exception:
        return errors, tests_passed

    # New checks (fast, content-based)
    errors += check_debug_code(file_path, content)
    errors += check_secrets(file_path, content)
    errors += check_todos_added(file_path)
    errors += check_large_edit(file_path)

    # Lint (skip E501 noise)
    ok, out = run(["ruff", "check", "--select=E,F,W,B,C4,SIM,RUF", str(file_path)])
    if ok is False:
        issues = [l for l in out.splitlines() if "E501" not in l and l.strip()]
        if issues:
            errors.append(f"⚠️  Lint in {file_path.name}:\n" + "\n".join(issues[:15]))

    # Mypy
    ok, out = run(
        ["mypy", "--ignore-missing-imports", "--no-error-summary", str(file_path)],
        timeout=20,
    )
    if ok is False and out:
        errs = [l for l in out.splitlines() if ": error:" in l]
        if errs:
            errors.append(f"⚠️  Type errors in {file_path.name}:\n" + "\n".join(errs[:10]))

    # Coverage gaps (functions with no tests)
    errors += check_function_coverage(file_path)

    # Run tests
    test_file = find_test_file(file_path)
    if test_file:
        passed, out = _run_tests(test_file)
        tests_passed = passed
        if not passed:
            errors.append(f"❌ Tests FAILED ({test_file.name}):\n{out}")

    return errors, tests_passed


def check_shell(file_path: Path) -> list[str]:
    ok, out = run(["bash", "-n", str(file_path)])
    if ok is False:
        return [f"❌ Shell syntax error in {file_path.name}:\n{out}"]
    return []


def check_json(file_path: Path) -> list[str]:
    try:
        json.loads(file_path.read_text())
        return []
    except json.JSONDecodeError as e:
        return [f"❌ JSON invalid in {file_path.name}: {e}"]
    except Exception as e:
        return [f"⚠️  Could not read {file_path.name}: {e}"]


def check_js(file_path: Path) -> list[str]:
    ok, out = run(["node", "--check", str(file_path)])
    if ok is None or ok:
        return []
    return [f"❌ JS syntax error in {file_path.name}:\n{out}"]


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    session_id = data.get("session_id")
    edit_log = _edit_log_path(session_id)

    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    file_path_str = data.get("tool_input", {}).get("file_path", "")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)
    if not file_path.exists():
        sys.exit(0)

    suffix = file_path.suffix.lower()
    errors = []
    tests_passed = None

    if suffix == ".py":
        errors, tests_passed = check_python(file_path)
    elif suffix == ".sh":
        errors = check_shell(file_path)
    elif suffix == ".json":
        errors = check_json(file_path)
    elif suffix in (".js", ".mjs", ".cjs"):
        errors = check_js(file_path)

    if errors:
        print("\n".join(errors))

    # Log edit + test result for Stop hook
    try:
        from test_helpers import extract_functions, should_require_tests
        funcs = extract_functions(file_path) if suffix == ".py" else []
        needs_tests = should_require_tests(file_path)
    except Exception:
        funcs, needs_tests = [], False

    try:
        existing = json.loads(edit_log.read_text()) if edit_log.exists() else []
        existing.append({
            "file": file_path_str,
            "ts": datetime.now().timestamp(),
            "functions": funcs,
            "needs_tests": needs_tests,
            "tests_passed": tests_passed,
        })
        edit_log.write_text(json.dumps(existing))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()

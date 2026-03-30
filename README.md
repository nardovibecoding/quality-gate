# claude-quality-gate

```bash
claude plugins install nardovibecoding/claude-quality-gate
```

---

<div align="center">

**10 hooks that enforce code quality automatically — tests, patterns, resource leaks, license headers.**

[![hooks](https://img.shields.io/badge/hooks-10-orange?style=for-the-badge)](.)
[![license](https://img.shields.io/badge/license-AGPL--3.0-red?style=for-the-badge)](LICENSE)
[![platform](https://img.shields.io/badge/platform-macOS%20%2B%20Linux-lightgrey?style=for-the-badge)](#)

</div>

Code quality degrades gradually — skipped tests, leaked resources, inconsistent patterns. These hooks enforce your standards automatically on every Claude Code operation, silently in the background.

No VPS required. No MCP server. Just hooks.

---

## Hooks

| Hook | Event | What it does |
|------|-------|-------------|
| `auto_test_after_edit.py` | PostToolUse: Edit/Write | Syntax + lint + mypy + tests after every edit. Silent on pass, loud on failure. Flags debug code, hardcoded secrets, untested functions, large edits |
| `auto_review_before_done.py` | Stop | Reads test results, checks caller impact, schema migrations, config drift. Blocks if tests fail |
| `hardcoded_model_guard.py` | PostToolUse: Edit/Write | Prevents model names being hardcoded outside the single config file |
| `async_safety_guard.py` | PostToolUse: Edit/Write | Catches async pitfalls — missing await, sync calls in async context |
| `resource_leak_guard.py` | PostToolUse: Edit/Write | Detects unclosed file handles, DB connections, HTTP sessions |
| `temp_file_guard.py` | PostToolUse: Edit/Write | Warns when /tmp files are created but not cleaned up |
| `unicode_grep_warn.py` | PostToolUse: Edit/Write | Catches grep calls that silently fail on Unicode/CJK content |
| `pre_commit_validate.py` | PostToolUse: Bash | Validates Python syntax after git commit |
| `auto_copyright_header.py` | PreToolUse: Edit/Write | Ensures copyright header on new source files |
| `auto_license.py` | PostToolUse: Edit/Write | Auto-setup license on new repos after `gh repo create` |

---

## Install

```bash
claude plugins install nardovibecoding/claude-quality-gate
```

Or manually — clone and add to `~/.claude/settings.json`:

```json
{
  "plugins": ["~/claude-quality-gate"]
}
```

---

## Related

- [claude-sec-ops-guard](https://github.com/nardovibecoding/claude-sec-ops-guard) — 27 hooks + 28 MCP tools for security enforcement and ops automation

---

## License

AGPL-3.0 — Copyright (c) 2026 Nardo (nardovibecoding)

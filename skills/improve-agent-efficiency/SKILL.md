---
name: improve-agent-efficiency
description: Indexes conversation telemetry (hardware token counts, inference turns, tool failures, and search-to-edit thrash) across sessions so the agent can inspect outlier transcripts and recommend first-principles improvements.
---

# Improve Agent Efficiency

This skill indexes objective telemetry from Antigravity `transcript.jsonl` logs and directs the agent to inspect outlier sessions directly. The script acts strictly as a neutral telemetry indexer; diagnosis and recommendations are performed dynamically by the agent from first principles.

---

## 1. Run the Telemetry Indexer

Execute `scripts/audit_trajectories.py` to aggregate hardware token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`), inference turns, tool call errors (across both shell commands and file/edit tools), and search-to-edit ratios. Output is written to the system temp directory (`$env:TEMP\agy_telemetry\telemetry_summary.json`) so repository roots are never polluted.

```pwsh
$Script = "$HOME\.gemini\config\skills\improve-agent-efficiency\scripts\audit_trajectories.py"
py -3.10 $Script --limit 100
```

### Optional Flags
- `--since YYYY-MM-DD`: Filter sessions modified on or after date.
- `--compare`: Partition sessions at `--since` (defaults to 24h ago) to compare recent sessions against prior baseline.
- `--repo <substring>`: Filter to sessions matching a repository name.
- `--exclude <name1,name2>`: Exclude specific repositories.
- `--limit <N>` / `--all`: Control how many recent sessions to index (default: 100).

---

## 2. Inspect Outliers & Diagnose from First Principles

Read `$env:TEMP\agy_telemetry\telemetry_summary.json` and review the flagged outlier sessions (`top_cost_sessions`, `top_thrash_sessions`, and `recent_error_chains`).

For the highest-signal outlier sessions, read the relevant step ranges in `<appDataDir>/brain/<conversation_id>/.system_generated/logs/transcript.jsonl` and evaluate:

1. **Context & Turn Multiplication:**
   Identify what caused excessive `PLANNER_RESPONSE` turns per user prompt (e.g., fragmented file reads, avoidable two-step scratch script writes, or lack of codebase orientation).
2. **True Tool Friction vs. Normal Engineering:**
   Separate normal red-green test/build cycles from avoidable friction (broken shell syntax, failed `edit_file` target matches, wrong working directories, or missing CLI tools).
3. **Rule ROI & Pruning:**
   Check whether existing rules in `~/.gemini/config/GEMINI.md` or `<repo_root>/AGENTS.md` are actively causing extra turns, tool errors, or prompt bloat. Recommend **removing or simplifying rules** whenever a rule imposes more turn overhead than it saves.

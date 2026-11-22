---
name: improve-agent-efficiency
description: Indexes conversation telemetry (hardware token counts, parent-child subagent trees, functional domain cost centers, two-turn scratch loops, async manage_task polling waste, output truncation cascades, and tool errors) across sessions so the agent can inspect outlier transcripts and recommend first-principles improvements.
---

# Improve Agent Efficiency

This skill indexes objective telemetry from Antigravity `transcript.jsonl` logs, reconstructs parent-child subagent DAGs (`invoke_subagent`), classifies turns into functional cost-center domains, and directs the agent to inspect outlier sessions and trees directly.

---

## 1. Run the Telemetry Indexer

Execute `scripts/audit_trajectories.py` to aggregate hardware token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`), parent-child subagent tree rollups (`tree_total_tokens`), functional domain distributions, two-turn scratch script loops (`write_then_run_pairs`), async backgrounding and `manage_task` polling waste (`async_polling_tokens`), truncated output reads (`step_output_file_reads`), and tool call errors. Output is written to the system temp directory (`$env:TEMP\agy_telemetry\telemetry_summary.json`) so repository roots are never polluted.

```pwsh
$Script = "$HOME\.gemini\config\skills\improve-agent-efficiency\scripts\audit_trajectories.py"
python $Script --limit 100
```

### Optional Flags
- `--since YYYY-MM-DD`: Filter sessions modified on or after date.
- `--compare`: Partition sessions at `--since` (defaults to 24h ago) to compare recent sessions against prior baseline.
- `--repo <substring>`: Filter to sessions matching a repository name.
- `--exclude <name1,name2>`: Exclude specific repositories.
- `--limit <N>` / `--all`: Control how many recent sessions to index (default: 100).

---

## 2. Inspect Outliers & Diagnose from First Principles

Read `$env:TEMP\agy_telemetry\telemetry_summary.json` and review the flagged outlier cohorts:
- `top_cost_trees`: Root sessions ranked by combined parent + child subagent tokens (`tree_total_tokens`).
- `top_cost_sessions`: Individual root or subagent sessions ranked by direct billed tokens.
- `top_thrash_sessions`: Root user sessions with high `turns_per_prompt` and high search-to-edit ratios.
- `top_subagent_sessions`: Highest-cost delegated subagent runs with their extracted delegation roles and briefs.
- `domain_token_distribution`: Macro token allocation across functional cost centers (`cdp_browser_exec`, `cdp_scratch_script_write`, `web_scouting_search_and_probe`, `async_task_polling`, `scratch_and_truncated_log_reads`, `tracking_and_kanban_ops`, `subagent_orchestration`).
- `recent_error_sessions`: Recent command and non-command tool failures.

For the highest-signal outlier sessions, read the relevant step ranges in `<appDataDir>/brain/<conversation_id>/.system_generated/logs/transcript.jsonl` and evaluate:

1. **Subagent Tree vs. Single-Session Context Economics:**
   Compare average tokens per model turn (`avg_tokens_per_model_turn`) and peak context (`peak_context_tokens`) against total turn multiplication across subagent trees (`tree_model_turns`). Identify whether subagents are re-inventing scripts or re-reading large context files from scratch.
2. **Two-Turn Scratch Multiplication (`write_then_run_pairs`):**
   Check if missing CLI flags on workspace tools or restrictive rules are forcing agents to execute two full LLM turns (`write_file("scratch/step.py")` followed by `run_command("python scratch/step.py")`) for routine micro-actions. Recommend declarative batch CLI flags (`--run-actions <json>`) to collapse multi-turn scratch loops into single commands.
3. **Async Timeout Backgrounding & Polling Thrash (`manage_task_polls`):**
   When `backgrounded_commands` and `async_polling_tokens` are elevated, inspect `WaitMsBeforeAsync` values on `run_command` calls. Recommend setting `WaitMsBeforeAsync: 10000` for synchronous scripts and stopping tool calls on backgrounded tasks (relying on reactive system wakeup rather than `manage_task(Action="status")` polling loops).
4. **Output Truncation Cascades (`truncated_tool_outputs` & `step_output_file_reads`):**
   When scripts dump unfiltered HTML/JSON to stdout or scratch files (>46KB), agents execute multi-chunk `read_file` calls on `.system_generated/steps/<N>/output.txt`, permanently inflating the context window to 500k+ tokens. Recommend filtering and bounding CLI outputs (`< 15KB`) inside Python before printing.
5. **Hot-Path vs. Cold-Path Administrative Ceremony (`tracking_and_kanban_ops`):**
   Identify administrative operations (spreadsheet rebuilds, Kanban card movements, email receipt sweeps) executed mid-session inside high-context windows, and recommend deferring them to a one-shot post-batch CLI commit.
6. **Rule ROI & Pruning:**
   Check whether existing rules in `~/.gemini/config/GEMINI.md` or `<repo_root>/AGENTS.md` are actively causing extra turns, tool errors, or prompt bloat. Recommend removing or simplifying rules whenever a rule imposes more turn overhead than it saves.

---
name: trajectory-efficiency-auditor
description: Audits Antigravity conversation trajectories, correlates unlabeled sessions to repositories, analyzes command execution failures, and synthesizes actionable remediation plans across native tools, global rules, and workspace AGENTS.md files.
---

# Trajectory Efficiency Auditor

This skill provides an automated, cross-platform procedure to audit agent conversation histories in Antigravity, discover hidden execution bottlenecks, measure command failure rates, and produce systemic remediation plans.

---

## When to Use This Skill

Activate this skill when:
- Reviewing agent performance across past sessions or repositories.
- Identifying repetitive command retries, syntax errors, or tool quoting collapses.
- Auditing token waste caused by unbounded file reads or command trial-and-error.
- Formulating repository-specific `AGENTS.md` rules or updating global `GEMINI.md` configurations.

---

## Procedure

### Step 1: Execute the Trajectory Auditor Script

Run the bundled, zero-dependency Python script to discover IDE workspaces, scan local Git repositories, parse conversation transcripts, and compute aggregate metrics:

```bash
# Cross-platform execution
python scripts/audit_trajectories.py "<output_directory>"
```

On Windows with PowerShell:
```pwsh
py -3.10 (Join-Path $SkillDir "scripts/audit_trajectories.py") (Get-Location).Path
```

The script outputs `trajectory_audit_summary.json` containing:
- Discovered repositories and IDE workspace access timestamps.
- Unlabeled conversation-to-repository attribution.
- Total command executions, failure counts, and failure rate percentage.
- Categorized error breakdown (quoting errors, encoding traps, missing tools, process locks).

### Step 2: Review Unlabeled Conversation Mapping

Verify conversation-to-repository attribution through the four-stage heuristic, particularly for sessions where IDE synchronization or ad-hoc prompts dropped workspace metadata:
1. **Explicit Workspace Declaration:** Checked `<user_information>` in initial system prompts.
2. **Tool Path Matching:** Longest common path prefix from `Cwd`, `TargetFile`, and `AbsolutePath` arguments.
3. **Prompt Keyword Matching:** Basename repository matching in user input text.
4. **General Environment Clustering:** Sessions modifying operating system configurations or unmanaged scripts.

### Step 3: Classify Execution Friction

Group identified failures into the primary archetypes detailed in:
- [references/remediation_patterns.md](references/remediation_patterns.md)

Common archetypes include:
- **Inline Script Quoting Collapse:** Multi-line `python -c` or `node -e` broken by shell parsing.
- **Console Encoding Trap:** Output streams crashing on non-ASCII characters (`UnicodeEncodeError`).
- **Missing Host Binary:** Model attempting to execute CLI utilities or runtimes absent from PATH.
- **Missing Project Path:** `ModuleNotFoundError` due to unexported virtualenv or source directories.
- **Process Write Lock:** Build failures caused by background daemon or test processes holding open file handles.

### Step 4: Synthesize Tri-Layer Remediation

Translate findings into concrete interventions:

1. **Host Tooling Layer (Zero Token Overhead):**
   - Install missing CLI binaries via native package managers (`winget`, `brew`, `apt`).
   - Set persistent environment variables (e.g. `PYTHONIOENCODING=utf-8`).
2. **Global Rules Layer (`~/.gemini/config/GEMINI.md`):**
   - Enforce the File-First Execution SOP for multi-line scripts.
   - Maintain bounded output limits and bounded file reading constraints.
3. **Workspace Rules Layer (`<repo_root>/AGENTS.md`):**
   - Codify runtime pinning, `$env:PYTHONPATH` exports, solution file targets, and pre-build process hygiene.

### Step 5: Deliver Structured Audit Artifact

Format the results into a markdown artifact containing:
1. Aggregate metrics (total commands, failed commands, failure rate percentage).
2. Per-repository failure breakdown.
3. Master incident table (failed command, root cause, retry sequence, working command).
4. Phased remediation plan for user review.

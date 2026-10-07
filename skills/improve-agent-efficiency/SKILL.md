---
name: improve-agent-efficiency
description: Audits past agent sessions, measures command failure rates, detects syntax collapses and missing tools, and synthesizes actionable remediation plans across native tools, global rules, and workspace AGENTS.md files.
---

# Improve Agent Efficiency

This skill provides an automated, cross-platform procedure to audit agent conversation histories in Antigravity, discover execution bottlenecks, measure command failure rates, and produce systemic remediation plans.

---

## Direct Chat Prompts

When this skill is installed, the user can invoke this workflow directly from the chat interface with prompts such as:
- *"Audit my past sessions and optimize agent rules."*
- *"Check my command failure rate across past trajectories and update workspace AGENTS.md."*
- *"Analyze execution friction across my projects and recommend host tooling fixes."*

---

## Architectural Rationale

This skill splits the auditing process into two distinct phases:

1. **Deterministic Log Extraction (Local Process, Zero Token Cost):**
   Conversation histories are stored as raw JSON Lines files (`transcript.jsonl`). Reading raw transcripts directly into an LLM context window across multiple sessions exhausts context limits, costs excessive tokens, and triggers log truncation. The zero-dependency Python script parses hundreds of raw conversation logs locally in seconds, deduplicates UUIDs across storage locations, maps unlinked sessions to local Git repositories, and outputs a structured summary under 2 KB.

2. **Autonomous Rule Synthesis (LLM Agent Reasoning):**
   The agent reads the compact summary artifact, analyzes the highest-frequency failure patterns, and synthesizes repository-specific `AGENTS.md` and global `GEMINI.md` configurations.

---

## Procedure

### Step 1: Execute the Trajectory Auditor Script

Run the bundled, zero-dependency Python script to discover IDE workspaces, scan local Git repositories, parse conversation transcripts, and compute aggregate metrics:

```bash
# macOS / Linux (POSIX)
python3 scripts/audit_trajectories.py "<output_directory>"
```

```pwsh
# Windows (PowerShell)
py -3.10 (Join-Path $SkillDir "scripts/audit_trajectories.py") (Get-Location).Path
```

The script outputs `trajectory_audit_summary.json` containing:
- Discovered repositories and IDE workspace access timestamps.
- Unlabeled conversation-to-repository attribution.
- Total command executions, failure counts, and failure rate percentage.
- Categorized error breakdown across JavaScript, TypeScript, Python, Go, Rust, .NET, shell parsing, and process locks.

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
- **Inline Script Quoting Collapse:** Multi-line `python -c`, `node -e`, or nested shell commands broken by parser quotation stripping.
- **Console Encoding Trap:** Output streams crashing on non-ASCII characters (`UnicodeEncodeError`).
- **Missing Host Binary:** Model attempting to execute CLI utilities or runtimes absent from PATH.
- **Dependency & Module Resolution Error:** `ModuleNotFoundError`, `ERR_MODULE_NOT_FOUND`, or lockfile mismatch.
- **Process & Port Lock Collision:** Build or server failures caused by active processes holding open file handles or network sockets (`EADDRINUSE`, `CS2012`).
- **POSIX Permission Trap:** Shell scripts executed without executable bits (`+x`) or interpreter prefixes.

### Step 4: Synthesize Tri-Layer Remediation

Translate findings into concrete interventions:

1. **Host Tooling Layer (Zero Token Overhead):**
   - Install missing CLI binaries via native package managers (`winget`, `brew`, `apt`).
   - Set persistent environment variables (e.g. `PYTHONIOENCODING=utf-8`).
2. **Global Rules Layer (`~/.gemini/config/GEMINI.md`):**
   - Enforce the File-First Execution SOP for multi-line scripts.
   - Maintain bounded output limits and bounded file reading constraints.
3. **Workspace Rules Layer (`<repo_root>/AGENTS.md`):**
   - Codify runtime pinning, package manager lockfile enforcement, test targets, and pre-build process hygiene for TypeScript, Python, Go, Rust, or .NET projects.

### Step 5: Deliver Structured Audit Artifact

Format the results into a markdown artifact containing:
1. Aggregate metrics (total commands, failed commands, failure rate percentage).
2. Per-repository failure breakdown.
3. Master incident table (failed command, root cause, retry sequence, working command).
4. Phased remediation plan for user review.

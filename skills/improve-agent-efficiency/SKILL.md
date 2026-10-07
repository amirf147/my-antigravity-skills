---
name: improve-agent-efficiency
description: Probes host development tools, mines causal command failure chains across past agent sessions, and executes verified remediation across host binaries, global rules, and workspace AGENTS.md files.
---

# Improve Agent Efficiency

This skill audits agent conversation histories in Antigravity, detects execution friction and multi-turn retry loops, probes the live host environment for tool discrepancies, and executes verified systemic remediations.

---

## Direct Chat Prompts

The user can invoke this workflow directly from the chat interface with prompts such as:
- *"Audit my past sessions and optimize agent rules."*
- *"Check my command failure rate across past trajectories and update workspace AGENTS.md."*
- *"Analyze execution friction across my projects and recommend host tooling fixes."*
- *"Probe my host environment and identify discrepancies in my agent configuration."*

---

## Architecture: Fast Probing, Causal Mining, and Verified Remediation

The workflow operates across five distinct phases:

1. **Host Environment Probe (Local Script):**
   `scripts/probe_environment.py` inspects the live host runtime, verifies installed CLI binaries (`git`, `gh`, `rg`, `py -3.10`, `dotnet`, `node`, `cargo`), tests standard output stream encoding, and cross-references active rules in `GEMINI.md` to identify false negative claims.

2. **Causal Trajectory Mining (Local Script):**
   `scripts/audit_trajectories.py` parses conversation logs, matches sessions to repositories via dynamic git discovery, and reconstructs multi-turn incident chains (`initial failed command -> intermediate retries / file writes -> eventual working resolution`).

3. **Targeted Forensic Sampling (Agent Reasoning):**
   For the highest-friction incident chains, the agent uses bounded `view_file` calls directly on `transcript.jsonl` to inspect the original prompt intent, raw error tracebacks, and tool execution context.

4. **Tri-Layer Remediation Synthesis (Agent Execution):**
   Interventions are partitioned into Host Tooling (package manager installs), Global Rules (`~/.gemini/config/GEMINI.md`), and Workspace Rules (`<repo_root>/AGENTS.md`).

5. **Verification Gate (Live Execution):**
   All applied environment configurations, shell rules, or workspace settings are tested using verification commands before completing the turn.

---

## Operational Procedure

### Phase 1: Execute Host Probe and Trajectory Mining

Locate the skill scripts directory and execute both diagnostic tools:

```pwsh
# Windows (PowerShell)
$SkillScripts = "C:\Users\Amir\.gemini\config\skills\improve-agent-efficiency\scripts"
py -3.10 "$SkillScripts\probe_environment.py" (Get-Location).Path
py -3.10 "$SkillScripts\audit_trajectories.py" (Get-Location).Path --limit 50
```

```bash
# macOS / Linux (POSIX)
SkillScripts="$HOME/.gemini/config/skills/improve-agent-efficiency/scripts"
python3 "$SkillScripts/probe_environment.py" "$(pwd)"
python3 "$SkillScripts/audit_trajectories.py" "$(pwd)" --limit 50
```

#### Optional Mining Flags
- `--since YYYY-MM-DD`: Restrict audit to sessions on or after a specific date. Useful for measuring the impact of recent rule updates.
- `--repo <keyword>`: Restrict audit to sessions associated with a specific repository name.
- `--all`: Parse all discovered sessions across all brain storage directories without limits.

The diagnostic run produces two artifacts in the current directory:
- `host_environment_probe.json`: Live binary inventory, stdout encoding status, and rule discrepancies.
- `trajectory_audit_summary.json`: Command failure counts, repository distribution, and extracted incident chains.

### Phase 2: Review Diagnostic Outputs

Read both generated JSON artifacts using bounded file reading:

1. **Inspect Host Findings:**
   Check `host_environment_probe.json` for missing standard tools (`rg`, `gh`, `dotnet`, runtimes) and encoding errors. Flag any tools that are installed on the system but prohibited or declared absent in `GEMINI.md`.

2. **Inspect High-Friction Incident Chains:**
   Review `high_friction_incidents` in `trajectory_audit_summary.json`. Focus on incidents exhibiting:
   - `retry_count >= 1`: Multi-step trial-and-error attempts before finding a working command.
   - `resolved: false`: Unhandled command failures that blocked completion.
   - `intervening_file_writes`: Cases where the agent had to write a disk script to bypass shell quoting issues.

### Phase 3: Targeted Forensic Sampling

When an incident category shows recurring friction (such as process file locks, module import errors, or encoding crashes), sample the raw conversation log to understand the full context:

1. Identify the `conversation_id` and `initial_step` from the incident record.
2. Locate the transcript file at:
   `<appDataDir>/brain/<conversation_id>/.system_generated/logs/transcript.jsonl`
3. Execute bounded file inspection around the failure step index to review the exact error stack and model reasoning.

### Phase 4: Tri-Layer Remediation Deployment

Apply corrective measures categorized across three distinct layers:

1. **Host Tooling Layer (Zero Token Overhead):**
   - Install missing CLI utilities requested by agents using native package managers (`winget install --id <Id>`, `brew install <pkg>`).
   - Set persistent environment variables for terminal streams (e.g., `[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")`).

2. **Global Rules Layer (`~/.gemini/config/GEMINI.md`):**
   - Correct false statements regarding installed platform binaries.
   - Enforce the File-First Execution SOP for multi-line logic (`py -c`, `node -e`).
   - Enforce bounded reading and bounded command output limits.

3. **Workspace Rules Layer (`<repo_root>/AGENTS.md`):**
   - Reference [references/remediation_patterns.md](references/remediation_patterns.md) for language-specific templates.
   - Codify runtime pinning (`py -3.10`), explicit `PYTHONPATH` exports, solution file targets (`.slnx`), pre-build process termination, and test invocation commands.

### Phase 5: Verification Gate

Validate all applied changes before concluding the task:

1. For host tool installations: Run `<binary> --version` to verify exit code 0.
2. For environment variables: Run a test command verifying the variable is active in child processes.
3. For workspace rules: Verify test runner commands and build commands execute cleanly against the target repository.
4. Format findings, incident comparisons, and verified actions into a final Markdown artifact for user review.

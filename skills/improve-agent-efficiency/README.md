# `improve-agent-efficiency` Skill

An automated diagnostic runbook, trajectory mining auditor, and systemic remediation engine for the Google Antigravity IDE and Antigravity CLI.

---

## Capabilities

- **Zero-Match Query Disambiguation:** Differentiates benign search returns (`rg`, `grep`, `findstr`, `diff` exiting with code 1) from true runtime errors, preventing false alarms.
- **Native Token Burn Telemetry:** Estimates token burn across prompt inputs, model responses, internal reasoning/thinking, and tool output streams.
- **Comparative Efficiency Mode (`--compare`):** Mathematically evaluates before vs. after performance to verify whether rule optimizations or tooling fixes produced measurable gains.
- **Causal Incident Mining:** Reconstructs multi-step retry loops (`initial failure -> retries / script writes -> eventual resolution`) to isolate true system friction.
- **Tri-Layer Remediation:** Synthesizes verified fixes across Host Tooling (`winget`/`brew`), Global Rules (`~/.gemini/config/GEMINI.md`), and Workspace Rules (`<repo_root>/AGENTS.md`).
- **Zero Third-Party Dependencies:** Pure Python standard library (`sys`, `os`, `json`, `re`, `platform`, `datetime`), compatible across Windows, macOS, and Linux.

---

## Operational Workflows

### Mode A: Status, Efficiency Gains & Token Burn Check (Read-Only)
When evaluating whether recent rule adjustments worked or checking resource expenditure:
```
/improve-agent-efficiency check efficiency status and token burn for the last 24 hours
```

Runs a fast comparative audit:
```pwsh
# Windows PowerShell
python ./scripts/audit_trajectories.py (Get-Location).Path --since 2026-10-07 --compare
```

```bash
# macOS / Linux (POSIX)
python3 ./scripts/audit_trajectories.py "$(pwd)" --since 2026-10-07 --compare
```

### Mode B: Deep Friction Audit & Tri-Layer Remediation
When discovering new execution friction, missing CLI tools, or broken workspace configurations:
```
/improve-agent-efficiency audit my past sessions and optimize agent rules
```

Executes the full 6-phase remediation cycle:
1. **Scoping & Discovery Gate:** Run rapid inventory scan (`--inventory-only`).
2. **Host Probe and Trajectory Mining:** Execute `probe_environment.py` and `audit_trajectories.py`.
3. **Diagnostic Output Review:** Inspect `host_environment_probe.json` and high-friction incidents.
4. **Targeted Forensic Sampling:** Inspect bounded lines in `transcript.jsonl` around failure steps.
5. **Tri-Layer Remediation Deployment:** Apply host tool installs, update global rules, or configure workspace `AGENTS.md`.
6. **Verification Gate:** Test all applied changes (`<binary> --version`, builds, and tests).

---

## CLI Options (`scripts/audit_trajectories.py`)

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `output_dir` | Positional | Current Directory | Target directory for generated JSON reports |
| `--compare` | Flag | `False` | Compare target window against baseline history and compute efficiency gains / token burn deltas |
| `--since` | String (`YYYY-MM-DD`) | `None` | Restrict parsing to sessions recorded on or after this date |
| `--limit` | Integer | `100` | Maximum number of recent conversations to parse |
| `--repo` | String | `None` | Filter parsing to sessions matching a repository substring |
| `--exclude` | String | `None` | Comma-separated list of repository names to exclude from parsing |
| `--all` | Flag | `False` | Parse all discovered conversations across all storage locations |
| `--inventory-only` | Flag | `False` | Discover repositories and date boundaries rapidly without parsing transcripts |

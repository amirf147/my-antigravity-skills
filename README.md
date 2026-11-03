# My Antigravity Skills

A repository of custom skills, diagnostic utilities, and execution runbooks for the Antigravity IDE and standalone Antigravity CLI.

Skills can be mounted globally into `~/.gemini/config/skills/` (machine scope) or vendored into `<repo_root>/.agents/skills/` (workspace scope).

---

## Skills Catalog

| Skill | Category | Platforms | Supported Stacks | Key Capability |
| :--- | :--- | :--- | :--- | :--- |
| [`improve-agent-efficiency`](./skills/improve-agent-efficiency/) | Diagnostics & Telemetry | Linux, macOS, Windows | Language-agnostic | Indexes hardware token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`), inference turns per prompt, tool errors across commands and file edits, and search-to-edit thrash ratios for first-principles transcript analysis. |
| [`public-repo-safety`](./skills/public-repo-safety/) | Security & Hygiene | Linux, macOS, Windows | Language-agnostic Git & Python scanner | Audits, scaffolds, and enforces pre-commit hooks and CI safety gates to prevent hardcoded local user paths (Windows `C:\Users\<user>`, Unix `/home/<user>`), secrets, API keys, and binary blobs from being committed. |

---

## Included Skills

### `improve-agent-efficiency`

A neutral session telemetry indexer and first-principles diagnostic workflow. Rather than relying on hardcoded failure categories or rigid remediation templates that cause rule bloat, `scripts/audit_trajectories.py` collects objective hardware and tool telemetry across conversation transcripts so the agent can inspect outlier sessions directly and diagnose root causes on the fly.

#### Core Capabilities (`scripts/audit_trajectories.py`)

- **Hardware Token Telemetry:** Extracts exact `input_tokens`, `cache_read_tokens`, `output_tokens`, cache hit rates, and peak context window sizes directly from `PLANNER_RESPONSE` steps in `transcript.jsonl`.
- **Turn Multiplication & Thrash Detection:** Tracks model inference turns (`PLANNER_RESPONSE`) per user prompt, read/search-to-edit ratios, and `scratch/` script creation overhead (`scratch_writes` and `scratch_runs`).
- **Comprehensive Tool Error Indexing:**
  - Separates benign zero-match search queries (`rg`, `grep`, `findstr`, `diff` exiting with code 1) from actual command failures.
  - Separates normal test and build verification cycles (`pytest`, `vitest`, `jest`, `cargo test`, `dotnet test`, `go test`, `tsc`) from unexpected shell errors.
  - Captures non-command tool failures (`edit_file` target mismatches, relative path errors in `read_file` / `edit_file`, `write_file` collisions, and `manage_task` errors).
- **Zero Repository Pollution:** Writes telemetry output to the system temporary directory (`$TEMP/agy_telemetry/telemetry_summary.json`) by default instead of leaving untracked artifacts in active repositories.
- **Comparative Cohort Analysis (`--compare`):** Partitions sessions around `--since YYYY-MM-DD` (defaulting to the last 24 hours) to compare turn counts, failure rates, and scratch script usage against historical baselines.

#### Workflow

1. **Index Telemetry:** Run `scripts/audit_trajectories.py` to generate `telemetry_summary.json` containing aggregate metrics, `top_cost_sessions`, `top_thrash_sessions`, and `recent_error_sessions`.
2. **Inspect Outliers from First Principles:** Read bounded step slices in `<appDataDir>/brain/<conversation_id>/.system_generated/logs/transcript.jsonl` for the highest-cost or highest-thrash sessions.
3. **Evaluate Rule ROI & Prune Overhead:** Identify whether existing rules in `~/.gemini/config/GEMINI.md` or `<repo_root>/AGENTS.md` are causing unnecessary tool calls (such as pre-read line counting, sequential chunking, or two-step scratch script writes) and simplify or remove counterproductive rules.

#### Usage

```pwsh
# Windows (PowerShell)
$Script = "$HOME\.gemini\config\skills\improve-agent-efficiency\scripts\audit_trajectories.py"

# Index recent 100 sessions
py -3.10 $Script --limit 100

# Index all sessions across history
py -3.10 $Script --all

# Compare sessions since a specific date against baseline
py -3.10 $Script --since 2026-11-01 --compare
```

```bash
# macOS / Linux (POSIX)
Script="$HOME/.gemini/config/skills/improve-agent-efficiency/scripts/audit_trajectories.py"
python3 "$Script" --limit 100
```

#### Command-Line Arguments

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `output_dir` | Positional | `$TEMP/agy_telemetry` | Directory where `telemetry_summary.json` is written |
| `--limit` | Integer | `100` | Maximum number of recent conversations to index |
| `--all` | Flag | `False` | Index all discovered conversations without limit |
| `--since` | String (`YYYY-MM-DD`) | `None` | Filter conversations modified on or after date |
| `--repo` | String | `None` | Filter conversations matching a repository name substring |
| `--exclude` | String | `None` | Comma-separated list of repository names to exclude |
| `--compare` | Flag | `False` | Compare target cohort since `--since` against prior baseline |

---

### `public-repo-safety`

An automated security and hygiene runbook for public and open-source repositories. Scaffolds pre-commit interception hooks, portable scanners, and GitHub Actions CI gates to prevent data leakage, user path disclosure, and accidental credential commits.

#### Core Capabilities
- **Local Path Hygiene:** Detects Windows user paths (`C:\Users\<user>`), Unix user home paths (`/home/<user>`, `/Users/<user>`), active username fragments, and local `file:///` URIs.
- **Credential & Secret Interception:** Flags private key headers, provider API tokens, GitHub personal access tokens, JWT tokens, and unredacted personal email addresses.
- **Binary Artifact Gate:** Blocks tracking of compiled binaries, objects, and unmanaged archives (`.dll`, `.exe`, `.so`, `.zip`, `.pyc`).
- **Three-Tier Enforcement:** Deploys a standalone scanner (`scripts/check_repo_safety.py`), local Git hook interception (`.git/hooks/pre-commit`, `.pre-commit-config.yaml`), and GitHub Actions CI verification (`.github/workflows/ci.yml`).

---

## Installation

### Global Installation (Machine Scope)

```bash
# macOS & Linux
mkdir -p ~/.gemini/config/skills
cp -r ./skills/improve-agent-efficiency ~/.gemini/config/skills/
```

```pwsh
# Windows PowerShell
$dest = "$env:USERPROFILE\.gemini\config\skills\improve-agent-efficiency"
Copy-Item -Path ".\skills\improve-agent-efficiency" -Destination $dest -Recurse -Force
```

### Workspace Installation (Project Scope)

```bash
# macOS & Linux
mkdir -p <project_root>/.agents/skills
cp -r ./skills/improve-agent-efficiency <project_root>/.agents/skills/
```

```pwsh
# Windows PowerShell
$dest = "<project_root>\.agents\skills\improve-agent-efficiency"
Copy-Item -Path ".\skills\improve-agent-efficiency" -Destination $dest -Recurse -Force
```

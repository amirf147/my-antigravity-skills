# My Antigravity Skills

A personal repository for custom skills used in the Antigravity IDE and the standalone Antigravity CLI application.

This repository tracks reusable skills, diagnostic utilities, and execution runbooks deployed into `~/.gemini/config/skills/` (global machine scope) or `<repo_root>/.agents/skills/` (workspace scope).

---

## Skills Catalog

| Skill | Category | Platforms | Key Capability |
| :--- | :--- | :--- | :--- |
| [`improve-agent-efficiency`](./skills/improve-agent-efficiency/) | Diagnostics & Auditing | Windows, macOS, Linux | Audits conversation histories, correlates unlinked trajectories to repositories, detects command failures and syntax collapses, and synthesizes actionable remediation plans. |

---

## Included Skills & Features

### `improve-agent-efficiency`

An automated diagnostic runbook and script that inspects past agent conversation transcripts to locate command execution bottlenecks, measure failure rates, and prevent token exhaustion.

#### Features
- **Cross-Platform Workspace Discovery:** Automatically resolves Antigravity IDE and standalone app storage paths across Windows (`%APPDATA%\Antigravity IDE\User\workspaceStorage`), macOS, and Linux without hardcoded paths.
- **Unlabeled Session Correlation:** Uses a four-tier heuristic (workspace declarations, tool path prefixes, and prompt keyword tokens) to map orphaned or desynchronized trajectories back to their source Git repositories.
- **Transcript Parsing & Failure Detection:** Analyzes JSON Lines logs (`transcript.jsonl`) to pair commands with process exit codes, unhandled exceptions, and shell parsing failures.
- **Failure Classification:** Categorizes failures into standardized archetypes including inline script quotation collapse, terminal output encoding crashes (`cp1252`), missing system binaries, process file locks, and dependency path errors.
- **Tri-Layer Remediation Model:** Translates identified failure modes into fixes across native host binaries (zero token cost), global configuration (`~/.gemini/config/GEMINI.md`), and workspace rules (`<repo_root>/AGENTS.md`).

#### Usage

Run the bundled zero-dependency Python script against the target output directory:

```pwsh
# Windows (PowerShell)
py -3.10 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py (Get-Location).Path
```

```bash
# macOS / Linux (POSIX)
python3 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py "$(pwd)"
```

---

## Installation

### Global Installation (Machine Scope)

Mount a skill globally so it is available across all workspaces in the Antigravity IDE and standalone CLI:

```pwsh
# Windows PowerShell
$dest = "$env:USERPROFILE\.gemini\config\skills\improve-agent-efficiency"
Copy-Item -Path ".\skills\improve-agent-efficiency" -Destination $dest -Recurse -Force
```

```bash
# macOS & Linux
mkdir -p ~/.gemini/config/skills
cp -r ./skills/improve-agent-efficiency ~/.gemini/config/skills/
```

### Workspace Installation (Project Scope)

Vendor a skill directly into a repository to share it within a specific project:

```bash
mkdir -p <project_root>/.agents/skills
cp -r ./skills/improve-agent-efficiency <project_root>/.agents/skills/
```

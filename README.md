# Antigravity Skills Library

A curated repository of modular, production-grade skills for Google Antigravity (AGY) and Antigravity 2.0.

This repository serves as a centralized source for reusable agent capabilities, diagnostic runbooks, and automation workflows that can be mounted globally across a machine or vendored into specific projects.

---

## 1. Architectural Philosophy: Human Documentation vs. Agent Context

A common concern when building a skills library is whether human-facing documentation (such as this `README.md`) consumes context tokens when an agent accesses the repository.

### How Antigravity Progressive Disclosure Protects Context

Antigravity employs strict progressive disclosure during skill discovery:

1. **Discovery Boundary:** When Antigravity mounts a skills folder (e.g., `~/.gemini/config/skills/` or `.agents/skills/`), it scans only for subdirectories containing a `SKILL.md` file. It completely ignores root-level files such as `README.md`, `LICENSE`, or `.gitignore`.
2. **Catalog Indexing (Zero Runbook Token Cost):** For each discovered skill, the system parses **only** the top YAML frontmatter block (`name` and `description`). The main body of `SKILL.md` is not loaded into the system prompt.
3. **On-Demand Activation:** The agent retrieves the full instructions inside `SKILL.md` only when the user's prompt matches the skill's description or when explicitly invoked.
4. **Encapsulated Isolation:** Each skill in `skills/<skill_name>/` is a standalone unit:
   - `SKILL.md` contains concise, imperative operational instructions for the agent.
   - `scripts/` contains cross-platform CLI executables.
   - `references/` contains deep manuals or templates, which the agent reads only if a step directs it to do so.

This architecture ensures that rich educational documentation for human engineers at the repository root consumes zero tokens during agent turns.

---

## 2. Included Skills

| Skill | Category | Target Environments | Purpose |
| :--- | :--- | :--- | :--- |
| [`trajectory-efficiency-auditor`](./skills/trajectory-efficiency-auditor/) | Diagnostics & Auditing | Windows, macOS, Linux | Audits conversation histories, correlates unlinked trajectories to repositories, detects command failures and syntax collapses, and synthesizes actionable remediation plans. |

---

## 3. Deep Dive: `trajectory-efficiency-auditor`

### 3.1 Background & Empirical Motivation

During prolonged software development with autonomous coding agents, execution friction accumulates quietly:
- Multi-line inline scripts (`python -c`, `node -e`) collapse under shell quotation and variable expansion rules.
- Legacy terminal encodings (such as Windows `cp1252`) crash with `UnicodeEncodeError` when agents print non-ASCII text, foreign languages, or transcripts.
- Missing host binaries (e.g. `rg`, `gh`, `jq`) trigger repeated trial-and-error loops.
- Running background daemons lock output binaries, failing successive builds.

This skill was synthesized after an empirical audit of 2,200 command executions across 80 Antigravity working sessions, which revealed a 12.05% baseline failure rate. By auditing past trajectories, developers can measure execution failure rates and identify missing tools or workspace rules.

### 3.2 Core Mechanisms

The auditor engine ([`audit_trajectories.py`](./skills/trajectory-efficiency-auditor/scripts/audit_trajectories.py)) operates through five automated stages:

1. **Cross-Platform Workspace Discovery:**
   Dynamically locates IDE state and workspace storage without hardcoded paths:
   - Windows: `%APPDATA%\Antigravity IDE\User\workspaceStorage`
   - macOS: `~/Library/Application Support/Antigravity IDE/User/workspaceStorage`
   - Linux: `~/.config/Antigravity IDE/User/workspaceStorage`
2. **Four-Tier Unlabeled Conversation Correlation:**
   Many sessions are started in general folders or without explicit repository metadata. The auditor attributes sessions to their true Git repository using:
   - System prompt `<user_information>` workspace declarations.
   - Longest common path prefix matching from tool arguments (`Cwd`, `TargetFile`, `AbsolutePath`).
   - Repository basename matching against user prompt text.
   - General environment fallback clustering for host configuration sessions.
3. **Transcript Parsing & Failure Matching:**
   Reads JSON Lines steps in `.system_generated/logs/transcript.jsonl`, pairs `run_command` invocations with exit codes and standard error streams, and detects unhandled exceptions and syntax errors.
4. **Failure Classification:**
   Sorts issues into seven standardized archetypes:
   - Inline Script Quoting Collapse
   - Console Output Encoding Trap
   - Missing Host Tool / CLI Binary
   - Missing Project Environment / Dependency Path
   - Process File Lock Collision
   - Shell Syntax / Parser Error
   - Git Remote / Branch Safety Block
5. **The Tri-Layer Remediation Model:**
   Rather than treating all failures as prompt engineering problems, the skill divides solutions into three layers:
   - **Layer 1: Native Tools (Zero Token Cost):** Install missing tools via Winget, Homebrew, or Apt.
   - **Layer 2: Global Rules (`~/.gemini/config/GEMINI.md`):** Enforce cross-project constraints (such as File-First scripting and bounded file reading).
   - **Layer 3: Workspace Rules (`<repo_root>/AGENTS.md`):** Codify project-specific invariants (`$env:PYTHONPATH`, solution formats, pre-build process termination).

---

## 4. Installation & Mounting Guide

To use skills from this repository in your local Antigravity environment, choose between global mounting or project-specific vendoring.

### Option A: Global Installation (Machine-Wide)

To make a skill available across all projects and chat sessions on your machine, copy or symlink the specific skill folder into your Antigravity global configuration:

#### Windows (PowerShell)
```pwsh
# Copy trajectory-efficiency-auditor to global skills
$dest = "$env:USERPROFILE\.gemini\config\skills\trajectory-efficiency-auditor"
Copy-Item -Path ".\skills\trajectory-efficiency-auditor" -Destination $dest -Recurse -Force
```

#### macOS & Linux (Bash)
```bash
# Symlink or copy to global configuration
mkdir -p ~/.gemini/config/skills
cp -r ./skills/trajectory-efficiency-auditor ~/.gemini/config/skills/
```

### Option B: Project-Specific Vendoring (Team-Shared via Git)

To provide a skill exclusively within a specific repository, place it inside the project's `.agents/skills/` directory:

```bash
mkdir -p <project_root>/.agents/skills
cp -r ./skills/trajectory-efficiency-auditor <project_root>/.agents/skills/
git add <project_root>/.agents/skills
git commit -m "chore(agents): vendor trajectory-efficiency-auditor skill"
```

Once placed, any agent working in that project will automatically discover the skill through hierarchical directory traversal.

---

## 5. Standardized Skill Specification

All skills in this repository adhere to the modern Antigravity Agent Skills standard:

```text
skills/<skill_name>/
├── SKILL.md                          # Mandatory: Runbook with YAML frontmatter
├── scripts/                          # Optional: Standalone zero-dependency scripts
├── references/                       # Optional: Progressive disclosure manuals & templates
└── examples/                         # Optional: Sample configurations or fixtures
```

### Frontmatter Requirements
Every `SKILL.md` must start with valid YAML frontmatter:

```yaml
---
name: skill-name-in-kebab-case
description: Third-person description stating both WHAT the skill does and WHEN the agent should activate it.
---
```

### Authoring Rules
1. **Zero External Runtime Dependencies:** Scripts in `scripts/` should rely strictly on the standard library of their language (Python 3 standard library, native PowerShell 7 cmdlets, or POSIX sh).
2. **Dynamic Path Resolution:** Never hardcode user profiles or absolute drive letters. Use dynamic home path discovery.
3. **High Explanatory Density:** Runbooks must prioritize exact commands, directory layouts, and deterministic steps over conversational descriptions.

# My Antigravity Skills

A repository of custom skills, diagnostic utilities, and execution runbooks for the Antigravity IDE and standalone Antigravity CLI.

Skills can be mounted globally into `~/.gemini/config/skills/` (machine scope) or vendored into `<repo_root>/.agents/skills/` (workspace scope).

---

## Skills Catalog

| Skill | Category | Platforms | Supported Stacks | Key Capability |
| :--- | :--- | :--- | :--- | :--- |
| [`improve-agent-efficiency`](./skills/improve-agent-efficiency/) | Diagnostics & Auditing | Linux, macOS, Windows | TypeScript/Node, Python, Go, Rust, .NET | Audits conversation histories, correlates unlinked trajectories to repositories, detects command failures and syntax collapses, and synthesizes actionable remediation plans. |

---

## Architectural Model: Why an Automated Script Instead of Direct Chat Prompts

A common question is why a dedicated skill and local Python script are needed when Antigravity can be prompted directly in chat.

The two approaches differ in token economics and data fidelity:

1. **Context Window Protection:**
   Conversation transcripts are stored as raw JSON Lines files (`transcript.jsonl`) containing full tool payloads, verbose process outputs, and system prompts. Feeding dozens of raw session logs directly into an LLM context window consumes hundreds of thousands of tokens and triggers context window truncation. The bundled script parses all local sessions out-of-band in seconds at zero token cost.

2. **Empirical Precision vs. LLM Estimation:**
   Direct prompting causes the model to guess failure frequencies based on a small sample. The auditor deterministically checks every command step across all sessions, calculates exact failure percentages, and groups errors by standardized archetype.

3. **Unlabeled Session Correlation:**
   Transcripts are stored by UUID. When IDE synchronization drops workspace headers, raw prompts lose their repository context. The auditor matches UUIDs back to local Git repositories using workspace declarations, file path prefixes, and prompt keyword heuristics.

4. **Natural Chat Interface:**
   Once installed, the user does not need to execute scripts manually. Asking Antigravity *"Audit my past sessions and optimize agent rules"* causes the agent to invoke the script autonomously, read the 2 KB summary, and synthesize tailored rules.

---

## Included Skills

### `improve-agent-efficiency`

An automated diagnostic runbook and zero-dependency script that inspects past agent conversation transcripts to locate command execution bottlenecks, measure failure rates, and prevent token exhaustion.

#### Supported Failure Archetypes
- **Inline Script Quoting Collapse:** Multi-line `python -c`, `node -e`, or shell parsing errors.
- **Console Encoding Traps:** Non-UTF-8 stream crashes (`UnicodeEncodeError`).
- **Missing Host Binaries:** Dynamic detection of missing CLI tools across `apt`, `brew`, and `winget`.
- **Dependency & Module Resolution:** TypeScript module errors, `npm`/`pnpm` lockfile collisions, Python `ModuleNotFoundError`.
- **Process & Port Locks:** Compiler binary locks (`CS2012`), occupied dev ports (`EADDRINUSE`).
- **POSIX Execution Traps:** Unset executable bits (`chmod +x`) and shell interpreter mismatches.

#### Usage

You can trigger the audit directly via chat:
```
Audit my past sessions and optimize workspace rules.
```

Or execute the script manually from the command line:

```bash
# macOS / Linux (POSIX)
python3 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py "$(pwd)"
```

```pwsh
# Windows (PowerShell)
py -3.10 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py (Get-Location).Path
```

---

## Installation

### Global Installation (Machine Scope)

Mount a skill globally so it is available across all workspaces:

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

Vendor a skill directly into a repository to share it with a specific project:

```bash
mkdir -p <project_root>/.agents/skills
cp -r ./skills/improve-agent-efficiency <project_root>/.agents/skills/
```

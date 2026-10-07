# My Antigravity Skills

A repository of custom skills, diagnostic utilities, and execution runbooks for the Antigravity IDE and standalone Antigravity CLI.

Skills can be mounted globally into `~/.gemini/config/skills/` (machine scope) or vendored into `<repo_root>/.agents/skills/` (workspace scope).

---

## Skills Catalog

| Skill | Category | Platforms | Supported Stacks | Key Capability |
| :--- | :--- | :--- | :--- | :--- |
| [`improve-agent-efficiency`](./skills/improve-agent-efficiency/) | Diagnostics & Auditing | Linux, macOS, Windows | TypeScript/Node, Python, Go, Rust, .NET | Probes live host tooling, mines multi-turn causal incident chains from past conversation logs, and synthesizes verified tri-layer remediations. |

---

## Architecture: Out-of-Band Script Execution vs. Direct Chat Prompts

Executing diagnostic scripts locally rather than inspecting raw transcripts inside chat provides measurable advantages in token economics and data fidelity:

1. **Context Window Protection:**
   Conversation transcripts are stored as raw JSON Lines files (`transcript.jsonl`) containing tool payloads, process outputs, system instructions, and user messages. Feeding unparsed session logs directly into an LLM context window consumes hundreds of thousands of tokens and causes context window truncation. The bundled scripts parse local sessions out-of-band at zero token cost.

2. **Causal Incident Mining vs. LLM Estimation:**
   Direct prompting causes the model to guess failure frequencies based on a small sample. The trajectory auditor deterministically evaluates every command step across sessions, measures exact failure percentages, and reconstructs multi-turn incident chains (`initial command failure -> retries / intervening file writes -> eventual resolution`).

3. **Dynamic Git Root Resolution and Session Attribution:**
   Transcripts are stored by UUID. When IDE synchronization drops workspace headers, raw prompts lose their repository context. The auditor matches UUIDs back to local repositories by parsing workspace declarations, longest common path prefixes from tool arguments (`Cwd`, `TargetFile`, `AbsolutePath`), and dynamic Git root discovery.

4. **Natural Chat Interface:**
   The user does not need to execute scripts manually during regular workflows. Asking Antigravity to audit past sessions causes the agent to invoke the scripts autonomously, read the compact JSON summaries, and synthesize verified rules.

---

## Included Skills

### `improve-agent-efficiency`

An automated diagnostic runbook and toolset that inspects past agent conversation transcripts, detects execution friction and multi-turn retry loops, probes the live host environment for tool discrepancies, and executes verified systemic remediations.

#### Core Diagnostic Utilities

The skill bundles two standalone Python scripts in `scripts/`:

1. **Host Environment Probe (`scripts/probe_environment.py`):**
   - Tests standard output stream encoding and verifies UTF-8 byte resilience.
   - Inspects host availability and version strings for standard platform binaries (`git`, `gh`, `rg`, `pwsh`, `python`, `node`, `pnpm`, `go`, `cargo`, `dotnet`, `winget`, `brew`, `apt`).
   - Cross-references detected binaries against global rules (`~/.gemini/config/GEMINI.md`) to detect discrepancies, such as tools marked absent in configuration that exist on PATH.
   - Writes diagnostic output to `host_environment_probe.json`.

2. **Causal Trajectory Auditor (`scripts/audit_trajectories.py`):**
   - Parses local conversation transcripts across all discovered brain storage locations.
   - Reconstructs multi-turn incident chains, tracking initial command failures, subsequent retries, intervening file-write workarounds, and eventual working resolutions.
   - Dynamically resolves Git repository roots from touched file paths.
   - Features rapid inventory scanning (`--inventory-only`) to discover date boundaries and repository footprints in seconds without parsing transcripts.
   - Supports temporal filtering (`--since YYYY-MM-DD`), repository targeting (`--repo <keyword>`), and negative filtering (`--exclude <name1,name2>`).
   - Writes diagnostic output to `trajectory_audit_summary.json` or `trajectory_inventory.json`.

#### Six-Phase Operational Workflow

The operational procedure executes across six sequential phases:

1. **Scoping & Discovery Gate:** Run rapid inventory scan (`--inventory-only`) and interactively select repository scope and date window before deep parsing.
2. **Host Probe and Trajectory Mining:** Execute `probe_environment.py` and `audit_trajectories.py` to produce structured diagnostic artifacts.
3. **Diagnostic Output Review:** Inspect `host_environment_probe.json` for missing tools or encoding bugs, and review high-friction incident chains in `trajectory_audit_summary.json`.
4. **Targeted Forensic Sampling:** Perform bounded file reading on `transcript.jsonl` around failure step indices for unresolved or high-retry incidents.
5. **Tri-Layer Remediation Deployment:**
   - **Host Tooling Layer:** Install missing platform binaries via native package managers (`winget`, `brew`, `apt`) and configure persistent environment variables (`PYTHONIOENCODING=utf-8`).
   - **Global Rules Layer (`~/.gemini/config/GEMINI.md`):** Correct platform binary declarations, enforce the File-First Execution SOP for multi-line logic, and maintain bounded output rules.
   - **Workspace Rules Layer (`<repo_root>/AGENTS.md`):** Enforce runtime pinning, lockfile policies, build/test commands, and pre-build process termination.
6. **Verification Gate:** Test all applied binary installations (`<binary> --version`), environment settings, build steps, and test commands before concluding.

#### Supported Failure Archetypes

- **Inline Script Quoting Collapse:** Multi-line `python -c`, `node -e`, or shell parsing errors caused by quotation stripping.
- **Console Encoding Traps:** Terminal output crashes on non-ASCII characters (`UnicodeEncodeError`).
- **Missing Host Binaries:** Commands failing due to missing CLI utilities on PATH.
- **Dependency & Module Resolution:** TypeScript module errors, `npm`/`pnpm` lockfile collisions, and Python `ModuleNotFoundError`.
- **Process & Port Locks:** Compiler file access locks (`CS2012`) and occupied development ports (`EADDRINUSE`).
- **POSIX Execution Traps:** Unset executable bits (`chmod +x`) and shell interpreter mismatches.

#### Usage

##### Direct Chat Invocation

Trigger the audit workflow directly from chat:

```
Audit my past sessions and optimize agent rules.
```

##### Manual CLI Execution

Run the diagnostic scripts directly from the repository root:

```pwsh
# Windows (PowerShell)
# Rapid repository inventory
python ./skills/improve-agent-efficiency/scripts/audit_trajectories.py (Get-Location).Path --inventory-only

# Deep diagnostic probe & trajectory audit
python ./skills/improve-agent-efficiency/scripts/probe_environment.py (Get-Location).Path
python ./skills/improve-agent-efficiency/scripts/audit_trajectories.py (Get-Location).Path --limit 50 --exclude temp-repo
```

```bash
# macOS / Linux (POSIX)
# Rapid repository inventory
python3 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py "$(pwd)" --inventory-only

# Deep diagnostic probe & trajectory audit
python3 ./skills/improve-agent-efficiency/scripts/probe_environment.py "$(pwd)"
python3 ./skills/improve-agent-efficiency/scripts/audit_trajectories.py "$(pwd)" --limit 50 --exclude temp-repo
```

##### Command-Line Arguments

The `audit_trajectories.py` script supports the following filtering parameters:

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `output_dir` | Positional | Current Directory | Target directory for generated JSON reports |
| `--limit` | Integer | `100` | Maximum number of recent conversations to parse |
| `--since` | String (`YYYY-MM-DD`) | `None` | Restrict parsing to sessions recorded on or after this date |
| `--repo` | String | `None` | Filter parsing to sessions matching a repository substring |
| `--exclude` | String | `None` | Comma-separated list of repository names to exclude from parsing |
| `--all` | Flag | `False` | Parse all discovered conversations across all storage locations |
| `--inventory-only` | Flag | `False` | Discover repositories and date boundaries rapidly without parsing transcripts |

The `probe_environment.py` script accepts an optional positional `output_dir` parameter.

#### Diagnostic Artifacts

The scripts generate structured JSON artifacts in the specified output directory:

| Artifact | Generated By | Primary Contents |
| :--- | :--- | :--- |
| `trajectory_inventory.json` | `audit_trajectories.py --inventory-only` | Total conversation count, earliest/latest session dates, active workspace info, and list of discovered git repositories |
| `host_environment_probe.json` | `probe_environment.py` | Platform details, Python stream encoding status, installed binary inventory, and configuration discrepancies against `GEMINI.md` |
| `trajectory_audit_summary.json` | `audit_trajectories.py` | Aggregate command failure metrics, category breakdowns, repository distribution, and extracted incident chains |

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
# macOS & Linux
mkdir -p <project_root>/.agents/skills
cp -r ./skills/improve-agent-efficiency <project_root>/.agents/skills/
```

```pwsh
# Windows PowerShell
$dest = "<project_root>\.agents\skills\improve-agent-efficiency"
Copy-Item -Path ".\skills\improve-agent-efficiency" -Destination $dest -Recurse -Force
```

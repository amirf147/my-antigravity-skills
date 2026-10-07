# Remediation Patterns & Invariant Archetypes

This reference guide details how to translate trajectory failure patterns into actionable, high-density Antigravity configurations.

---

## 1. The Tri-Layer Remediation Model

When auditing agent failures, categorize fixes into three distinct layers:

```
Layer 1: Native Host Tools (Zero Token Cost)
   └── If the model naturally invokes standard CLI tools (rg, gh, fd, jq), install them globally.

Layer 2: Global Configuration (~/.gemini/config/GEMINI.md)
   └── If a failure mode spans all projects (quoting collapse, output limits), enforce it globally.

Layer 3: Workspace Rules (<repo_root>/AGENTS.md)
   └── If an invariant is project-specific (PYTHONPATH, solution file, test mocks), deploy it locally.
```

---

## 2. Common Failure Archetypes & Prescriptions

### Archetype 1: Inline Script Quoting Collapse
- **Symptoms:** `SyntaxError: unterminated string literal`, `SyntaxError: '(' was never closed`.
- **Root Cause:** Shell parsing strips quotes, collapses backticks, and breaks multi-line strings.
- **Remediation:**
  - Enforce a strict **File-First Execution SOP** in global rules: logic exceeding one line must be written to `<appDataDir>/brain/<id>/scratch/` and executed via `-File` or python interpreter.

### Archetype 2: Console Output Encoding Crash
- **Symptoms:** `UnicodeEncodeError: 'charmap' codec can't encode character...`
- **Root Cause:** Operating system terminal standard output defaults to legacy code pages (`cp1252` on Windows).
- **Remediation:**
  - Set persistent environment variable `PYTHONIOENCODING=utf-8`.
  - On Windows, install a `sitecustomize.py` in Python `site-packages` that reconfigures `sys.stdout` to UTF-8.

### Archetype 3: Missing Host Binary
- **Symptoms:** `The term 'rg' is not recognized`, `command not found: jq`.
- **Root Cause:** Agent prompts or model training bias reach for standard CLI tools not installed in the PATH.
- **Remediation:**
  - On Windows: `winget install --id <PackageId> --exact`
  - On macOS: `brew install <package>`
  - On Linux: `apt install -y <package>` or equivalent package manager.

### Archetype 4: Missing Project Environment / Paths
- **Symptoms:** `ModuleNotFoundError: No module named '<local_pkg>'`.
- **Root Cause:** Script executed without exporting local project paths or virtual environment packages.
- **Remediation:**
  - Deploy `<repo_root>/AGENTS.md` containing explicit environment exports (e.g. `$env:PYTHONPATH = "..."`).

### Archetype 5: Concurrency & File Write Locks
- **Symptoms:** `CSC : error CS2012: Cannot open '...dll' for writing`, `Move-Item: Process cannot access the file`.
- **Root Cause:** A running daemon, background test runner, or MCP server holds an open file handle on the build target.
- **Remediation:**
  - Deploy `<repo_root>/AGENTS.md` prescribing pre-build process termination before compiling.

---

## 3. Workspace Rule Templates (`AGENTS.md`)

### Template A: Python / Virtualenv Project
```markdown
# <ProjectName> Workspace Rules

## 1. Runtime & Environment Stack
- Python Version: Target Python <version> via `py -<version>` or `<venv>/bin/python`.
- Environment Paths: Export local module paths before running test commands:
  `$env:PYTHONPATH = "<path/to/modules>"`
- Encoding: Enforce UTF-8 standard output on all data parsers and file handlers.

## 2. Test Execution
- Run tests via pinned virtualenv: `py -3.10 -m pytest tests/`
- Avoid wildcard path arguments in shell runners.
```

### Template B: .NET / C# Solution
```markdown
# <ProjectName> Workspace Rules

## 1. Runtime & Build Target
- Framework: .NET 10 (`net10.0-windows`).
- Solution File: Target `<Project>.slnx` directly. Do not target legacy `.sln` files.
- Process Hygiene: Before running `dotnet build`, kill any running instances locking output binaries:
  `Get-Process -Name "*<ProcessName>*" -ErrorAction SilentlyContinue | Stop-Process -Force`
```

# Remediation Patterns & Invariant Archetypes

This reference guide details how to translate trajectory failure patterns into actionable, high-density Antigravity configurations.

---

## 1. The Tri-Layer Remediation Model

When auditing agent failures, categorize fixes into three distinct layers:

```
Layer 1: Native Host Tools (Zero Token Cost)
   └── If transcripts show the model repeatedly invoking missing host binaries (e.g. rg, gh, fd, jq, node, pnpm, uv, go, cargo, dotnet), install them globally rather than forcing prompt workarounds.

Layer 2: Global Configuration (~/.gemini/config/GEMINI.md)
   └── If a failure mode spans all projects (quoting collapse, output limits, bounded reading), enforce it globally.

Layer 3: Workspace Rules (<repo_root>/AGENTS.md)
   └── If an invariant is project-specific (PYTHONPATH, package manager, solution file, port hygiene, test targets), deploy it locally.
```

---

## 2. Common Failure Archetypes & Prescriptions

### Archetype 1: Inline Script Quoting Collapse
- **Symptoms:** `SyntaxError: unterminated string literal`, `SyntaxError: '(' was never closed`, `ParserError: Unexpected token`.
- **Root Cause:** Shell parsing in bash, zsh, or PowerShell strips nested quotes and breaks multi-line logic passed via inline flags (`python -c`, `node -e`, `bash -c`).
- **Remediation:**
  - Enforce a strict **File-First Execution SOP** in global rules: logic exceeding one line must be written to `<appDataDir>/brain/<id>/scratch/` as a standalone script file and executed directly.

### Archetype 2: Console Output Encoding & Stream Traps
- **Symptoms:** `UnicodeEncodeError: 'charmap' codec can't encode character...`, garbled terminal control sequences.
- **Root Cause:** Operating system terminal standard output defaults to legacy non-UTF-8 code pages.
- **Remediation:**
  - Set persistent environment variable `PYTHONIOENCODING=utf-8`.
  - On Windows, install a `sitecustomize.py` in Python `site-packages` that reconfigures `sys.stdout` to UTF-8.

### Archetype 3: Missing Host Binary
- **Symptoms:** `The term '<binary>' is not recognized`, `command not found: <binary>`.
- **Root Cause:** Agent prompts or model training bias reach for standard CLI tools not installed in the host system PATH.
- **Auditor Guidance:**
  - Do not restrict inspection to hardcoded tool names. The auditor dynamically extracts whatever binary name triggered `not recognized` or `command not found` from the standard error stream.
  - Typical examples include repository search utilities (`rg`, `fd`), platform clients (`gh`), language runtimes (`uv`, `node`, `pnpm`, `go`, `cargo`, `dotnet`), and data formatters (`jq`).
- **Remediation:**
  - Windows: `winget install --id <PackageId> --exact`
  - macOS: `brew install <package>`
  - Linux: `apt install -y <package>` or `pacman -S <package>`

### Archetype 4: Dependency & Module Resolution Failures
- **Symptoms:** `ModuleNotFoundError: No module named '<pkg>'`, `ERR_MODULE_NOT_FOUND`, `ERESOLVE unable to resolve dependency tree`.
- **Root Cause:** Scripts executed without exporting local project paths, virtual environment binaries, or running wrong package manager variants (`npm` instead of `pnpm`).
- **Remediation:**
  - Python: Deploy `<repo_root>/AGENTS.md` containing explicit environment exports (e.g. `PYTHONPATH = "."`) or pinning runners (`uv run pytest`).
  - JavaScript / TypeScript: Specify exact package manager (`pnpm`, `npm`, `yarn`, `bun`) and enforce strict lockfile adherence (`pnpm install --frozen-lockfile`).

### Archetype 5: Concurrency, Port Collisions, & Process File Locks
- **Symptoms:** `CSC : error CS2012: Cannot open '...dll' for writing`, `EADDRINUSE: address already in use :::3000`, `text file busy`.
- **Root Cause:** A running daemon, background test runner, or dev server holds an open handle or socket on the build target.
- **Remediation:**
  - Deploy `<repo_root>/AGENTS.md` prescribing pre-build process termination or port reclamation before recompiling or launching servers.

### Archetype 6: POSIX Permissions & Shell Execution Traps
- **Symptoms:** `permission denied: ./script.sh`, `EACCES: permission denied`.
- **Root Cause:** Scripts generated without executable bits (`+x`) or invoked without explicit shell interpreter prefix.
- **Remediation:**
  - Codify interpreter prefixes in rules (e.g. `bash ./script.sh` or explicit `chmod +x` prior to invocation).

---

## 3. Workspace Rule Templates (`AGENTS.md`)

### Template A: TypeScript / Full-Stack Project (Node.js, Vite, Next.js)
```markdown
# <ProjectName> Workspace Rules

## 1. Runtime & Package Management
- Package Manager: Pin to `pnpm`. Do not use `npm` or `yarn`.
- Install Command: Use `pnpm install --frozen-lockfile`.
- Module Resolution: Project uses native ECMAScript Modules (`"type": "module"`). Use fully qualified import specifiers with extensions if required by bundler.

## 2. Quality Checks & Builds
- Type Checking: Run `pnpm exec tsc --noEmit` before proposing completed refactors.
- Linter: Run `pnpm lint`.
- Dev Server Hygiene: Before starting dev servers (`pnpm dev`), ensure target ports (e.g. 3000, 5173) are vacant.

## 3. Test Execution
- Runner: Run tests via `pnpm test` or `pnpm exec vitest run <file>`.
```

### Template B: Python Project (Modern `uv` / Virtualenv)
```markdown
# <ProjectName> Workspace Rules

## 1. Runtime & Environment Stack
- Package & Environment Manager: Target `uv` or pinned virtualenv at `.venv/`.
- Execution Prefix: Run scripts and tools via `uv run python <script>` or `uv run pytest`.
- Environment Paths: Set `PYTHONPATH = "."` when executing uninstalled package modules.
- Encoding: Enforce UTF-8 standard output on all data parsers and file handlers.

## 2. Test Execution
- Run tests via pinned environment: `uv run pytest tests/ -v`
- Avoid wildcard path arguments in shell runners.
```

### Template C: Go Module Project
```markdown
# <ProjectName> Workspace Rules

## 1. Toolchain & Dependencies
- Go Version: Target Go 1.22+.
- Dependency Sync: Run `go mod tidy` after modifying imports. Do not manually edit `go.sum`.

## 2. Testing & Quality Checks
- Test Execution: Run `go test -race -timeout 30s ./...`
- Targeted Test: Run `go test -v -run <TestName> ./<package>`
- Vet: Run `go vet ./...` before finalizing code edits.
```

### Template D: Rust / Cargo Workspace
```markdown
# <ProjectName> Workspace Rules

## 1. Toolchain & Workspace Targets
- Compiler: Stable Rust toolchain.
- Target Selection: Target specific crates via `-p <crate_name>` in workspace roots.
- Fast Checks: Run `cargo check --workspace` before initiating full compilation.

## 2. Testing & Linting
- Linting: Run `cargo clippy --all-targets -- -D warnings`
- Tests: Run `cargo test -p <crate_name> -- --nocapture`
```

### Template E: .NET / C# Solution
```markdown
# <ProjectName> Workspace Rules

## 1. Runtime & Build Target
- Framework: .NET 10 (`net10.0-windows` or `net10.0`).
- Solution File: Target `<Project>.slnx` directly. Do not target legacy `.sln` files.
- Process Hygiene: Before running `dotnet build`, terminate running instances locking output binaries:
  PowerShell: `Get-Process -Name "*<ProcessName>*" -ErrorAction SilentlyContinue | Stop-Process -Force`
  POSIX: `pkill -f "<ProcessName>" || true`
```

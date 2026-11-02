---
name: public-repo-safety
description: Audits, scaffolds, and enforces pre-commit hooks and CI safety gates to prevent hardcoded local user paths (Windows C:\Users, Unix /home), secrets, API keys, and binary blobs from being committed to public repositories.
---

# Public Repository Safety & Hygiene

Use this skill when onboarding, auditing, or configuring a public repository to intercept data leaks, personal paths, credentials, and binary artifacts before commits reach GitHub.

## When to Run This Skill
- When creating or open-sourcing a new public repository.
- When auditing an existing repository prior to initial release or major contribution.
- When configuring local developer hooks (`.git/hooks/pre-commit`, `.pre-commit-config.yaml`).
- When setting up the initial GitHub Actions CI workflow gate.

---

## Workflow Sequence

### Phase 1: Pre-Audit Existing Workspace
Before scaffolding hooks, inspect current repository health:
1. Verify repository root via `git rev-parse --show-toplevel`.
2. Execute the scanner in audit mode across all tracked files (if `scripts/check_repo_safety.py` is not yet deployed in the workspace root, run it directly from the skill directory or copy the script first):
   ```bash
   python scripts/check_repo_safety.py
   ```
3. If violations are flagged, resolve or redact paths before committing.

### Phase 2: Scaffold Safety Components
Deploy the standard three-tier safety infrastructure into the target repository:

1. **Scanner Script:**
   Copy `scripts/check_repo_safety.py` from this skill into `<target_repo>/scripts/check_repo_safety.py`.

2. **Pre-Commit Framework Configuration:**
   Copy `templates/.pre-commit-config.yaml` to `<target_repo>/.pre-commit-config.yaml`.

3. **Native Git Hook Wrapper:**
   Copy `templates/pre-commit-hook.sh` to `<target_repo>/.git/hooks/pre-commit`.
   Ensure execution permissions:
   ```bash
   chmod +x .git/hooks/pre-commit
   ```

4. **CI Workflow Gate:**
   Copy `templates/ci-safety.yml` to `<target_repo>/.github/workflows/ci.yml`.

### Phase 3: Verification & Interception Test
1. Run `python scripts/check_repo_safety.py` and confirm `[PASSED]` with zero violations.
2. Stage modified files (`git add scripts/ .pre-commit-config.yaml .github/`).
3. Verify that native commit interception aborts mock invalid lines containing `C:\Users\<username>` or test tokens.

---

## Platform Portability
- **Windows:** Supported via Python 3.10+ and Git for Windows (`.git/hooks/pre-commit` executes in Git Bash subshell).
- **macOS & Linux:** Native execution using `python3` and POSIX `sh`.

#!/usr/bin/env python3
"""
Trajectory Efficiency Auditor for Antigravity.
Cross-platform, zero-dependency auditor for analyzing Antigravity agent transcripts,
correlating unlabeled conversations to repositories, detecting command execution failures,
and synthesizing systemic remediation recommendations.
"""

import os
import sys
import json
import re
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# Ensure UTF-8 output across all environments
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def clean_str(val):
    if not val or not isinstance(val, str):
        return ""
    v = val.strip(' \t\r\n"\'')
    if v.startswith("file:///"):
        v = v.replace("file:///", "").replace("%3A", ":")
        if platform.system() == "Windows":
            v = v.replace("/", "\\")
    return v


def norm_path(p_str):
    if not p_str:
        return ""
    cp = clean_str(p_str)
    try:
        res = os.path.abspath(cp)
        return os.path.normcase(res) if platform.system() == "Windows" else res
    except Exception:
        return cp


def locate_antigravity_dir():
    custom = os.environ.get("ANTIGRAVITY_DATA_DIR")
    if custom and Path(custom).exists():
        return Path(custom)
    default_dir = Path.home() / ".gemini" / "antigravity"
    if default_dir.exists():
        return default_dir
    default_ide = Path.home() / ".gemini" / "antigravity-ide"
    if default_ide.exists():
        return default_ide
    return Path.home() / ".gemini"


def locate_brain_directories(base_dir=None):
    brain_dirs = []
    custom = os.environ.get("ANTIGRAVITY_DATA_DIR")
    if custom:
        p = Path(custom)
        if (p / "brain").exists() and (p / "brain") not in brain_dirs:
            brain_dirs.append(p / "brain")
        elif p.exists() and p not in brain_dirs:
            brain_dirs.append(p)

    gemini_dir = Path.home() / ".gemini"
    for sub in ["antigravity-ide", "antigravity", "antigravity-cli"]:
        b = gemini_dir / sub / "brain"
        if b.exists() and b not in brain_dirs:
            brain_dirs.append(b)

    b_direct = gemini_dir / "brain"
    if b_direct.exists() and b_direct not in brain_dirs:
        brain_dirs.append(b_direct)

    if base_dir and (base_dir / "brain").exists() and (base_dir / "brain") not in brain_dirs:
        brain_dirs.append(base_dir / "brain")

    return brain_dirs


def locate_ide_workspace_storage():
    system = platform.system()
    home = Path.home()
    candidates = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Antigravity IDE" / "User" / "workspaceStorage")
            candidates.append(Path(appdata) / "Antigravity" / "User" / "workspaceStorage")
    elif system == "Darwin":
        candidates.append(home / "Library" / "Application Support" / "Antigravity IDE" / "User" / "workspaceStorage")
        candidates.append(home / "Library" / "Application Support" / "Antigravity" / "User" / "workspaceStorage")
    else:  # Linux / FreeBSD
        config_dir = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        candidates.append(Path(config_dir) / "Antigravity IDE" / "User" / "workspaceStorage")
        candidates.append(Path(config_dir) / "Antigravity" / "User" / "workspaceStorage")

    for c in candidates:
        if c.exists():
            return c
    return None


def discover_ide_workspaces(ws_storage_dir):
    workspaces = []
    if not ws_storage_dir or not ws_storage_dir.exists():
        return workspaces

    for item in ws_storage_dir.iterdir():
        ws_json = item / "workspace.json"
        if ws_json.exists():
            try:
                mtime = os.path.getmtime(ws_json)
                with open(ws_json, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    uri = data.get("folder") or data.get("workspace")
                    if uri:
                        cp = clean_str(uri)
                        workspaces.append({
                            "storage_id": item.name,
                            "mtime": mtime,
                            "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "raw_uri": uri,
                            "norm_path": norm_path(cp),
                            "display_path": cp
                        })
            except Exception:
                pass

    workspaces.sort(key=lambda x: x["mtime"], reverse=True)
    return workspaces


def discover_git_repositories(ide_workspaces, base_dir):
    repos = {}
    search_dirs = [
        Path.home() / "Documents" / "repos",
        Path.home() / "Documents" / "Projects",
        Path.home() / "Projects",
        Path.home() / "src",
        Path.home() / "repos",
        Path.home() / "dev",
        Path.home() / "code",
        Path.home() / "workspace",
        Path.home() / "workspaces",
        Path.home() / "Documents",
        base_dir / "scratch"
    ]

    for sd in search_dirs:
        if sd.exists():
            if (sd / ".git").exists():
                np = norm_path(str(sd))
                repos[np] = str(sd.resolve())
            else:
                try:
                    for child in sd.iterdir():
                        if child.is_dir() and (child / ".git").exists():
                            np = norm_path(str(child))
                            repos[np] = str(child.resolve())
                except Exception:
                    pass

    # Include IDE workspaces with a .git directory
    for ws in ide_workspaces:
        p_str = ws["display_path"]
        p = Path(p_str)
        if p.exists() and (p / ".git").exists():
            repos[norm_path(p_str)] = str(p.resolve())

    return repos


def query_git_metadata(repo_path):
    branch = "unknown"
    last_commit = "unknown"
    is_dirty = False
    remote = ""

    try:
        res = subprocess.run(["git", "-C", repo_path, "branch", "--show-current"], capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout.strip():
            branch = res.stdout.strip()
        else:
            res2 = subprocess.run(["git", "-C", repo_path, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=4)
            if res2.returncode == 0 and res2.stdout.strip():
                branch = f"detached:{res2.stdout.strip()}"

        res = subprocess.run(["git", "-C", repo_path, "log", "-1", "--format=%cd | %s", "--date=short"], capture_output=True, text=True, timeout=4)
        if res.returncode == 0:
            last_commit = res.stdout.strip()

        res = subprocess.run(["git", "-C", repo_path, "status", "-s"], capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout.strip():
            is_dirty = True

        res = subprocess.run(["git", "-C", repo_path, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=4)
        if res.returncode == 0:
            remote = res.stdout.strip()
    except Exception:
        pass

    return {
        "branch": branch,
        "last_commit": last_commit,
        "is_dirty": is_dirty,
        "remote": remote
    }


def parse_conversations(brain_dirs, candidate_repos, max_conversations=50):
    sorted_repo_norms = sorted(list(candidate_repos.keys()), key=lambda x: len(x), reverse=True)
    conversations = []
    seen_conv_ids = set()
    conv_candidates = []

    if isinstance(brain_dirs, Path):
        brain_dirs = [brain_dirs]

    for brain_dir in brain_dirs:
        if not brain_dir or not brain_dir.exists():
            continue

        for item in brain_dir.iterdir():
            if not item.is_dir() or item.name == "tempmediaStorage" or item.name in seen_conv_ids:
                continue

            tpath = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not tpath.exists():
                continue

            seen_conv_ids.add(item.name)
            try:
                mtime = os.path.getmtime(item)
                conv_candidates.append((mtime, item, tpath))
            except Exception:
                pass

    conv_candidates.sort(key=lambda x: x[0], reverse=True)
    total_candidates = len(conv_candidates)
    if max_conversations and max_conversations > 0:
        conv_candidates = conv_candidates[:max_conversations]

    for mtime, item, tpath in conv_candidates:
        first_prompt = ""
        user_prompts = []
        active_ws = ""
        touched_paths = set()
        command_steps = []

        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                steps = [json.loads(line) for line in f if line.strip()]
        except Exception:
            continue

        for i, step in enumerate(steps):
            st = step.get("type")
            content = step.get("content", "")

            if st == "USER_INPUT":
                p_clean = content.strip().replace("\r", " ").replace("\n", " ")
                if "<USER_REQUEST>" in p_clean:
                    start = p_clean.find("<USER_REQUEST>") + len("<USER_REQUEST>")
                    end = p_clean.find("</USER_REQUEST>")
                    p_clean = p_clean[start:end].strip() if end != -1 else p_clean[start:].strip()
                if not first_prompt:
                    first_prompt = p_clean[:200]
                user_prompts.append(p_clean[:120])

            if "<user_information>" in content:
                for line in content.split("\n"):
                    if "active workspace is" in line.lower():
                        cand = line.split("active workspace is")[-1].strip().rstrip(".")
                        if cand:
                            active_ws = norm_path(cand)

            tc_list = step.get("tool_calls", [])
            for tc in tc_list:
                tname = tc.get("name")
                args = tc.get("args") or tc.get("arguments") or {}
                if isinstance(args, dict):
                    for k in ["Cwd", "TargetFile", "AbsolutePath"]:
                        v = args.get(k)
                        if v and isinstance(v, str):
                            np = norm_path(v)
                            if np:
                                touched_paths.add(np)

                if tname == "run_command":
                    # Look ahead for response
                    resp_content = ""
                    exit_code = None
                    for j in range(i + 1, min(i + 4, len(steps))):
                        m_content = steps[j].get("content", "")
                        if "exited with code" in m_content or "finished with result:" in m_content:
                            resp_content = m_content
                            m = re.search(r"exited with code (-?\d+)", m_content)
                            if m:
                                exit_code = int(m.group(1))
                            break

                    is_failed = False
                    if exit_code is not None and exit_code != 0:
                        is_failed = True
                    elif any(err in resp_content for err in ["ParserError:", "SyntaxError:", "CommandNotFoundException", "The term", "Traceback (most recent call last):"]):
                        is_failed = True

                    command_steps.append({
                        "step_index": i,
                        "command": clean_str(args.get("CommandLine")),
                        "cwd": clean_str(args.get("Cwd")),
                        "summary": clean_str(args.get("toolSummary")),
                        "action": clean_str(args.get("toolAction")),
                        "exit_code": exit_code,
                        "is_failed": is_failed,
                        "response_snippet": resp_content[:250]
                    })

        # Infer associated repository
        matched_repo_norm = None
        if active_ws:
            for rn in sorted_repo_norms:
                if active_ws == rn or active_ws.startswith(rn + os.sep) or active_ws.startswith(rn + "\\"):
                    matched_repo_norm = rn
                    break

        if not matched_repo_norm:
            for tp in touched_paths:
                for rn in sorted_repo_norms:
                    if tp == rn or tp.startswith(rn + os.sep) or tp.startswith(rn + "\\"):
                        matched_repo_norm = rn
                        break
                if matched_repo_norm:
                    break

        if not matched_repo_norm:
            low_prompts = " ".join(user_prompts).lower()
            for rn in sorted_repo_norms:
                rname = Path(candidate_repos[rn]).name.lower()
                if len(rname) >= 4 and rname in low_prompts:
                    matched_repo_norm = rn
                    break

        repo_display = candidate_repos[matched_repo_norm] if matched_repo_norm else "General Environment"

        conversations.append({
            "id": item.name,
            "mtime": mtime,
            "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "repo_norm": matched_repo_norm,
            "repo_path": repo_display,
            "first_prompt": first_prompt,
            "commands": command_steps
        })

    return conversations, total_candidates


def classify_failure(cmd, response_snippet, exit_code):
    snip = response_snippet.lower()
    cmd_lower = cmd.lower()

    if any(p in cmd_lower for p in ["py -c", "python -c", "node -e", "bash -c", "powershell -c"]):
        return "Inline Script Quoting Collapse"
    if "charmap" in snip or "unicodeencodeerror" in snip:
        return "Console Encoding Trap (Non-UTF8 Stream)"
    if any(k in snip for k in ["parsererror", "syntaxerror near unexpected token", "unterminated quoted string", "syntaxerror: unterminated"]):
        return "Shell Parser / Quoting Error"
    if any(k in snip for k in ["command not found", "is not recognized as", "commandnotfoundexception"]):
        return "Missing Host Binary / Tool"
    if any(k in snip for k in ["err_module_not_found", "cannot find module", "eresolve unable to resolve dependency tree", "err_pnpm_outdated_lockfile", "npm err!"]):
        return "JavaScript / Node Module or Lockfile Error"
    if any(k in snip for k in ["error ts", "tsc : error", "ts2304", "ts2307", "ts2322"]):
        return "TypeScript Compilation / Type Check Failure"
    if ("cannot open" in snip and "for writing" in snip) or "being used by another process" in snip or "text file busy" in snip:
        return "Process File Lock Collision"
    if "eaddrinuse" in snip or "address already in use" in snip:
        return "Port / Network Socket Collision"
    if "permission denied" in snip or "eacces" in snip:
        return "Filesystem / Permission Denied"
    if "no module named" in snip or "importerror" in snip:
        return "Missing Python Dependency / Path"
    if any(k in snip for k in ["cargo build", "cargo check"]) and ("error[e" in snip or "failed to compile" in snip):
        return "Rust Cargo Compilation Failure"
    if ("go build" in cmd_lower or "go test" in cmd_lower) and ("no required module provides package" in snip or "undefined:" in snip):
        return "Go Module / Build Failure"
    if "fatal: " in snip or "pathspec" in snip:
        return "Git Remote / Branch Safety Error"
    return f"Runtime Execution Failure (Exit Code {exit_code})"


def run_audit(output_dir=None, max_conversations=50):
    base_dir = locate_antigravity_dir()
    brain_dirs = locate_brain_directories(base_dir)
    ws_storage_dir = locate_ide_workspace_storage()

    print(f"=== Antigravity Trajectory Auditor ===")
    print(f"Platform: {platform.system()} ({platform.machine()})")
    print(f"Antigravity Data Dir: {base_dir}")
    print(f"Brain Storage Locations: {len(brain_dirs)}")
    print(f"IDE Storage Dir: {ws_storage_dir or 'Not found'}")

    ide_workspaces = discover_ide_workspaces(ws_storage_dir)
    print(f"Discovered IDE Workspaces: {len(ide_workspaces)}")

    candidate_repos = discover_git_repositories(ide_workspaces, base_dir)
    print(f"Discovered Git Repositories: {len(candidate_repos)}")

    conversations, total_candidates = parse_conversations(brain_dirs, candidate_repos, max_conversations=max_conversations)
    print(f"Parsed Active Conversations: {len(conversations)} (out of {total_candidates} discovered)")

    # Aggregate metrics
    total_commands = 0
    total_failures = 0
    failures_by_category = Counter()
    failures_by_repo = Counter()
    failure_records = []

    for conv in conversations:
        for cmd_entry in conv["commands"]:
            total_commands += 1
            if cmd_entry["is_failed"]:
                total_failures += 1
                cat = classify_failure(cmd_entry["command"], cmd_entry["response_snippet"], cmd_entry["exit_code"])
                failures_by_category[cat] += 1
                failures_by_repo[conv["repo_path"]] += 1
                failure_records.append({
                    "conversation_id": conv["id"],
                    "date": conv["date"],
                    "repo": conv["repo_path"],
                    "category": cat,
                    "command": cmd_entry["command"],
                    "summary": cmd_entry["summary"],
                    "exit_code": cmd_entry["exit_code"],
                    "error_snippet": cmd_entry["response_snippet"][:180]
                })

    failure_rate = (total_failures / total_commands * 100) if total_commands > 0 else 0.0

    print(f"\nTotal Commands Executed: {total_commands}")
    print(f"Total Command Failures: {total_failures} ({failure_rate:.2f}% failure rate)")

    print("\nFailures by Category:")
    for cat, count in failures_by_category.most_common():
        print(f"  - {cat}: {count} ({(count / total_failures * 100):.1f}%)")

    print("\nFailures by Repository:")
    for repo, count in failures_by_repo.most_common(10):
        print(f"  - {Path(repo).name}: {count} failures")

    # Generate output json
    out_dir = Path(output_dir) if output_dir else Path.cwd()
    out_file = out_dir / "trajectory_audit_summary.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "audit_timestamp": datetime.now().isoformat(),
            "platform": platform.system(),
            "total_conversations": len(conversations),
            "total_commands": total_commands,
            "total_failures": total_failures,
            "failure_rate_pct": round(failure_rate, 2),
            "failures_by_category": dict(failures_by_category),
            "failures_by_repo": dict(failures_by_repo),
            "top_failures": failure_records[:30]
        }, f, indent=2)

    print(f"\nAudit complete. Structured summary written to: {out_file}")
    return out_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trajectory Efficiency Auditor for Antigravity")
    parser.add_argument("output_dir", nargs="?", default=None, help="Directory to save trajectory_audit_summary.json")
    parser.add_argument("--limit", type=int, default=50, help="Max recent conversations to parse (default 50)")
    parser.add_argument("--all", action="store_true", help="Parse all conversations without limit")
    args = parser.parse_args()

    conv_limit = None if args.all else args.limit
    run_audit(args.output_dir, max_conversations=conv_limit)

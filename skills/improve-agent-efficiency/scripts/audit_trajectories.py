#!/usr/bin/env python3
"""
Trajectory Efficiency Auditor for Antigravity.
Cross-platform, zero-dependency auditor for analyzing Antigravity agent transcripts,
correlating unlabeled conversations to repositories, detecting command execution failures,
mining causal retry chains (initial failure -> retries -> eventual resolution),
measuring token burn and context consumption, evaluating efficiency gains over time,
and synthesizing systemic remediation recommendations.
"""

import os
import sys
import json
import re
import platform
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
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


def find_git_root(path_str):
    """Ascends directory tree to identify enclosing git repository root."""
    if not path_str:
        return None
    try:
        p = Path(clean_str(path_str))
        if not p.is_dir() and p.parent.exists():
            p = p.parent
        for candidate in [p] + list(p.parents):
            if (candidate / ".git").exists():
                return str(candidate.resolve())
    except Exception:
        pass
    return None


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
    else:  # Linux
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

    for ws in ide_workspaces:
        p_str = ws["display_path"]
        p = Path(p_str)
        if p.exists() and (p / ".git").exists():
            repos[norm_path(p_str)] = str(p.resolve())

    return repos


def is_benign_search_query(cmd, exit_code, resp_content):
    """
    Identifies search or pattern matching tools (rg, ripgrep, grep, findstr, diff)
    where exit code 1 denotes zero matches found or non-zero differences rather than an execution crash.
    """
    if exit_code != 1:
        return False
    cmd_lower = (cmd or "").strip().lower()
    is_search = bool(re.search(r'(^|[|;&\s])(rg|ripgrep|grep|findstr|diff)\b', cmd_lower))
    if not is_search:
        return False
    resp_lower = (resp_content or "").lower()
    error_signals = [
        "error:", "fatal:", "invalid option", "unrecognized option",
        "commandnotfound", "the term '", "syntaxerror", "permission denied"
    ]
    if any(sig in resp_lower for sig in error_signals):
        return False
    return True


def classify_failure(cmd, response_snippet, exit_code):
    snip = (response_snippet or "").lower()
    cmd_lower = (cmd or "").lower()

    if any(p in cmd_lower for p in ["py -c", "python -c", "node -e", "bash -c", "powershell -c"]):
        return "Inline Script Quoting Collapse"
    if "charmap" in snip or "unicodeencodeerror" in snip:
        return "Console Encoding Trap (Non-UTF8 Stream)"
    if any(k in snip for k in ["parsererror", "syntaxerror near unexpected token", "unterminated quoted string", "syntaxerror: unterminated", "syntaxerror: '(' was never closed"]):
        return "Shell Parser / Quoting Error"
    if any(k in snip for k in ["command not found", "is not recognized as", "commandnotfoundexception", "the term"]):
        return "Missing Host Binary / Tool"
    if any(k in snip for k in ["err_module_not_found", "cannot find module", "eresolve unable to resolve dependency tree", "err_pnpm_outdated_lockfile", "npm err!"]):
        return "JavaScript / Node Module or Lockfile Error"
    if any(k in snip for k in ["error ts", "tsc : error", "ts2304", "ts2307", "ts2322"]):
        return "TypeScript Compilation / Type Check Failure"
    if ("cannot open" in snip and "for writing" in snip) or "being used by another process" in snip or "text file busy" in snip or "error cs2012" in snip:
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
    if "fatal: " in snip or "pathspec" in snip or "forbidden_do_not_push" in snip:
        return "Git Remote / Branch Safety Error"
    return f"Runtime Execution Failure (Exit Code {exit_code})"


def parse_conversations(brain_dirs, candidate_repos, max_conversations=50, since_dt=None, target_repo=None, exclude_repo=None, compare_mode=False):
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
                conv_dt = datetime.fromtimestamp(mtime)
                # When comparing, we keep both cohorts (target >= since_dt and baseline < since_dt)
                if since_dt and not compare_mode and conv_dt < since_dt:
                    continue
                conv_candidates.append((mtime, item, tpath, conv_dt))
            except Exception:
                pass

    conv_candidates.sort(key=lambda x: x[0], reverse=True)
    total_candidates = len(conv_candidates)
    if max_conversations and max_conversations > 0:
        conv_candidates = conv_candidates[:max_conversations]

    for mtime, item, tpath, conv_dt in conv_candidates:
        first_prompt = ""
        user_prompts = []
        active_ws = ""
        touched_paths = set()
        action_trace = []
        user_turn_indices = []

        total_prompt_chars = 0
        total_resp_chars = 0
        total_thinking_chars = 0
        total_tool_output_chars = 0
        file_views_count = 0
        file_views_unbounded = 0
        file_views_bounded = 0
        user_turns_count = 0

        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                steps = [json.loads(line) for line in f if line.strip()]
        except Exception:
            continue

        for i, step in enumerate(steps):
            st = step.get("type", "")
            source = step.get("source", "")
            content = step.get("content", "") or ""
            thinking = step.get("thinking", "") or ""

            if st == "USER_INPUT" or source == "USER_EXPLICIT":
                user_turns_count += 1
                user_turn_indices.append(i)
                total_prompt_chars += len(content)
                p_clean = content.strip().replace("\r", " ").replace("\n", " ")
                if "<USER_REQUEST>" in p_clean:
                    start = p_clean.find("<USER_REQUEST>") + len("<USER_REQUEST>")
                    end = p_clean.find("</USER_REQUEST>")
                    p_clean = p_clean[start:end].strip() if end != -1 else p_clean[start:].strip()
                if not first_prompt:
                    first_prompt = p_clean[:200]
                user_prompts.append(p_clean[:120])
            elif st == "PLANNER_RESPONSE" or source == "MODEL":
                total_resp_chars += len(content)
                total_thinking_chars += len(thinking)
            else:
                total_tool_output_chars += len(content)

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
                if not isinstance(args, dict):
                    continue

                for k in ["Cwd", "TargetFile", "AbsolutePath"]:
                    v = args.get(k)
                    if v and isinstance(v, str):
                        np = norm_path(v)
                        if np:
                            touched_paths.add(np)
                            git_root = find_git_root(v)
                            if git_root:
                                gn = norm_path(git_root)
                                if gn not in candidate_repos:
                                    candidate_repos[gn] = git_root
                                    sorted_repo_norms = sorted(list(candidate_repos.keys()), key=lambda x: len(x), reverse=True)

                if tname in ["write_to_file", "replace_file_content"]:
                    action_trace.append({
                        "step_index": i,
                        "tool": tname,
                        "target_file": clean_str(args.get("TargetFile")),
                        "is_command": False
                    })

                elif tname == "view_file":
                    file_views_count += 1
                    s_line = args.get("StartLine")
                    e_line = args.get("EndLine")
                    if s_line is not None and e_line is not None:
                        file_views_bounded += 1
                    else:
                        file_views_unbounded += 1

                elif tname == "run_command":
                    exit_code = None
                    resp_content = ""
                    for j in range(i + 1, min(i + 4, len(steps))):
                        m_content = steps[j].get("content", "")
                        if "exited with code" in m_content or "finished with result:" in m_content:
                            resp_content = m_content
                            m = re.search(r"exited with code (-?\d+)", m_content)
                            if m:
                                exit_code = int(m.group(1))
                            break

                    is_failed = False
                    cmd_str = clean_str(args.get("CommandLine"))
                    if exit_code is not None:
                        if exit_code != 0:
                            if is_benign_search_query(cmd_str, exit_code, resp_content):
                                is_failed = False
                            else:
                                is_failed = True
                    elif any(err in resp_content for err in ["ParserError:", "SyntaxError:", "CommandNotFoundException", "The term", "Traceback (most recent call last):"]):
                        is_failed = True

                    action_trace.append({
                        "step_index": i,
                        "turn_index": len(user_turn_indices),
                        "tool": "run_command",
                        "command": cmd_str,
                        "cwd": clean_str(args.get("Cwd")),
                        "summary": clean_str(args.get("toolSummary")),
                        "action": clean_str(args.get("toolAction")),
                        "exit_code": exit_code,
                        "is_failed": is_failed,
                        "response_snippet": resp_content[:500],
                        "is_command": True
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

        if target_repo and target_repo.lower() not in repo_display.lower():
            continue

        if exclude_repo:
            if any(ex.lower() in repo_display.lower() for ex in exclude_repo if ex):
                continue

        # Mine Incident Chains
        incident_chains = []
        commands_only = [a for a in action_trace if a["is_command"]]

        k = 0
        while k < len(action_trace):
            act = action_trace[k]
            if act["is_command"] and act["is_failed"]:
                cat = classify_failure(act["command"], act["response_snippet"], act["exit_code"])
                turn_id = act["turn_index"]
                incident = {
                    "incident_id": f"{item.name}_{act['step_index']}",
                    "conversation_id": item.name,
                    "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "repo": repo_display,
                    "turn_index": turn_id,
                    "initial_step": act["step_index"],
                    "initial_command": act["command"],
                    "category": cat,
                    "initial_exit_code": act["exit_code"],
                    "error_snippet": act["response_snippet"][:350],
                    "retries": [],
                    "intervening_file_writes": [],
                    "eventual_working_command": None,
                    "resolved": False
                }

                look_ahead_idx = k + 1
                max_look = min(len(action_trace), k + 12)
                while look_ahead_idx < max_look:
                    next_act = action_trace[look_ahead_idx]
                    if next_act.get("turn_index", turn_id) > turn_id + 1:
                        break

                    if not next_act["is_command"]:
                        tf = next_act.get("target_file")
                        if tf and tf not in incident["intervening_file_writes"]:
                            incident["intervening_file_writes"].append(tf)
                    else:
                        if next_act["is_failed"]:
                            incident["retries"].append({
                                "step_index": next_act["step_index"],
                                "command": next_act["command"],
                                "exit_code": next_act["exit_code"],
                                "error_snippet": next_act["response_snippet"][:200]
                            })
                        else:
                            incident["eventual_working_command"] = next_act["command"]
                            incident["resolved"] = True
                            k = look_ahead_idx
                            break
                    look_ahead_idx += 1

                incident["retry_count"] = len(incident["retries"])
                incident_chains.append(incident)
            k += 1

        prompt_tok = round(total_prompt_chars / 4)
        resp_tok = round(total_resp_chars / 4)
        think_tok = round(total_thinking_chars / 4)
        tool_tok = round(total_tool_output_chars / 4)

        conversations.append({
            "id": item.name,
            "mtime": mtime,
            "dt": conv_dt,
            "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "repo_norm": matched_repo_norm,
            "repo_path": repo_display,
            "first_prompt": first_prompt,
            "commands": commands_only,
            "incident_chains": incident_chains,
            "user_turns": user_turns_count,
            "prompt_tokens": prompt_tok,
            "resp_tokens": resp_tok,
            "thinking_tokens": think_tok,
            "tool_tokens": tool_tok,
            "total_tokens": prompt_tok + resp_tok + think_tok + tool_tok,
            "file_views": file_views_count,
            "unbounded_views": file_views_unbounded,
            "bounded_views": file_views_bounded
        })

    return conversations, total_candidates


def calculate_cohort_summary(conv_list):
    total_convs = len(conv_list)
    total_user_turns = sum(c["user_turns"] for c in conv_list)
    total_commands = sum(len(c["commands"]) for c in conv_list)
    total_failures = sum(sum(1 for cmd in c["commands"] if cmd["is_failed"]) for c in conv_list)
    
    failures_by_category = Counter()
    failures_by_repo = Counter()
    all_incidents = []
    py_c_count = 0
    bash_syntax_count = 0

    for c in conv_list:
        for cmd_entry in c["commands"]:
            cmd = cmd_entry["command"]
            if any(p in cmd.lower() for p in ["py -c", "python -c", "node -e"]):
                py_c_count += 1
            if re.search(r"\b(grep|cat|rm -rf|ls -la)\b", cmd):
                bash_syntax_count += 1
            if cmd_entry["is_failed"]:
                cat = classify_failure(cmd, cmd_entry["response_snippet"], cmd_entry["exit_code"])
                failures_by_category[cat] += 1
                failures_by_repo[c["repo_path"]] += 1

        for inc in c["incident_chains"]:
            all_incidents.append(inc)

    failure_rate = (total_failures / total_commands * 100) if total_commands > 0 else 0.0
    high_friction = [inc for inc in all_incidents if inc["retry_count"] >= 1 or not inc["resolved"]]

    total_prompt_tok = sum(c["prompt_tokens"] for c in conv_list)
    total_resp_tok = sum(c["resp_tokens"] for c in conv_list)
    total_think_tok = sum(c["thinking_tokens"] for c in conv_list)
    total_tool_tok = sum(c["tool_tokens"] for c in conv_list)
    total_tokens = sum(c["total_tokens"] for c in conv_list)

    total_views = sum(c["file_views"] for c in conv_list)
    total_unbounded = sum(c["unbounded_views"] for c in conv_list)
    unbounded_pct = (total_unbounded / total_views * 100) if total_views > 0 else 0.0

    tokens_per_conv = round(total_tokens / total_convs) if total_convs > 0 else 0
    tokens_per_turn = round(total_tokens / total_user_turns) if total_user_turns > 0 else 0

    return {
        "conversations": total_convs,
        "user_turns": total_user_turns,
        "commands": total_commands,
        "failures": total_failures,
        "failure_rate_pct": round(failure_rate, 2),
        "total_incidents": len(all_incidents),
        "high_friction_count": len(high_friction),
        "py_c_inline": py_c_count,
        "bash_syntax": bash_syntax_count,
        "file_views": total_views,
        "unbounded_views": total_unbounded,
        "unbounded_view_pct": round(unbounded_pct, 2),
        "total_tokens": total_tokens,
        "prompt_tokens": total_prompt_tok,
        "response_tokens": total_resp_tok,
        "thinking_tokens": total_think_tok,
        "tool_tokens": total_tool_tok,
        "tokens_per_conv": tokens_per_conv,
        "tokens_per_turn": tokens_per_turn,
        "failures_by_category": dict(failures_by_category),
        "failures_by_repo": dict(failures_by_repo),
        "high_friction_incidents": high_friction
    }


def format_delta(current, baseline, lower_is_better=True, is_pct=False):
    if baseline == 0:
        return f"{current}"
    diff = current - baseline
    pct_change = (diff / baseline) * 100.0
    sign = "+" if diff > 0 else ""
    unit = "%" if is_pct else ""

    improved = (diff < 0) if lower_is_better else (diff > 0)
    tag = "IMPROVED" if improved else ("DRIFT" if diff != 0 else "FLAT")
    return f"{sign}{diff:.2f}{unit} ({sign}{pct_change:.1f}% {tag})"


def run_inventory(output_dir=None):
    base_dir = locate_antigravity_dir()
    brain_dirs = locate_brain_directories(base_dir)
    ws_storage_dir = locate_ide_workspace_storage()

    ide_workspaces = discover_ide_workspaces(ws_storage_dir)
    candidate_repos = discover_git_repositories(ide_workspaces, base_dir)

    earliest_dt = None
    latest_dt = None
    total_convs = 0

    seen_ids = set()
    for brain_dir in brain_dirs:
        if not brain_dir or not brain_dir.exists():
            continue
        for item in brain_dir.iterdir():
            if not item.is_dir() or item.name == "tempmediaStorage" or item.name in seen_ids:
                continue
            tpath = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not tpath.exists():
                continue
            seen_ids.add(item.name)
            total_convs += 1
            try:
                mtime = os.path.getmtime(tpath)
                dt = datetime.fromtimestamp(mtime)
                if earliest_dt is None or dt < earliest_dt:
                    earliest_dt = dt
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
            except Exception:
                pass

    cwd_git = find_git_root(os.getcwd())
    active_ws_display = Path(cwd_git).name if cwd_git else "General Environment"

    repo_list = []
    for r_norm, r_path in candidate_repos.items():
        repo_list.append({
            "name": Path(r_path).name,
            "path": r_path
        })
    repo_list.sort(key=lambda x: x["name"].lower())

    inventory_data = {
        "timestamp": datetime.now().isoformat(),
        "total_conversations": total_convs,
        "earliest_session": earliest_dt.strftime("%Y-%m-%d %H:%M:%S") if earliest_dt else None,
        "latest_session": latest_dt.strftime("%Y-%m-%d %H:%M:%S") if latest_dt else None,
        "active_workspace": active_ws_display,
        "total_discovered_repositories": len(repo_list),
        "repositories": repo_list
    }

    out_dir = Path(output_dir) if output_dir else Path.cwd()
    out_file = out_dir / "trajectory_inventory.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(inventory_data, f, indent=2)

    print(f"=== Antigravity Rapid Inventory ===")
    print(f"Total Conversations Found: {total_convs}")
    print(f"Date Range: {inventory_data['earliest_session']} -> {inventory_data['latest_session']}")
    print(f"Discovered Repositories: {len(repo_list)}")
    print(f"Inventory saved to: {out_file}")
    return out_file


def run_audit(output_dir=None, max_conversations=100, since_date=None, target_repo=None, exclude_repo=None, compare_mode=False):
    base_dir = locate_antigravity_dir()
    brain_dirs = locate_brain_directories(base_dir)
    ws_storage_dir = locate_ide_workspace_storage()

    since_dt = None
    if since_date:
        try:
            since_dt = datetime.fromisoformat(since_date)
        except Exception:
            try:
                since_dt = datetime.strptime(since_date, "%Y-%m-%d")
            except Exception:
                print(f"Warning: Could not parse --since '{since_date}'. Ignoring filter.")

    if compare_mode and not since_dt:
        # Default compare mode to last 24 hours if no since_date passed
        since_dt = datetime.now() - timedelta(hours=24)

    exclude_list = []
    if exclude_repo:
        if isinstance(exclude_repo, str):
            exclude_list = [e.strip() for e in exclude_repo.split(",") if e.strip()]
        else:
            exclude_list = list(exclude_repo)

    print(f"=== Antigravity Trajectory Auditor ===")
    print(f"Platform: {platform.system()} ({platform.machine()})")
    print(f"Antigravity Data Dir: {base_dir}")
    print(f"Brain Storage Locations: {len(brain_dirs)}")
    print(f"Since Filter: {since_dt.strftime('%Y-%m-%d %H:%M:%S') if since_dt else 'None'}")
    print(f"Mode: {'Comparative Efficiency Gains (--compare)' if compare_mode else 'Standard Trajectory Audit'}")
    print(f"Target Repo: {target_repo or 'All'}")
    print(f"Exclude Repos: {', '.join(exclude_list) if exclude_list else 'None'}")

    ide_workspaces = discover_ide_workspaces(ws_storage_dir)
    candidate_repos = discover_git_repositories(ide_workspaces, base_dir)

    all_convs, total_candidates = parse_conversations(
        brain_dirs=brain_dirs,
        candidate_repos=candidate_repos,
        max_conversations=max_conversations,
        since_dt=since_dt,
        target_repo=target_repo,
        exclude_repo=exclude_list,
        compare_mode=compare_mode
    )

    out_dir = Path(output_dir) if output_dir else Path.cwd()
    out_file = out_dir / "trajectory_audit_summary.json"

    if compare_mode and since_dt:
        # Partition conversations
        target_convs = [c for c in all_convs if c["dt"] >= since_dt]
        baseline_convs = [c for c in all_convs if c["dt"] < since_dt]

        target_summary = calculate_cohort_summary(target_convs)
        baseline_summary = calculate_cohort_summary(baseline_convs)

        print(f"\nParsed Conversations: {len(target_convs)} target (post {since_dt.strftime('%Y-%m-%d %H:%M')}) vs {len(baseline_convs)} baseline")

        print("\n" + "=" * 78)
        print("                 EFFICIENCY GAINS & TOKEN BURN COMPARISON")
        print("=" * 78)
        header_fmt = "{:<32} {:<15} {:<15} {:<16}"
        print(header_fmt.format("Metric", "Baseline", "Target Window", "Delta / Outcome"))
        print("-" * 78)

        def print_row(label, base_val, tgt_val, lower_is_better=True, is_pct=False, val_suffix=""):
            delta_str = format_delta(tgt_val, base_val, lower_is_better=lower_is_better, is_pct=is_pct)
            b_str = f"{base_val}{val_suffix}"
            t_str = f"{tgt_val}{val_suffix}"
            print(header_fmt.format(label, b_str, t_str, delta_str))

        print_row("Active Conversations", baseline_summary["conversations"], target_summary["conversations"], lower_is_better=False)
        print_row("Total User Turns", baseline_summary["user_turns"], target_summary["user_turns"], lower_is_better=False)
        print_row("True Failure Rate", baseline_summary["failure_rate_pct"], target_summary["failure_rate_pct"], lower_is_better=True, is_pct=True, val_suffix="%")
        print_row("High-Friction Loops", baseline_summary["high_friction_count"], target_summary["high_friction_count"], lower_is_better=True)
        print_row("Inline py -c / node -e", baseline_summary["py_c_inline"], target_summary["py_c_inline"], lower_is_better=True)
        print_row("Bash Syntax Usage", baseline_summary["bash_syntax"], target_summary["bash_syntax"], lower_is_better=True)
        print_row("Unbounded File Views", baseline_summary["unbounded_view_pct"], target_summary["unbounded_view_pct"], lower_is_better=True, is_pct=True, val_suffix="%")
        print_row("Est. Tokens / Conversation", baseline_summary["tokens_per_conv"], target_summary["tokens_per_conv"], lower_is_better=True)
        print_row("Est. Tokens / User Turn", baseline_summary["tokens_per_turn"], target_summary["tokens_per_turn"], lower_is_better=True)
        print("-" * 78)

        summary_payload = {
            "audit_timestamp": datetime.now().isoformat(),
            "platform": platform.system(),
            "mode": "comparative",
            "since_filter": since_dt.isoformat(),
            "comparison": {
                "target_window": target_summary,
                "baseline_window": baseline_summary
            }
        }
    else:
        summary = calculate_cohort_summary(all_convs)
        print(f"\nParsed Active Conversations: {summary['conversations']} (out of {total_candidates} matching candidates)")
        print(f"Total Commands Executed: {summary['commands']}")
        print(f"True Command Failures: {summary['failures']} ({summary['failure_rate_pct']:.2f}% true failure rate)")
        print(f"Total Incident Chains: {summary['total_incidents']}")
        print(f"High-Friction Loops: {summary['high_friction_count']}")
        print(f"Unbounded View Ratio: {summary['unbounded_view_pct']}% ({summary['unbounded_views']}/{summary['file_views']})")
        print(f"Estimated Tokens / Conversation: {summary['tokens_per_conv']}")
        print(f"Estimated Tokens / User Turn: {summary['tokens_per_turn']}")

        print("\nFailures by Category:")
        for cat, count in sorted(summary["failures_by_category"].items(), key=lambda x: x[1], reverse=True):
            pct = (count / summary['failures'] * 100) if summary['failures'] else 0
            print(f"  - {cat}: {count} ({pct:.1f}%)")

        print("\nFailures by Repository:")
        for repo, count in sorted(summary["failures_by_repo"].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {Path(repo).name}: {count} failures")

        summary_payload = {
            "audit_timestamp": datetime.now().isoformat(),
            "platform": platform.system(),
            "mode": "standard",
            "since_filter": since_dt.isoformat() if since_dt else None,
            "target_repo": target_repo,
            "exclude_filter": exclude_list,
            **summary
        }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    print(f"\nAudit complete. Structured summary written to: {out_file}")
    return out_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trajectory Efficiency Auditor for Antigravity")
    parser.add_argument("output_dir", nargs="?", default=None, help="Directory to save summary json")
    parser.add_argument("--limit", type=int, default=100, help="Max recent conversations to parse (default 100)")
    parser.add_argument("--all", action="store_true", help="Parse all conversations without limit")
    parser.add_argument("--since", type=str, default=None, help="Filter to conversations on or after date (YYYY-MM-DD)")
    parser.add_argument("--repo", type=str, default=None, help="Filter to specific repository substring")
    parser.add_argument("--exclude", type=str, default=None, help="Comma-separated repository names to exclude")
    parser.add_argument("--inventory-only", action="store_true", help="Discover repositories and date boundaries rapidly without parsing transcripts")
    parser.add_argument("--compare", action="store_true", help="Compare target window against baseline history and compute efficiency gains")
    args = parser.parse_args()

    if args.inventory_only:
        run_inventory(args.output_dir)
    else:
        conv_limit = None if args.all else args.limit
        run_audit(
            output_dir=args.output_dir,
            max_conversations=conv_limit,
            since_date=args.since,
            target_repo=args.repo,
            exclude_repo=args.exclude,
            compare_mode=args.compare
        )

#!/usr/bin/env python3
"""
Neutral Trajectory Telemetry Indexer for Antigravity.
Indexes hardware token usage (input, cache_read, output), model inference turns,
tool errors across all tools (commands, edits, reads, MCP), test/build cycles,
scratch script overhead, and search-to-edit thrash ratios without polluting
working directories or imposing hardcoded failure classifications.
"""

import os
import sys
import json
import re
import platform
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

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
    for sub in ["antigravity", "antigravity-ide"]:
        d = Path.home() / ".gemini" / sub
        if d.exists():
            return d
    return Path.home() / ".gemini"


def locate_brain_directories(base_dir=None):
    brain_dirs = []
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


def discover_candidate_repos(base_dir):
    repos = {}
    search_dirs = [
        Path.home() / "Documents" / "repos",
        Path.home() / "Documents" / "Projects",
        Path.home() / "Projects",
        Path.home() / "src",
        Path.home() / "repos",
        Path.home() / "dev",
        Path.home() / "code",
        Path.home() / "Documents",
        base_dir / "scratch",
    ]
    for sd in search_dirs:
        if sd.exists():
            if (sd / ".git").exists():
                repos[norm_path(str(sd))] = str(sd.resolve())
            else:
                try:
                    for child in sd.iterdir():
                        if child.is_dir() and (child / ".git").exists():
                            repos[norm_path(str(child))] = str(child.resolve())
                except Exception:
                    pass
    return repos


def is_benign_search_exit(cmd, exit_code, resp_content):
    if exit_code != 1:
        return False
    cmd_lower = (cmd or "").strip().lower()
    if not re.search(r'(^|[|;&\s])(rg|ripgrep|grep|findstr|diff)\b', cmd_lower):
        return False
    resp_lower = (resp_content or "").lower()
    error_signals = [
        "error:", "fatal:", "invalid option", "unrecognized option",
        "commandnotfound", "the term '", "syntaxerror", "permission denied"
    ]
    return not any(sig in resp_lower for sig in error_signals)


def is_test_or_build_cmd(cmd):
    cmd_lower = (cmd or "").strip().lower()
    patterns = [
        r'\bpytest\b', r'\bvitest\b', r'\bjest\b', r'\bcargo\s+(test|check|build|clippy)\b',
        r'\bdotnet\s+(test|build)\b', r'\bgo\s+(test|build|vet)\b', r'\btsc\b',
        r'\b(npm|pnpm|yarn|bun)\s+(test|run\s+test|run\s+build|run\s+typecheck|run\s+lint)\b'
    ]
    return any(re.search(p, cmd_lower) for p in patterns)


def parse_conversations(brain_dirs, candidate_repos, max_conversations=100, since_dt=None, target_repo=None, exclude_repo=None, compare_mode=False):
    sorted_repo_norms = sorted(list(candidate_repos.keys()), key=len, reverse=True)
    conv_candidates = []
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
            try:
                mtime = os.path.getmtime(tpath)
                conv_dt = datetime.fromtimestamp(mtime)
                if since_dt and not compare_mode and conv_dt < since_dt:
                    continue
                conv_candidates.append((mtime, item, tpath, conv_dt))
            except Exception:
                pass

    conv_candidates.sort(key=lambda x: x[0], reverse=True)
    total_candidates = len(conv_candidates)
    if max_conversations and max_conversations > 0:
        conv_candidates = conv_candidates[:max_conversations]

    conversations = []
    for mtime, item, tpath, conv_dt in conv_candidates:
        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                steps = [json.loads(line) for line in f if line.strip()]
        except Exception:
            continue

        first_prompt = ""
        user_prompts = []
        active_ws = ""
        touched_paths = set()

        user_turns = 0
        model_turns = 0
        hw_input_tokens = 0
        hw_cache_tokens = 0
        hw_output_tokens = 0
        peak_context_tokens = 0
        has_hw_tokens = False
        fallback_char_tokens = 0

        tool_counts = Counter()
        read_search_calls = 0
        edit_write_calls = 0
        scratch_writes = 0
        scratch_runs = 0
        inline_script_runs = 0

        shell_failures = []
        test_build_failures = []
        non_cmd_tool_failures = []

        for i, step in enumerate(steps):
            st = step.get("type", "")
            source = step.get("source", "")
            content = step.get("content", "") or ""
            thinking = step.get("thinking", "") or ""
            fallback_char_tokens += round((len(content) + len(thinking)) / 4)

            if st == "USER_INPUT" or source == "USER_EXPLICIT":
                user_turns += 1
                p_clean = content.strip().replace("\r", " ").replace("\n", " ")
                if "<USER_REQUEST>" in p_clean:
                    start = p_clean.find("<USER_REQUEST>") + len("<USER_REQUEST>")
                    end = p_clean.find("</USER_REQUEST>")
                    p_clean = p_clean[start:end].strip() if end != -1 else p_clean[start:].strip()
                if not first_prompt and p_clean:
                    first_prompt = p_clean[:200]
                if p_clean:
                    user_prompts.append(p_clean[:120])

                if "<user_information>" in content:
                    for line in content.split("\n"):
                        if "active workspace is" in line.lower():
                            cand = line.split("active workspace is")[-1].strip().rstrip(".")
                            if cand:
                                active_ws = norm_path(cand)

            elif st == "PLANNER_RESPONSE" or source == "MODEL":
                if st == "PLANNER_RESPONSE":
                    model_turns += 1
                    in_tok = step.get("input_tokens") or 0
                    cache_tok = step.get("cache_read_tokens") or 0
                    out_tok = step.get("output_tokens") or 0
                    if in_tok or cache_tok or out_tok:
                        has_hw_tokens = True
                        hw_input_tokens += in_tok
                        hw_cache_tokens += cache_tok
                        hw_output_tokens += out_tok
                        ctx = in_tok + cache_tok
                        if ctx > peak_context_tokens:
                            peak_context_tokens = ctx

                tc_list = step.get("tool_calls", [])
                for tc_idx, tc in enumerate(tc_list):
                    tname = tc.get("name") or "unknown"
                    tool_counts[tname] += 1
                    args = tc.get("args") or tc.get("arguments") or {}
                    if not isinstance(args, dict):
                        args = {}

                    for k in ["Cwd", "TargetFile", "AbsolutePath", "Path", "path", "SearchPath", "DirectoryPath"]:
                        v = args.get(k)
                        if v and isinstance(v, str):
                            cv = clean_str(v)
                            # Ignore scratch/brain paths when inferring target repo
                            if "\\brain\\" not in cv.lower() and "/brain/" not in cv.lower():
                                np = norm_path(cv)
                                if np:
                                    touched_paths.add(np)
                                    git_root = find_git_root(cv)
                                    if git_root:
                                        gn = norm_path(git_root)
                                        if gn not in candidate_repos:
                                            candidate_repos[gn] = git_root
                                            sorted_repo_norms = sorted(list(candidate_repos.keys()), key=len, reverse=True)

                    # Find corresponding tool output step
                    resp_step = None
                    resp_idx = i + 1 + tc_idx
                    if resp_idx < len(steps) and steps[resp_idx].get("type") == "GENERIC":
                        resp_step = steps[resp_idx]
                    else:
                        for j in range(i + 1, min(i + 6, len(steps))):
                            if steps[j].get("type") == "GENERIC":
                                resp_step = steps[j]
                                break

                    resp_content = (resp_step.get("content", "") if resp_step else "") or ""
                    resp_status = (resp_step.get("status", "") if resp_step else "") or ""

                    if tname in ["read_file", "view_file", "grep_search", "find_by_name", "list_dir", "view_file_outline", "view_code_item"]:
                        read_search_calls += 1
                    elif tname in ["edit_file", "write_file", "replace_file_content", "write_to_file", "multi_replace_file_content"]:
                        target_p = clean_str(args.get("Path") or args.get("TargetFile") or args.get("path"))
                        if "scratch" in target_p.lower():
                            scratch_writes += 1
                        else:
                            edit_write_calls += 1

                    if tname == "run_command":
                        cmd_str = clean_str(args.get("CommandLine"))
                        cmd_lower = cmd_str.lower()
                        if "scratch" in cmd_lower:
                            scratch_runs += 1
                        if any(p in cmd_lower for p in ["py -c", "python -c", "node -e", "pwsh -c", "powershell -c"]):
                            inline_script_runs += 1
                        if re.search(r'(^|[|;&\s])(rg|Get-ChildItem|Select-String|git\s+(status|diff|log|show))\b', cmd_str, re.I):
                            read_search_calls += 1

                        exit_code = None
                        m = re.search(r"exited with code (-?\d+)", resp_content)
                        if m:
                            exit_code = int(m.group(1))

                        is_err = False
                        if exit_code is not None and exit_code != 0:
                            if not is_benign_search_exit(cmd_str, exit_code, resp_content):
                                is_err = True
                        elif resp_status == "ERROR" or any(e in resp_content for e in ["ParserError:", "CommandNotFoundException"]):
                            is_err = True

                        if is_err:
                            rec = {
                                "step_index": i,
                                "command": cmd_str[:300],
                                "exit_code": exit_code,
                                "snippet": resp_content[:300]
                            }
                            if is_test_or_build_cmd(cmd_str):
                                test_build_failures.append(rec)
                            else:
                                shell_failures.append(rec)
                    else:
                        # Non-command tool error detection
                        is_tool_err = (
                            resp_status == "ERROR"
                            or resp_content.startswith("Error:")
                            or "error applying edit" in resp_content.lower()
                            or "target not found" in resp_content.lower()
                            or "could not find matching" in resp_content.lower()
                            or "file already exists" in resp_content.lower()
                        )
                        if is_tool_err:
                            non_cmd_tool_failures.append({
                                "step_index": i,
                                "tool": tname,
                                "snippet": resp_content[:250]
                            })

        # Match repository
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

        repo_display = Path(candidate_repos[matched_repo_norm]).name if matched_repo_norm else "General/Unscoped"
        if target_repo and target_repo.lower() not in repo_display.lower():
            continue
        if exclude_repo and any(ex.lower() in repo_display.lower() for ex in exclude_repo if ex):
            continue

        total_billed_context = (hw_input_tokens + hw_cache_tokens + hw_output_tokens) if has_hw_tokens else fallback_char_tokens
        turns_per_prompt = round(model_turns / user_turns, 2) if user_turns > 0 else float(model_turns)

        conversations.append({
            "id": item.name,
            "mtime": mtime,
            "dt": conv_dt,
            "date": conv_dt.strftime("%Y-%m-%d %H:%M"),
            "repo": repo_display,
            "first_prompt": first_prompt,
            "user_turns": user_turns,
            "model_turns": model_turns,
            "turns_per_prompt": turns_per_prompt,
            "has_hw_tokens": has_hw_tokens,
            "input_tokens": hw_input_tokens,
            "cache_read_tokens": hw_cache_tokens,
            "output_tokens": hw_output_tokens,
            "peak_context_tokens": peak_context_tokens,
            "total_tokens": total_billed_context,
            "tool_counts": dict(tool_counts),
            "read_search_calls": read_search_calls,
            "edit_write_calls": edit_write_calls,
            "scratch_writes": scratch_writes,
            "scratch_runs": scratch_runs,
            "inline_script_runs": inline_script_runs,
            "shell_failures": shell_failures,
            "test_build_failures": test_build_failures,
            "non_cmd_tool_failures": non_cmd_tool_failures,
        })

    return conversations, total_candidates


def summarize_cohort(convs):
    n = len(convs)
    user_turns = sum(c["user_turns"] for c in convs)
    model_turns = sum(c["model_turns"] for c in convs)
    cmd_calls = sum(c["tool_counts"].get("run_command", 0) for c in convs)
    shell_Errs = sum(len(c["shell_failures"]) for c in convs)
    test_Errs = sum(len(c["test_build_failures"]) for c in convs)
    tool_Errs = sum(len(c["non_cmd_tool_failures"]) for c in convs)
    scratch_writes = sum(c["scratch_writes"] for c in convs)
    scratch_runs = sum(c["scratch_runs"] for c in convs)
    inline_runs = sum(c["inline_script_runs"] for c in convs)

    in_tok = sum(c["input_tokens"] for c in convs)
    cache_tok = sum(c["cache_read_tokens"] for c in convs)
    out_tok = sum(c["output_tokens"] for c in convs)
    tot_tok = sum(c["total_tokens"] for c in convs)

    overall_tools = Counter()
    repo_counts = Counter()
    for c in convs:
        repo_counts[c["repo"]] += 1
        for k, v in c["tool_counts"].items():
            overall_tools[k] += v

    top_cost = sorted(convs, key=lambda c: c["total_tokens"], reverse=True)[:10]
    top_thrash = sorted(
        [c for c in convs if c["model_turns"] >= 6],
        key=lambda c: (c["turns_per_prompt"], c["read_search_calls"] - c["edit_write_calls"]),
        reverse=True
    )[:10]

    recent_errors = []
    for c in convs:
        if c["shell_failures"] or c["non_cmd_tool_failures"]:
            recent_errors.append({
                "id": c["id"],
                "date": c["date"],
                "repo": c["repo"],
                "first_prompt": c["first_prompt"][:100],
                "shell_failures": c["shell_failures"][:5],
                "non_cmd_tool_failures": c["non_cmd_tool_failures"][:5],
                "test_build_failures_count": len(c["test_build_failures"])
            })

    def slim_conv(c):
        return {
            "id": c["id"],
            "date": c["date"],
            "repo": c["repo"],
            "first_prompt": c["first_prompt"][:110],
            "user_turns": c["user_turns"],
            "model_turns": c["model_turns"],
            "turns_per_prompt": c["turns_per_prompt"],
            "input_tokens": c["input_tokens"],
            "cache_read_tokens": c["cache_read_tokens"],
            "output_tokens": c["output_tokens"],
            "peak_context_tokens": c["peak_context_tokens"],
            "total_tokens": c["total_tokens"],
            "read_search_calls": c["read_search_calls"],
            "edit_write_calls": c["edit_write_calls"],
            "scratch_writes": c["scratch_writes"],
            "shell_failures_count": len(c["shell_failures"]),
            "non_cmd_failures_count": len(c["non_cmd_tool_failures"]),
            "test_build_failures_count": len(c["test_build_failures"]),
        }

    return {
        "conversations": n,
        "user_turns": user_turns,
        "model_turns": model_turns,
        "avg_model_turns_per_prompt": round(model_turns / user_turns, 2) if user_turns else 0.0,
        "run_command_calls": cmd_calls,
        "shell_failures": shell_Errs,
        "shell_failure_rate_pct": round(shell_Errs / cmd_calls * 100, 2) if cmd_calls else 0.0,
        "test_build_failures": test_Errs,
        "non_cmd_tool_failures": tool_Errs,
        "scratch_writes": scratch_writes,
        "scratch_runs": scratch_runs,
        "inline_script_runs": inline_runs,
        "input_tokens": in_tok,
        "cache_read_tokens": cache_tok,
        "output_tokens": out_tok,
        "total_tokens": tot_tok,
        "cache_hit_pct": round(cache_tok / (in_tok + cache_tok) * 100, 1) if (in_tok + cache_tok) else 0.0,
        "avg_tokens_per_conv": round(tot_tok / n) if n else 0,
        "avg_tokens_per_user_turn": round(tot_tok / user_turns) if user_turns else 0,
        "tool_distribution": dict(overall_tools.most_common(15)),
        "repo_distribution": dict(repo_counts.most_common(15)),
        "top_cost_sessions": [slim_conv(c) for c in top_cost],
        "top_thrash_sessions": [slim_conv(c) for c in top_thrash],
        "recent_error_sessions": recent_errors[:15],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neutral Trajectory Telemetry Indexer")
    parser.add_argument("output_dir", nargs="?", default=None, help="Optional output directory (defaults to system temp)")
    parser.add_argument("--limit", type=int, default=100, help="Max conversations to index (default 100)")
    parser.add_argument("--all", action="store_true", help="Index all conversations")
    parser.add_argument("--since", type=str, default=None, help="Filter conversations since YYYY-MM-DD")
    parser.add_argument("--repo", type=str, default=None, help="Filter by repository substring")
    parser.add_argument("--exclude", type=str, default=None, help="Comma-separated repositories to exclude")
    parser.add_argument("--compare", action="store_true", help="Compare cohort since date against prior baseline")
    args = parser.parse_args()

    base_dir = locate_antigravity_dir()
    brain_dirs = locate_brain_directories(base_dir)
    candidate_repos = discover_candidate_repos(base_dir)

    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except Exception:
            try:
                since_dt = datetime.strptime(args.since, "%Y-%m-%d")
            except Exception:
                pass
    if args.compare and not since_dt:
        since_dt = datetime.now() - timedelta(hours=24)

    exclude_list = [e.strip() for e in args.exclude.split(",") if e.strip()] if args.exclude else []
    conv_limit = None if args.all else args.limit

    convs, total_candidates = parse_conversations(
        brain_dirs=brain_dirs,
        candidate_repos=candidate_repos,
        max_conversations=conv_limit,
        since_dt=since_dt,
        target_repo=args.repo,
        exclude_repo=exclude_list,
        compare_mode=args.compare,
    )

    out_dir = Path(args.output_dir) if args.output_dir else (Path(tempfile.gettempdir()) / "agy_telemetry")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "telemetry_summary.json"

    if args.compare and since_dt:
        target_c = [c for c in convs if c["dt"] >= since_dt]
        base_c = [c for c in convs if c["dt"] < since_dt]
        t_sum = summarize_cohort(target_c)
        b_sum = summarize_cohort(base_c)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "mode": "compare",
            "since": since_dt.isoformat(),
            "target": t_sum,
            "baseline": b_sum,
        }
        print(f"=== Telemetry Comparison (Since {since_dt.strftime('%Y-%m-%d %H:%M')}) ===")
        print(f"Target Sessions: {t_sum['conversations']} | Baseline Sessions: {b_sum['conversations']}")
        print(f"Model Turns / User Prompt: {b_sum['avg_model_turns_per_prompt']} -> {t_sum['avg_model_turns_per_prompt']}")
        print(f"Shell Failure Rate: {b_sum['shell_failure_rate_pct']}% -> {t_sum['shell_failure_rate_pct']}%")
        print(f"Non-Command Tool Failures: {b_sum['non_cmd_tool_failures']} -> {t_sum['non_cmd_tool_failures']}")
        print(f"Scratch Writes / Runs: {b_sum['scratch_writes']}/{b_sum['scratch_runs']} -> {t_sum['scratch_writes']}/{t_sum['scratch_runs']}")
    else:
        summary = summarize_cohort(convs)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "mode": "standard",
            "total_candidates": total_candidates,
            **summary,
        }
        print("=== Antigravity Session Telemetry ===")
        print(f"Indexed Conversations:      {summary['conversations']} (of {total_candidates})")
        print(f"User Prompts / Model Turns: {summary['user_turns']} / {summary['model_turns']} ({summary['avg_model_turns_per_prompt']} turns/prompt)")
        print(f"Hardware Tokens (In/Cache/Out): {summary['input_tokens']:,} / {summary['cache_read_tokens']:,} / {summary['output_tokens']:,} (Cache Hit: {summary['cache_hit_pct']}%)")
        print(f"Command Calls:              {summary['run_command_calls']} (Shell Errors: {summary['shell_failures']} [{summary['shell_failure_rate_pct']}%], Test/Build Fails: {summary['test_build_failures']})")
        print(f"Non-Command Tool Errors:    {summary['non_cmd_tool_failures']}")
        print(f"Scratch Writes / Runs:      {summary['scratch_writes']} writes / {summary['scratch_runs']} runs (Inline -c/-e runs: {summary['inline_script_runs']})")
        print("\nTop Repositories:")
        for r, cnt in list(summary["repo_distribution"].items())[:8]:
            print(f"  - {r}: {cnt} sessions")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nTelemetry written to: {out_file}")


if __name__ == "__main__":
    main()

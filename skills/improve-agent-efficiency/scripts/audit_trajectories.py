#!/usr/bin/env python3
"""
Neutral Trajectory Telemetry Indexer for Antigravity (v2).
Indexes hardware token usage (input, cache_read, output), model inference turns,
parent-child subagent DAG trees, functional cost-center domain breakdowns,
two-turn scratch script loops (write_file -> run_command), async command
backgrounding and manage_task polling waste, truncated step output reads,
and tool errors without polluting working directories.
"""

import os
import sys
import json
import re
import platform
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

UUID_RE = re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", re.I)


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


def extract_clean_prompt(content):
    if not content:
        return ""
    p_clean = content.strip().replace("\r", " ").replace("\n", " ")
    if "<USER_REQUEST>" in p_clean:
        start = p_clean.find("<USER_REQUEST>") + len("<USER_REQUEST>")
        end = p_clean.find("</USER_REQUEST>")
        p_clean = p_clean[start:end].strip() if end != -1 else p_clean[start:].strip()
    return p_clean


def classify_tool_domain(tname, args):
    args = args if isinstance(args, dict) else {}
    cmd_low = clean_str(args.get("CommandLine") or "").lower() if tname == "run_command" else ""
    path_low = clean_str(args.get("Path") or args.get("TargetFile") or args.get("path") or "").lower()
    args_low = json.dumps(args).lower()

    if tname in ("manage_task", "schedule"):
        return "async_task_polling"
    if tname in ("invoke_subagent", "manage_subagents", "send_message"):
        return "subagent_orchestration"
    if tname in ("search_web", "webview_browser"):
        return "web_scouting_search_and_probe"
    if tname == "call_mcp_tool" or "gmail" in cmd_low or "calendar" in cmd_low or "gmail" in args_low:
        return "gmail_and_calendar_ops"
    if tname == "run_command":
        if re.search(r'(^|[|;&\s"\'\\])kan(\.exe)?\b', cmd_low) or "sync_tracking" in cmd_low or "applications.json" in cmd_low:
            return "tracking_and_kanban_ops"
        if any(k in cmd_low for k in ["scout", "probe", "verify_url", "check_url", "curl", "invoke-webrequest"]):
            return "web_scouting_search_and_probe"
        if "9222" in cmd_low or "cdp" in cmd_low or "workday_cdp" in cmd_low or "oracle_cdp" in cmd_low or "scratch" in cmd_low:
            return "cdp_browser_exec"
        return "general_shell"
    if tname in ("read_file", "view_file", "grep_search", "find_by_name", "list_dir", "view_file_outline", "view_code_item"):
        if ".system_generated" in path_low or "scratch" in path_low:
            return "scratch_and_truncated_log_reads"
        if any(k in path_low for k in ["applications.json", "sync_tracking", ".kan", "boards"]):
            return "tracking_and_kanban_ops"
        return "orientation_and_code_reads"
    if tname in ("edit_file", "write_file", "replace_file_content", "write_to_file", "multi_replace_file_content"):
        if "scratch" in path_low:
            return "cdp_scratch_script_write"
        if any(k in path_low for k in ["applications.json", "sync_tracking", ".kan"]):
            return "tracking_and_kanban_ops"
        return "file_edits_and_staging"
    return "other"


def parse_conversations(brain_dirs, candidate_repos, max_conversations=100, since_dt=None, target_repo=None, exclude_repo=None, compare_mode=False):
    sorted_repo_norms = sorted(list(candidate_repos.keys()), key=len, reverse=True)
    conv_candidates = []
    seen_ids = set()

    for brain_dir in brain_dirs:
        if not brain_dir or not brain_dir.exists():
            continue
        for item in brain_dir.iterdir():
            cid = item.name.lower()
            if not item.is_dir() or item.name == "tempmediaStorage" or cid in seen_ids:
                continue
            tpath = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not tpath.exists():
                continue
            seen_ids.add(cid)
            try:
                mtime = os.path.getmtime(tpath)
                conv_dt = datetime.fromtimestamp(mtime)
                if since_dt and not compare_mode and conv_dt < since_dt:
                    continue
                conv_candidates.append((mtime, cid, tpath, conv_dt))
            except Exception:
                pass

    conv_candidates.sort(key=lambda x: x[0], reverse=True)
    total_candidates = len(conv_candidates)
    if max_conversations and max_conversations > 0:
        conv_candidates = conv_candidates[:max_conversations]

    raw_conversations = {}
    parent_to_children = defaultdict(list)
    child_to_parent = {}
    non_tool_types = {"USER_INPUT", "PLANNER_RESPONSE", "CONVERSATION_HISTORY", "KNOWLEDGE_ARTIFACTS", "CHECKPOINT", "SYSTEM_MESSAGE"}

    for mtime, cid, tpath, conv_dt in conv_candidates:
        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                steps = [json.loads(line) for line in f if line.strip()]
        except Exception:
            continue

        first_prompt = ""
        fallback_init_prompt = ""
        user_prompts = []
        active_ws = ""
        touched_paths = set()

        user_turns = 0
        model_turns = 0
        hw_input_tokens = 0
        hw_cache_tokens = 0
        hw_output_tokens = 0
        first_context_tokens = 0
        peak_context_tokens = 0
        has_hw_tokens = False
        fallback_char_tokens = 0

        tool_counts = Counter()
        domain_tokens = Counter()
        domain_turns = Counter()
        read_search_calls = 0
        edit_write_calls = 0
        scratch_writes = 0
        scratch_runs = 0
        inline_script_runs = 0

        # New v2 waste and micro-loop counters
        write_then_run_pairs = 0
        prev_turn_had_scratch_write = False
        backgrounded_commands = 0
        manage_task_polls = 0
        async_polling_tokens = 0
        wait_ms_le_5000 = 0
        wait_ms_gt_5000 = 0
        truncated_tool_outputs = 0
        step_output_file_reads = 0
        scratch_file_reads = 0
        write_file_collisions = 0

        shell_failures = []
        test_build_failures = []
        non_cmd_tool_failures = []

        for i, step in enumerate(steps):
            st = step.get("type", "")
            source = step.get("source", "")
            content = step.get("content", "") or ""
            thinking = step.get("thinking", "") or ""
            fallback_char_tokens += round((len(content) + len(thinking)) / 4)

            if i <= 3 and not fallback_init_prompt and content and st not in ("CONVERSATION_HISTORY", "KNOWLEDGE_ARTIFACTS", "CHECKPOINT"):
                p_init = extract_clean_prompt(content)
                if p_init:
                    fallback_init_prompt = p_init[:200]

            if st not in non_tool_types and "output was truncated due to being too long" in content:
                truncated_tool_outputs += 1

            if st == "USER_INPUT" or source == "USER_EXPLICIT":
                user_turns += 1
                p_clean = extract_clean_prompt(content)
                if not first_prompt and p_clean:
                    first_prompt = p_clean[:200]
                if p_clean:
                    user_prompts.append(p_clean[:120])

                if "<user_information>" in content:
                    for line in content.split("\n"):
                        if "active workspace is" in line.lower() or "command working directory:" in line.lower():
                            cand = line.split(":")[-1].strip().rstrip(".") if ":" in line else line.split("active workspace is")[-1].strip().rstrip(".")
                            if cand:
                                active_ws = norm_path(cand)

            elif st == "PLANNER_RESPONSE" or source == "MODEL":
                turn_tok = 0
                if st == "PLANNER_RESPONSE":
                    model_turns += 1
                    in_tok = step.get("input_tokens") or 0
                    cache_tok = step.get("cache_read_tokens") or 0
                    out_tok = step.get("output_tokens") or 0
                    turn_tok = in_tok + cache_tok + out_tok
                    if in_tok or cache_tok or out_tok:
                        has_hw_tokens = True
                        hw_input_tokens += in_tok
                        hw_cache_tokens += cache_tok
                        hw_output_tokens += out_tok
                        ctx = in_tok + cache_tok
                        if ctx > 0 and first_context_tokens == 0:
                            first_context_tokens = ctx
                        if ctx > peak_context_tokens:
                            peak_context_tokens = ctx

                tc_list = step.get("tool_calls", [])
                cur_turn_has_scratch_write = False
                cur_turn_has_scratch_run = False
                cur_turn_has_poll = False
                turn_domains = set()

                if not tc_list and st == "PLANNER_RESPONSE":
                    domain_tokens["final_or_text_response"] += turn_tok
                    domain_turns["final_or_text_response"] += 1

                share_tok = round(turn_tok / len(tc_list)) if tc_list else 0

                for tc_idx, tc in enumerate(tc_list):
                    tname = tc.get("name") or "unknown"
                    tool_counts[tname] += 1
                    args = tc.get("args") or tc.get("arguments") or {}
                    if not isinstance(args, dict):
                        args = {}

                    dom = classify_tool_domain(tname, args)
                    domain_tokens[dom] += share_tok
                    turn_domains.add(dom)

                    for k in ["Cwd", "TargetFile", "AbsolutePath", "Path", "path", "SearchPath", "DirectoryPath"]:
                        v = args.get(k)
                        if v and isinstance(v, str):
                            cv = clean_str(v)
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

                    resp_step = None
                    resp_idx = i + 1 + tc_idx
                    if resp_idx < len(steps) and steps[resp_idx].get("type") not in non_tool_types:
                        resp_step = steps[resp_idx]
                    else:
                        for j in range(i + 1, min(i + 10, len(steps))):
                            if steps[j].get("type") not in non_tool_types:
                                resp_step = steps[j]
                                break

                    resp_content = (resp_step.get("content", "") if resp_step else "") or ""
                    resp_status = (resp_step.get("status", "") if resp_step else "") or ""

                    # Parent-child subagent link extraction
                    if tname == "invoke_subagent":
                        role = clean_str(args.get("Role") or "")
                        sub_type = clean_str(args.get("TypeName") or "")
                        sub_prompt = clean_str(args.get("Prompt") or "").replace("\r", " ").replace("\n", " ")[:200]
                        sub_cid = None
                        if resp_content:
                            for m in UUID_RE.finditer(resp_content):
                                cand = m.group(1).lower()
                                if cand != cid and cand not in parent_to_children[cid]:
                                    sub_cid = cand
                                    break
                        if not sub_cid:
                            for j in range(i + 1, min(i + 15, len(steps))):
                                if steps[j].get("type") == "PLANNER_RESPONSE":
                                    break
                                rc = steps[j].get("content", "") or ""
                                for m in UUID_RE.finditer(rc):
                                    cand = m.group(1).lower()
                                    if cand != cid and cand not in parent_to_children[cid]:
                                        sub_cid = cand
                                        break
                                if sub_cid:
                                    break
                        if sub_cid:
                            parent_to_children[cid].append(sub_cid)
                            child_to_parent[sub_cid] = {
                                "parent_id": cid,
                                "role": role,
                                "type": sub_type,
                                "prompt": sub_prompt
                            }

                    if tname in ("manage_task", "schedule"):
                        manage_task_polls += 1
                        cur_turn_has_poll = True

                    if tname in ["read_file", "view_file", "grep_search", "find_by_name", "list_dir", "view_file_outline", "view_code_item"]:
                        read_search_calls += 1
                        target_p = clean_str(args.get("Path") or args.get("TargetFile") or args.get("path")).lower()
                        if ".system_generated" in target_p and "output.txt" in target_p:
                            step_output_file_reads += 1
                        elif "scratch" in target_p:
                            scratch_file_reads += 1
                    elif tname in ["edit_file", "write_file", "replace_file_content", "write_to_file", "multi_replace_file_content"]:
                        target_p = clean_str(args.get("Path") or args.get("TargetFile") or args.get("path"))
                        if "scratch" in target_p.lower():
                            scratch_writes += 1
                            cur_turn_has_scratch_write = True
                        else:
                            edit_write_calls += 1

                    if tname == "run_command":
                        cmd_str = clean_str(args.get("CommandLine"))
                        cmd_lower = cmd_str.lower()
                        w_ms = args.get("WaitMsBeforeAsync")
                        if isinstance(w_ms, (int, float)):
                            if w_ms <= 5000:
                                wait_ms_le_5000 += 1
                            else:
                                wait_ms_gt_5000 += 1

                        if "scratch" in cmd_lower:
                            scratch_runs += 1
                            cur_turn_has_scratch_run = True
                        if any(p in cmd_lower for p in ["py -c", "python -c", "node -e", "pwsh -c", "powershell -c"]):
                            inline_script_runs += 1
                        if re.search(r'(^|[|;&\s])(rg|Get-ChildItem|Select-String|git\s+(status|diff|log|show))\b', cmd_str, re.I):
                            read_search_calls += 1
                        if "tool is running as a background task" in resp_content.lower():
                            backgrounded_commands += 1

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
                        if "already exists" in resp_content.lower():
                            write_file_collisions += 1
                        is_tool_err = (
                            resp_status == "ERROR"
                            or resp_content.startswith("Error:")
                            or "error applying edit" in resp_content.lower()
                            or "target not found" in resp_content.lower()
                            or "could not find matching" in resp_content.lower()
                            or "file already exists" in resp_content.lower()
                            or "already exists" in resp_content.lower()
                        )
                        if is_tool_err:
                            non_cmd_tool_failures.append({
                                "step_index": i,
                                "tool": tname,
                                "snippet": resp_content[:250]
                            })

                for d in turn_domains:
                    domain_turns[d] += 1
                if cur_turn_has_poll:
                    async_polling_tokens += turn_tok
                if st == "PLANNER_RESPONSE":
                    if prev_turn_had_scratch_write and cur_turn_has_scratch_run:
                        write_then_run_pairs += 1
                    prev_turn_had_scratch_write = cur_turn_has_scratch_write

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
            low_prompts = " ".join(user_prompts + ([fallback_init_prompt] if fallback_init_prompt else [])).lower()
            for rn in sorted_repo_norms:
                rname = Path(candidate_repos[rn]).name.lower()
                if len(rname) >= 4 and rname in low_prompts:
                    matched_repo_norm = rn
                    break

        repo_display = Path(candidate_repos[matched_repo_norm]).name if matched_repo_norm else "General/Unscoped"
        total_billed_context = (hw_input_tokens + hw_cache_tokens + hw_output_tokens) if has_hw_tokens else fallback_char_tokens

        raw_conversations[cid] = {
            "id": cid,
            "mtime": mtime,
            "dt": conv_dt,
            "date": conv_dt.strftime("%Y-%m-%d %H:%M"),
            "repo": repo_display,
            "first_prompt": first_prompt or fallback_init_prompt,
            "user_turns": user_turns,
            "model_turns": model_turns,
            "has_hw_tokens": has_hw_tokens,
            "input_tokens": hw_input_tokens,
            "cache_read_tokens": hw_cache_tokens,
            "output_tokens": hw_output_tokens,
            "first_context_tokens": first_context_tokens,
            "peak_context_tokens": peak_context_tokens,
            "total_tokens": total_billed_context,
            "tool_counts": dict(tool_counts),
            "domain_tokens": dict(domain_tokens),
            "domain_turns": dict(domain_turns),
            "read_search_calls": read_search_calls,
            "edit_write_calls": edit_write_calls,
            "scratch_writes": scratch_writes,
            "scratch_runs": scratch_runs,
            "write_then_run_pairs": write_then_run_pairs,
            "inline_script_runs": inline_script_runs,
            "backgrounded_commands": backgrounded_commands,
            "manage_task_polls": manage_task_polls,
            "async_polling_tokens": async_polling_tokens,
            "wait_ms_le_5000": wait_ms_le_5000,
            "wait_ms_gt_5000": wait_ms_gt_5000,
            "truncated_tool_outputs": truncated_tool_outputs,
            "step_output_file_reads": step_output_file_reads,
            "scratch_file_reads": scratch_file_reads,
            "write_file_collisions": write_file_collisions,
            "shell_failures": shell_failures,
            "test_build_failures": test_build_failures,
            "non_cmd_tool_failures": non_cmd_tool_failures,
        }

    # Second pass: enrich with parent-child subagent links and roll up tree metrics
    conversations = []
    for cid, c in raw_conversations.items():
        p_meta = child_to_parent.get(cid)
        is_subagent = bool(p_meta or c["user_turns"] == 0)
        parent_id = p_meta["parent_id"] if p_meta else None
        subagent_role = p_meta["role"] if p_meta else ""
        if p_meta and not c["first_prompt"] and p_meta.get("prompt"):
            c["first_prompt"] = f"[{subagent_role}] {p_meta['prompt']}"
        elif subagent_role and not c["first_prompt"].startswith(f"[{subagent_role}]"):
            c["first_prompt"] = f"[{subagent_role}] {c['first_prompt']}"

        # Inherit parent repo if subagent repo was unscoped
        if c["repo"] == "General/Unscoped" and parent_id and parent_id in raw_conversations:
            c["repo"] = raw_conversations[parent_id]["repo"]

        effective_prompts = c["user_turns"] if c["user_turns"] > 0 else 1
        c["turns_per_prompt"] = round(c["model_turns"] / effective_prompts, 2)
        c["is_subagent"] = is_subagent
        c["parent_id"] = parent_id
        c["subagent_role"] = subagent_role

        kids = parent_to_children.get(cid, [])
        c["child_ids"] = kids
        c["child_count"] = len(kids)
        kid_tokens = sum(raw_conversations[k]["total_tokens"] for k in kids if k in raw_conversations)
        kid_turns = sum(raw_conversations[k]["model_turns"] for k in kids if k in raw_conversations)
        kid_polls = sum(raw_conversations[k]["manage_task_polls"] for k in kids if k in raw_conversations)
        kid_wtr = sum(raw_conversations[k]["write_then_run_pairs"] for k in kids if k in raw_conversations)
        c["children_tokens"] = kid_tokens
        c["children_model_turns"] = kid_turns
        c["tree_total_tokens"] = c["total_tokens"] + kid_tokens
        c["tree_model_turns"] = c["model_turns"] + kid_turns
        c["tree_manage_task_polls"] = c["manage_task_polls"] + kid_polls
        c["tree_write_then_run_pairs"] = c["write_then_run_pairs"] + kid_wtr

        if target_repo and target_repo.lower() not in c["repo"].lower():
            continue
        if exclude_repo and any(ex.lower() in c["repo"].lower() for ex in exclude_repo if ex):
            continue
        conversations.append(c)

    conversations.sort(key=lambda x: x["mtime"], reverse=True)
    return conversations, total_candidates


def summarize_cohort(convs):
    n = len(convs)
    root_convs = [c for c in convs if not c["is_subagent"]]
    sub_convs = [c for c in convs if c["is_subagent"]]

    user_turns = sum(c["user_turns"] for c in convs)
    model_turns = sum(c["model_turns"] for c in convs)
    cmd_calls = sum(c["tool_counts"].get("run_command", 0) for c in convs)
    shell_errs = sum(len(c["shell_failures"]) for c in convs)
    test_errs = sum(len(c["test_build_failures"]) for c in convs)
    tool_errs = sum(len(c["non_cmd_tool_failures"]) for c in convs)
    scratch_writes = sum(c["scratch_writes"] for c in convs)
    scratch_runs = sum(c["scratch_runs"] for c in convs)
    write_then_run = sum(c["write_then_run_pairs"] for c in convs)
    inline_runs = sum(c["inline_script_runs"] for c in convs)
    bg_cmds = sum(c["backgrounded_commands"] for c in convs)
    polls = sum(c["manage_task_polls"] for c in convs)
    poll_toks = sum(c["async_polling_tokens"] for c in convs)
    trunc_outs = sum(c["truncated_tool_outputs"] for c in convs)
    step_out_reads = sum(c["step_output_file_reads"] for c in convs)
    scratch_reads = sum(c["scratch_file_reads"] for c in convs)
    write_collisions = sum(c["write_file_collisions"] for c in convs)

    in_tok = sum(c["input_tokens"] for c in convs)
    cache_tok = sum(c["cache_read_tokens"] for c in convs)
    out_tok = sum(c["output_tokens"] for c in convs)
    tot_tok = sum(c["total_tokens"] for c in convs)

    overall_tools = Counter()
    overall_domains = Counter()
    repo_counts = Counter()
    for c in convs:
        repo_counts[c["repo"]] += 1
        for k, v in c["tool_counts"].items():
            overall_tools[k] += v
        for k, v in c["domain_tokens"].items():
            overall_domains[k] += v

    top_trees = sorted(root_convs, key=lambda c: c["tree_total_tokens"], reverse=True)[:10]
    top_cost = sorted(convs, key=lambda c: c["total_tokens"], reverse=True)[:10]
    top_thrash_roots = sorted(
        [c for c in root_convs if c["model_turns"] >= 6],
        key=lambda c: (c["turns_per_prompt"], c["read_search_calls"] - c["edit_write_calls"]),
        reverse=True
    )[:10]
    top_subagents = sorted(sub_convs, key=lambda c: c["total_tokens"], reverse=True)[:10]

    recent_errors = []
    for c in convs:
        if c["shell_failures"] or c["non_cmd_tool_failures"]:
            recent_errors.append({
                "id": c["id"],
                "date": c["date"],
                "repo": c["repo"],
                "is_subagent": c["is_subagent"],
                "parent_id": c["parent_id"],
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
            "is_subagent": c["is_subagent"],
            "parent_id": c["parent_id"],
            "child_count": c["child_count"],
            "first_prompt": c["first_prompt"][:110],
            "user_turns": c["user_turns"],
            "model_turns": c["model_turns"],
            "tree_model_turns": c["tree_model_turns"],
            "turns_per_prompt": c["turns_per_prompt"],
            "input_tokens": c["input_tokens"],
            "cache_read_tokens": c["cache_read_tokens"],
            "output_tokens": c["output_tokens"],
            "peak_context_tokens": c["peak_context_tokens"],
            "total_tokens": c["total_tokens"],
            "children_tokens": c["children_tokens"],
            "tree_total_tokens": c["tree_total_tokens"],
            "read_search_calls": c["read_search_calls"],
            "edit_write_calls": c["edit_write_calls"],
            "scratch_writes": c["scratch_writes"],
            "write_then_run_pairs": c["write_then_run_pairs"],
            "tree_write_then_run_pairs": c["tree_write_then_run_pairs"],
            "backgrounded_commands": c["backgrounded_commands"],
            "manage_task_polls": c["manage_task_polls"],
            "tree_manage_task_polls": c["tree_manage_task_polls"],
            "async_polling_tokens": c["async_polling_tokens"],
            "truncated_tool_outputs": c["truncated_tool_outputs"],
            "step_output_file_reads": c["step_output_file_reads"],
            "write_file_collisions": c["write_file_collisions"],
            "shell_failures_count": len(c["shell_failures"]),
            "non_cmd_failures_count": len(c["non_cmd_tool_failures"]),
            "test_build_failures_count": len(c["test_build_failures"]),
        }

    return {
        "conversations": n,
        "root_conversations": len(root_convs),
        "subagent_conversations": len(sub_convs),
        "user_turns": user_turns,
        "model_turns": model_turns,
        "avg_model_turns_per_prompt": round(model_turns / user_turns, 2) if user_turns else 0.0,
        "run_command_calls": cmd_calls,
        "shell_failures": shell_errs,
        "shell_failure_rate_pct": round(shell_errs / cmd_calls * 100, 2) if cmd_calls else 0.0,
        "test_build_failures": test_errs,
        "non_cmd_tool_failures": tool_errs,
        "write_file_collisions": write_collisions,
        "scratch_writes": scratch_writes,
        "scratch_runs": scratch_runs,
        "write_then_run_pairs": write_then_run,
        "inline_script_runs": inline_runs,
        "backgrounded_commands": bg_cmds,
        "manage_task_polls": polls,
        "async_polling_tokens": poll_toks,
        "async_polling_token_share_pct": round(poll_toks / tot_tok * 100, 2) if tot_tok else 0.0,
        "truncated_tool_outputs": trunc_outs,
        "step_output_file_reads": step_out_reads,
        "scratch_file_reads": scratch_reads,
        "input_tokens": in_tok,
        "cache_read_tokens": cache_tok,
        "output_tokens": out_tok,
        "total_tokens": tot_tok,
        "cache_hit_pct": round(cache_tok / (in_tok + cache_tok) * 100, 1) if (in_tok + cache_tok) else 0.0,
        "avg_tokens_per_conv": round(tot_tok / n) if n else 0,
        "avg_tokens_per_model_turn": round(tot_tok / model_turns) if model_turns else 0,
        "avg_tokens_per_user_turn": round(tot_tok / user_turns) if user_turns else 0,
        "domain_token_distribution": dict(overall_domains.most_common(15)),
        "tool_distribution": dict(overall_tools.most_common(15)),
        "repo_distribution": dict(repo_counts.most_common(15)),
        "top_cost_trees": [slim_conv(c) for c in top_trees],
        "top_cost_sessions": [slim_conv(c) for c in top_cost],
        "top_thrash_sessions": [slim_conv(c) for c in top_thrash_roots],
        "top_subagent_sessions": [slim_conv(c) for c in top_subagents],
        "recent_error_sessions": recent_errors[:15],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Neutral Trajectory Telemetry Indexer (v2)")
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
        print(f"Target Sessions: {t_sum['conversations']} (Roots: {t_sum['root_conversations']}, Subagents: {t_sum['subagent_conversations']})")
        print(f"Baseline Sessions: {b_sum['conversations']} (Roots: {b_sum['root_conversations']}, Subagents: {b_sum['subagent_conversations']})")
        print(f"Model Turns / User Prompt: {b_sum['avg_model_turns_per_prompt']} -> {t_sum['avg_model_turns_per_prompt']}")
        print(f"Avg Tokens / Model Turn: {b_sum['avg_tokens_per_model_turn']:,} -> {t_sum['avg_tokens_per_model_turn']:,}")
        print(f"Async Polling Share: {b_sum['async_polling_token_share_pct']}% -> {t_sum['async_polling_token_share_pct']}%")
        print(f"Scratch Write->Run Pairs: {b_sum['write_then_run_pairs']} -> {t_sum['write_then_run_pairs']}")
    else:
        summary = summarize_cohort(convs)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "mode": "standard",
            "total_candidates": total_candidates,
            **summary,
        }
        print("=== Antigravity Session Telemetry (v2) ===")
        print(f"Indexed Conversations:      {summary['conversations']} (of {total_candidates}) [Roots: {summary['root_conversations']} | Subagents: {summary['subagent_conversations']}]")
        print(f"User Prompts / Model Turns: {summary['user_turns']} / {summary['model_turns']} ({summary['avg_model_turns_per_prompt']} turns/prompt, {summary['avg_tokens_per_model_turn']:,} tok/turn)")
        print(f"Hardware Tokens (In/Cache/Out): {summary['input_tokens']:,} / {summary['cache_read_tokens']:,} / {summary['output_tokens']:,} (Cache Hit: {summary['cache_hit_pct']}%)")
        print(f"Command Calls:              {summary['run_command_calls']} (Shell Errors: {summary['shell_failures']} [{summary['shell_failure_rate_pct']}%], Test/Build Fails: {summary['test_build_failures']})")
        print(f"Non-Command Tool Errors:    {summary['non_cmd_tool_failures']} (Write File Collisions: {summary['write_file_collisions']})")
        print(f"Scratch Writes / Runs:      {summary['scratch_writes']} writes / {summary['scratch_runs']} runs (Write->Run 2-Turn Pairs: {summary['write_then_run_pairs']}, Inline -c/-e: {summary['inline_script_runs']})")
        print(f"Async Background / Polls:   {summary['backgrounded_commands']} bg cmds -> {summary['manage_task_polls']} manage_task/schedule polls ({summary['async_polling_tokens']:,} tok [{summary['async_polling_token_share_pct']}%])")
        print(f"Truncation & Scratch Reads: {summary['truncated_tool_outputs']} truncated outputs -> {summary['step_output_file_reads']} step output.txt reads, {summary['scratch_file_reads']} scratch file reads")
        print("\nTop Cost-Center Domains:")
        for dom, dtok in list(summary["domain_token_distribution"].items())[:8]:
            pct = round(dtok / summary["total_tokens"] * 100, 1) if summary["total_tokens"] else 0.0
            print(f"  - {dom:34s}: {dtok:14,d} tok ({pct:4.1f}%)")
        print("\nTop Cost Session Trees (Root + Child Subagents):")
        for tc in summary["top_cost_trees"][:5]:
            print(f"  - {tc['id'][:8]} ({tc['date']}) [{tc['child_count']:2d} sub]: Tree={tc['tree_total_tokens']/1e6:6.1f}M (Direct={tc['total_tokens']/1e6:5.1f}M + Sub={tc['children_tokens']/1e6:5.1f}M) | {tc['first_prompt'][:65]}")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nTelemetry written to: {out_file}")


if __name__ == "__main__":
    main()

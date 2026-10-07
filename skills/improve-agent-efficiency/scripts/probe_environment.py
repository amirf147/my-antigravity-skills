#!/usr/bin/env python3
"""
Host Environment & Tooling Probe.
Cross-platform, zero-dependency diagnostics utility that inspects the live host
environment, verifies binary presence, tests console encoding streams, and detects
discrepancies between global agent rules and actual system capabilities.
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path
from datetime import datetime

# Enforce UTF-8 for console output
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def probe_python_environment():
    """Evaluates Python interpreter, standard stream encoding, and environment flags."""
    stdout_enc = getattr(sys.stdout, "encoding", "unknown")
    default_enc = sys.getdefaultencoding()
    fs_enc = sys.getfilesystemencoding()
    py_io_encoding = os.environ.get("PYTHONIOENCODING", "")

    # Test encoding resilience with Finnish characters and Unicode symbols
    test_str = "Test: ä, ö, å, €, ✓, →"
    encoding_error = None
    try:
        if sys.stdout:
            sys.stdout.buffer.write(test_str.encode(stdout_enc or "utf-8"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
    except Exception as exc:
        encoding_error = str(exc)

    return {
        "version": platform.python_version(),
        "executable": sys.executable,
        "stdout_encoding": stdout_enc,
        "default_encoding": default_enc,
        "filesystem_encoding": fs_enc,
        "env_pythonioencoding": py_io_encoding,
        "stdout_test_passed": encoding_error is None,
        "encoding_error": encoding_error
    }


def probe_binary(name, args=("--version",), timeout=3):
    """Probes executable availability, resolves absolute path, and retrieves version."""
    path_str = shutil.which(name)
    if not path_str:
        return {
            "name": name,
            "installed": False,
            "path": None,
            "version": None
        }

    version_str = None
    try:
        cmd = [path_str] + list(args)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        output = (res.stdout or res.stderr or "").strip().splitlines()
        if output:
            version_str = output[0].strip()
    except Exception:
        pass

    return {
        "name": name,
        "installed": True,
        "path": path_str,
        "version": version_str
    }


def probe_host_binaries():
    """Probes core engineering CLI tools and runtimes across platforms."""
    tools_to_check = [
        ("git", ["--version"]),
        ("gh", ["--version"]),
        ("rg", ["--version"]),
        ("curl", ["--version"]),
        ("dotnet", ["--version"]),
        ("node", ["--version"]),
        ("pnpm", ["--version"]),
        ("npm", ["--version"]),
        ("cargo", ["--version"]),
        ("go", ["version"]),
        ("python", ["--version"])
    ]

    results = {}
    for name, args in tools_to_check:
        results[name] = probe_binary(name, args)

    # Windows specific Python launcher probe
    if platform.system() == "Windows":
        results["py"] = probe_binary("py", ["--version"])

    return results


def probe_global_configuration_discrepancies(binaries):
    """Cross-references active GEMINI.md rules against detected binary presence."""
    discrepancies = []
    gemini_config_path = Path.home() / ".gemini" / "config" / "GEMINI.md"

    if not gemini_config_path.exists():
        return {
            "config_found": False,
            "config_path": str(gemini_config_path),
            "discrepancies": discrepancies
        }

    try:
        content = gemini_config_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return {
            "config_found": True,
            "config_path": str(gemini_config_path),
            "read_error": str(exc),
            "discrepancies": discrepancies
        }

    # Check for 'gh CLI is not installed' false negative
    if "gh cli is not installed" in content.lower():
        if binaries.get("gh", {}).get("installed"):
            discrepancies.append({
                "type": "false_negative",
                "tool": "gh",
                "finding": "Rules declare gh CLI is not installed, but gh.exe is actively present on PATH.",
                "remediation": "Update GEMINI.md to authorize direct gh CLI operations."
            })

    # Check for missing tools that rules require or authorize
    for tool_name in ["rg", "git", "dotnet", "curl", "python"]:
        if f"`{tool_name}`" in content or f" {tool_name} " in content:
            if not binaries.get(tool_name, {}).get("installed"):
                discrepancies.append({
                    "type": "missing_required_binary",
                    "tool": tool_name,
                    "finding": f"Rules reference {tool_name}, but the executable is absent from PATH.",
                    "remediation": f"Install {tool_name} via native package manager."
                })

    return {
        "config_found": True,
        "config_path": str(gemini_config_path),
        "discrepancies": discrepancies
    }


def run_probe(output_dir=None):
    """Executes the host environment probe and writes a structured summary."""
    sys_info = {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "timestamp": datetime.now().isoformat()
    }

    py_info = probe_python_environment()
    binaries = probe_host_binaries()
    config_audit = probe_global_configuration_discrepancies(binaries)

    summary = {
        "system": sys_info,
        "python": py_info,
        "binaries": binaries,
        "configuration_audit": config_audit
    }

    out_path = Path(output_dir) if output_dir else Path.cwd()
    target_file = out_path / "host_environment_probe.json"
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Print human-readable summary
    print("=== Host Environment & Tooling Probe ===")
    print(f"OS: {sys_info['os']} {sys_info['release']} ({sys_info['machine']})")
    print(f"Python: {py_info['version']} (stdout: {py_info['stdout_encoding']}, env: {py_info['env_pythonioencoding'] or 'unset'})")
    print(f"Stdout Test: {'PASSED' if py_info['stdout_test_passed'] else 'FAILED: ' + str(py_info['encoding_error'])}")
    print("\nPlatform Binaries:")
    for b_name, b_data in binaries.items():
        status = "INSTALLED" if b_data.get("installed") else "MISSING"
        ver = f"({b_data.get('version')})" if b_data.get("version") else ""
        print(f"  - {b_name:<10}: {status:<10} {ver}")

    if config_audit["discrepancies"]:
        print("\nRule Discrepancies Detected:")
        for disc in config_audit["discrepancies"]:
            print(f"  - [{disc['type']}] {disc['finding']}")
    else:
        print("\nRule Discrepancies: None detected.")

    print(f"\nProbe report written to: {target_file}")
    return target_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Host Environment & Tooling Probe")
    parser.add_argument("output_dir", nargs="?", default=None, help="Directory to save host_environment_probe.json")
    args = parser.parse_args()
    run_probe(args.output_dir)

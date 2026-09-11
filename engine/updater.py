"""
Update checks and explicitly requested update operations for JaneConverter.
"""

import os
import sys
import subprocess
from typing import Optional, Dict, Any, Callable
import requests
import yt_dlp

REPO_DIR = os.path.realpath(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def _run_git_cmd(args: list, timeout: float = 10.0) -> subprocess.CompletedProcess:
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Windows can mark a repository as "dubious" when setup and the app run
    # under different accounts. Scope the exception to this exact checkout.
    if args and args[0] == "git":
        safe_repo = REPO_DIR.replace("\\", "/")
        args = ["git", "-c", f"safe.directory={safe_repo}", *args[1:]]
    return subprocess.run(
        args,
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        creationflags=no_window
    )

def is_git_repo() -> bool:
    """Checks whether the application is running from a valid Git clone."""
    git_dir = os.path.join(REPO_DIR, ".git")
    if not os.path.exists(git_dir):
        return False
    try:
        res = _run_git_cmd(["git", "rev-parse", "--is-inside-work-tree"], timeout=3.0)
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False

def get_current_repo_commit() -> str:
    """Returns the short commit hash of the local repository."""
    try:
        res = _run_git_cmd(["git", "rev-parse", "--short", "HEAD"], timeout=3.0)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"

def get_upstream_branch() -> str:
    """Returns the configured upstream ref (e.g. 'origin/main'), falling back to 'origin/main'."""
    try:
        res = _run_git_cmd(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], timeout=3.0)
        if res.returncode == 0:
            upstream = res.stdout.strip()
            if upstream and "/" in upstream:
                return upstream
    except Exception:
        pass
    return "origin/main"

def check_for_repo_updates(timeout_seconds: float = 6.0) -> Dict[str, Any]:
    """
    Queries the Git remote to check if newer application commits exist.
    """
    if not is_git_repo():
        return {
            "has_update": False,
            "is_git": False,
            "current_commit": "unknown",
            "latest_commit": "unknown",
            "commits_behind": 0,
            "error": "Not a Git repository"
        }

    upstream = get_upstream_branch()
    current_commit = get_current_repo_commit()
    try:
        fetch_res = _run_git_cmd(["git", "fetch", upstream.split("/")[0], upstream.split("/", 1)[1]], timeout=timeout_seconds)
        if fetch_res.returncode != 0:
            return {
                "has_update": False,
                "is_git": True,
                "current_commit": current_commit,
                "latest_commit": current_commit,
                "commits_behind": 0,
                "error": fetch_res.stderr.strip() or f"Failed to fetch from remote {upstream}"
            }

        head_res = _run_git_cmd(["git", "rev-parse", "HEAD"], timeout=3.0)
        origin_res = _run_git_cmd(["git", "rev-parse", upstream], timeout=3.0)

        if head_res.returncode == 0 and origin_res.returncode == 0:
            head_hash = head_res.stdout.strip()
            origin_hash = origin_res.stdout.strip()
            if head_hash != origin_hash:
                count_res = _run_git_cmd(["git", "rev-list", "--count", f"HEAD..{upstream}"], timeout=3.0)
                behind = int(count_res.stdout.strip()) if count_res.returncode == 0 and count_res.stdout.strip().isdigit() else 1
                short_origin = origin_hash[:7]
                return {
                    "has_update": True,
                    "is_git": True,
                    "current_commit": current_commit,
                    "latest_commit": short_origin,
                    "commits_behind": behind,
                    "error": None
                }
            return {
                "has_update": False,
                "is_git": True,
                "current_commit": current_commit,
                "latest_commit": current_commit,
                "commits_behind": 0,
                "error": None
            }
    except Exception as e:
        return {
            "has_update": False,
            "is_git": True,
            "current_commit": current_commit,
            "latest_commit": current_commit,
            "commits_behind": 0,
            "error": str(e)
        }

    return {
        "has_update": False,
        "is_git": True,
        "current_commit": current_commit,
        "latest_commit": current_commit,
        "commits_behind": 0,
        "error": "Unable to determine repository status"
    }

def apply_repo_update(status_callback: Optional[Callable[[str], None]] = None,
                      allow_live_update: bool = False) -> Dict[str, Any]:
    """
    Pulls latest commits from the configured upstream, installs updated dependencies, and recompiles launcher if needed.
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[RepoUpdate] {msg}")

    if not allow_live_update:
        log("Application updates are staged outside the running process. Use a published release installer to apply them safely.")
        return {"success": False, "error": "Live application updates are disabled"}

    if not is_git_repo():
        log("Cannot auto-patch: not a Git clone.")
        return {"success": False, "error": "Not a Git clone"}

    upstream = get_upstream_branch()
    log(f"Pulling latest application updates from {upstream}...")
    try:
        pull_res = _run_git_cmd(["git", "pull", "--ff-only"] + upstream.split("/", 1), timeout=20.0)
        if pull_res.returncode != 0:
            err_msg = pull_res.stderr.strip() or "git pull failed"
            log(f"Git pull failed: {err_msg}")
            return {"success": False, "error": err_msg}
    except Exception as e:
        log(f"Git pull failed: {e}")
        return {"success": False, "error": str(e)}

    log("Application code updated successfully.")

    req_file = os.path.join(REPO_DIR, "requirements.txt")
    if os.path.exists(req_file):
        log("Verifying and updating Python requirements...")
        try:
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"],
                cwd=REPO_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120.0,
                creationflags=no_window
            )
            if res.returncode == 0:
                log("Python requirements verified.")
            else:
                log(f"Notice: Dependency update failed ({res.stderr.strip() or 'pip returned non-zero code'}).")
        except Exception as e:
            log(f"Notice: Dependency update skipped ({e}).")

    cs_file = os.path.join(REPO_DIR, "Program.cs")
    if os.path.exists(cs_file):
        csc_candidates = [
            r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
            r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
        ]
        csc_exe = next((p for p in csc_candidates if os.path.exists(p)), None)
        if csc_exe:
            icon_arg = f"/win32icon:{os.path.join(REPO_DIR, 'assets', 'icon.ico')}"
            out_arg = f"/out:{os.path.join(REPO_DIR, 'JaneConverter.exe')}"
            target_arg = "/target:winexe"
            try:
                no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                res = subprocess.run(
                    [csc_exe, target_arg, icon_arg, out_arg, "Program.cs"],
                    cwd=REPO_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30.0,
                    creationflags=no_window
                )
                if res.returncode == 0:
                    log("Recompiled native launcher JaneConverter.exe.")
                else:
                    log(f"Notice: Launcher recompile failed ({res.stderr.strip() or 'compiler returned non-zero code'}). Existing launcher left unchanged.")
            except Exception as e:
                log(f"Notice: Launcher recompile skipped ({e}).")

    return {"success": True, "error": None}

def get_current_engine_version() -> str:
    """Returns the currently installed version of yt-dlp."""
    return getattr(yt_dlp.version, "__version__", "unknown")

def check_for_engine_updates(timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """
    Queries PyPI API to check if a newer yt-dlp release is available.
    Fails gracefully if offline or request times out.
    """
    current_ver = get_current_engine_version()
    try:
        resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=timeout_seconds)
        if resp.status_code == 200:
            data = resp.json()
            latest_ver = data.get("info", {}).get("version", current_ver)
            has_update = False
            try:
                from packaging import version
                has_update = version.parse(latest_ver) > version.parse(current_ver)
            except Exception:
                has_update = latest_ver != current_ver

            return {
                "has_update": has_update,
                "current_version": current_ver,
                "latest_version": latest_ver,
                "online": True
            }
    except Exception:
        pass

    return {
        "has_update": False,
        "current_version": current_ver,
        "latest_version": current_ver,
        "online": False
    }

def update_engine(status_callback: Optional[Callable[[str], None]] = None,
                  info: Optional[Dict[str, Any]] = None,
                  allow_install: bool = False) -> bool:
    """
    Upgrades yt-dlp to the latest release via pip in the background, pinned to the
    exact version reported by PyPI. Pass a pre-fetched result from
    check_for_engine_updates() via `info` to avoid a duplicate network check.
    Returns True if successfully updated.
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[AutoUpdate] {msg}")

    if not allow_install:
        log("Extractor engine installation is disabled for read-only update checks.")
        return False

    if info is None:
        log("Checking for real-time extractor engine updates...")
        info = check_for_engine_updates()

    if not info["online"]:
        log(f"Offline or network unreachable. Using installed engine (v{info['current_version']}).")
        return False

    if not info["has_update"]:
        log(f"Extractor engine is already up to date (v{info['current_version']}).")
        return False

    target_version = info["latest_version"]
    try:
        target_major = int(str(target_version).split(".", 1)[0])
    except (TypeError, ValueError):
        log(f"Extractor engine upgrade skipped: unsupported version '{target_version}'.")
        return False
    if target_major >= 2027:
        log(f"Extractor engine upgrade skipped: v{target_version} is outside the tested dependency range.")
        return False
    log(f"New engine release detected: v{target_version}. Upgrading now...")

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [sys.executable, "-m", "pip", "install", f"yt-dlp=={target_version}", "--quiet"]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, timeout=120.0, creationflags=no_window)
        if res.returncode == 0:
            log(f"Engine successfully updated to v{target_version}.")
            return True
        log(f"Engine upgrade failed ({res.stderr.strip() or 'pip returned non-zero code'}).")
        return False
    except Exception as e:
        log(f"Notice: Automatic engine upgrade skipped ({e}).")
        return False

def check_and_apply_all_updates(status_callback: Optional[Callable[[str], None]] = None,
                                auto_apply: bool = False) -> Dict[str, Any]:
    """
    Coordinates checking and applying updates for both the JaneConverter application repository
    and the real-time yt-dlp extractor engine. With auto_apply=False, only reports availability
    without modifying the installation.
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[UpdatePipeline] {msg}")

    log("Starting update verification...")
    repo_updated = False
    engine_updated = False
    engine_info: Optional[Dict[str, Any]] = None
    errors = []

    # 1. Extractor Engine check & update (single network check, reused below)
    log("Checking extractor engine (yt-dlp)...")
    try:
        engine_info = check_for_engine_updates()
        if engine_info.get("has_update") and auto_apply:
            log(f"Updating extractor engine from v{engine_info['current_version']} to v{engine_info['latest_version']}...")
            if update_engine(status_callback=status_callback, info=engine_info, allow_install=True):
                engine_updated = True
        elif engine_info.get("has_update"):
            log(f"Extractor engine update available: v{engine_info['current_version']} -> v{engine_info['latest_version']}.")
        else:
            log(f"Extractor engine is already up to date (v{engine_info.get('current_version')}).")
    except Exception as e:
        errors.append(f"Engine update check failed: {e}")

    # 2. Repo check & update
    log("Checking JaneConverter repository...")
    repo_info = check_for_repo_updates()
    if repo_info.get("has_update") and auto_apply:
        log(f"New repository commits found (current: {repo_info.get('current_commit')} -> latest: {repo_info.get('latest_commit')}).")
        res = apply_repo_update(status_callback=status_callback, allow_live_update=auto_apply)
        if res.get("success"):
            repo_updated = True
        else:
            errors.append(res.get("error", "Repository update failed"))
    elif repo_info.get("has_update"):
        log(f"Repository update available ({repo_info.get('commits_behind')} commits behind, current: {repo_info.get('current_commit')}).")
    else:
        if repo_info.get("error") and repo_info.get("is_git"):
            errors.append(repo_info["error"])
        else:
            log(f"JaneConverter code is already up to date ({repo_info.get('current_commit')}).")

    already_up_to_date = (
        not repo_updated and not engine_updated and len(errors) == 0
        and not repo_info.get("has_update")
        and not (engine_info and engine_info.get("has_update"))
    )

    return {
        "repo_updated": repo_updated,
        "engine_updated": engine_updated,
        "already_up_to_date": already_up_to_date,
        "repo_update_available": repo_info.get("has_update", False),
        "engine_update_available": bool(engine_info and engine_info.get("has_update")),
        "commits_behind": repo_info.get("commits_behind", 0),
        "current_commit": repo_info.get("current_commit", get_current_repo_commit()),
        "current_engine_version": get_current_engine_version(),
        "error": "; ".join(errors) if errors else None,
    }

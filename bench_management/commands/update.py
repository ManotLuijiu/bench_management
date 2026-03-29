"""
bench selective-update

Auto-detects app remotes and branches from git config.
Skip lists and overrides live in ~/.bench_management.json (per-server, never committed).

Usage:
    bench selective-update
    bench selective-update --dry-run
    bench selective-update --skip-build
    bench selective-update --no-migrate
"""

import json
import os
import subprocess
import time

import click

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _ok(msg):
    click.echo(f"  {GREEN}✓{RESET}  {msg}")


def _warn(msg):
    click.echo(f"  {YELLOW}!{RESET}  {msg}")


def _err(msg):
    click.echo(f"  {RED}✗{RESET}  {msg}")


def _info(msg):
    click.echo(f"  {CYAN}→{RESET}  {msg}")


def _header(msg):
    click.echo(f"\n{BOLD}{msg}{RESET}")


# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.expanduser("~/.bench_management.json")
CONFIG_EXAMPLE = {
    "skip": [],
    "force_reset": [],
    "force_pull": [],
}
CONFIG_COMMENT = """
# ~/.bench_management.json  —  per-server overrides (never committed to git)
#
# skip        : apps to skip entirely (expired PAT, broken remote, frozen)
# force_reset : override auto-detection → use git fetch + reset --hard
# force_pull  : override auto-detection → use git pull
#
# Auto-detection rules (when not listed above):
#   app has "upstream" remote  →  reset  (core/upstream app)
#   app has only "origin"      →  pull   (your custom app)
"""


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {"skip": [], "force_reset": [], "force_pull": []}
    try:
        with open(CONFIG_PATH) as f:
            # Strip comment lines before parsing
            lines = [l for l in f if not l.strip().startswith("#")]
            return json.loads("".join(lines))
    except Exception as e:
        _warn(f"Could not read {CONFIG_PATH}: {e} — using defaults")
        return {"skip": [], "force_reset": [], "force_pull": []}


# ── Git helpers ───────────────────────────────────────────────────────────────


def _run(cmd: str, cwd: str, dry_run: bool = False) -> tuple[bool, str]:
    if dry_run:
        _info(f"[dry-run] {cmd}")
        return True, ""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode == 0, result.stdout.strip()


def _git_remotes(app_path: str) -> list[str]:
    ok, out = _run("git remote", app_path)
    return out.splitlines() if ok else []


def _git_branch(app_path: str) -> str:
    ok, out = _run("git rev-parse --abbrev-ref HEAD", app_path)
    return out.strip() if ok else "main"


def _git_head(app_path: str) -> str:
    ok, out = _run("git log --oneline -1", app_path)
    return out.strip() if ok else ""


# ── App discovery ─────────────────────────────────────────────────────────────


def discover_apps(bench_path: str, cfg: dict) -> tuple[dict, dict, dict]:
    """
    Returns (reset_apps, pull_apps, skip_apps).

    Auto-detects from git remotes:
      upstream remote  →  reset (core)
      origin only      →  pull  (custom)

    Config overrides applied after auto-detection.
    """
    apps_dir = os.path.join(bench_path, "apps")
    skip_set = set(cfg.get("skip", []))
    force_reset = set(cfg.get("force_reset", []))
    force_pull = set(cfg.get("force_pull", []))

    reset_apps = {}  # name → (remote, branch)
    pull_apps = {}
    skip_apps = {}

    for app in sorted(os.listdir(apps_dir)):
        app_path = os.path.join(apps_dir, app)
        if not os.path.isdir(os.path.join(app_path, ".git")):
            continue

        # Explicit skip from config
        if app in skip_set:
            skip_apps[app] = "listed in ~/.bench_management.json skip"
            continue

        remotes = _git_remotes(app_path)
        branch = _git_branch(app_path)

        # Explicit overrides from config
        if app in force_reset:
            remote = "upstream" if "upstream" in remotes else (remotes[0] if remotes else "origin")
            reset_apps[app] = (remote, branch)
            continue

        if app in force_pull:
            remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "origin")
            pull_apps[app] = (remote, branch)
            continue

        # Auto-detect
        if "upstream" in remotes:
            reset_apps[app] = ("upstream", branch)
        elif "origin" in remotes:
            pull_apps[app] = ("origin", branch)
        elif remotes:
            pull_apps[app] = (remotes[0], branch)
        else:
            skip_apps[app] = "no git remote configured"

    return reset_apps, pull_apps, skip_apps


# ── Update actions ────────────────────────────────────────────────────────────


def reset_app(bench_path: str, app: str, remote: str, branch: str, dry_run: bool) -> bool:
    path = os.path.join(bench_path, "apps", app)
    ok, out = _run(f"git fetch {remote}", path, dry_run)
    if not ok:
        _err(f"{app}: git fetch {remote} failed\n    {out}")
        return False
    ok, out = _run(f"git reset --hard {remote}/{branch}", path, dry_run)
    if not ok:
        _err(f"{app}: git reset --hard failed\n    {out}")
        return False
    head = _git_head(path)
    _ok(f"{app}  {DIM}[{head}]{RESET}")
    return True


def pull_app(bench_path: str, app: str, remote: str, branch: str, dry_run: bool) -> bool:
    path = os.path.join(bench_path, "apps", app)
    ok, out = _run(f"git pull {remote} {branch}", path, dry_run)
    if not ok:
        _err(f"{app}: git pull failed\n    {out}")
        return False
    head = _git_head(path)
    _ok(f"{app}  {DIM}[{head}]{RESET}")
    return True


# ── CLI command ───────────────────────────────────────────────────────────────


@click.command("selective-update")
@click.option("--skip-build", is_flag=True, default=False, help="Skip bench build")
@click.option("--no-migrate", is_flag=True, default=False, help="Skip bench migrate")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print commands without executing",
)
@click.pass_context
def commands(ctx, skip_build, no_migrate, dry_run):
    """
    Update all bench apps — auto-detects reset vs pull per app.

    Apps with an 'upstream' remote are reset (core apps).
    Apps with only 'origin' are pulled (custom apps).
    Skip lists live in ~/.bench_management.json (never committed).
    """
    bench_path = _find_bench_path()
    if not bench_path:
        _err("Not inside a bench directory.")
        return

    cfg = load_config()
    start = time.time()
    failed = []

    click.echo(f"\n{BOLD}{'─' * 55}{RESET}")
    click.echo(
        f"{BOLD}  bench selective-update{RESET}"
        + (f"  {DIM}(dry-run){RESET}" if dry_run else "")
    )
    click.echo(f"{BOLD}{'─' * 55}{RESET}")

    reset_apps, pull_apps, skip_apps = discover_apps(bench_path, cfg)

    # ── Skipped ───────────────────────────────────────────────────────────────
    if skip_apps:
        _header("Skipping")
        for app, reason in skip_apps.items():
            _warn(f"{app}: {reason}")

    # ── Core apps — reset ─────────────────────────────────────────────────────
    _header(f"Core apps  {DIM}(git fetch + reset --hard){RESET}")
    for app, (remote, branch) in reset_apps.items():
        if not reset_app(bench_path, app, remote, branch, dry_run):
            failed.append(app)

    # ── Custom apps — pull ────────────────────────────────────────────────────
    _header(f"Custom apps  {DIM}(git pull){RESET}")
    for app, (remote, branch) in pull_apps.items():
        if not pull_app(bench_path, app, remote, branch, dry_run):
            failed.append(app)

    # ── bench migrate ─────────────────────────────────────────────────────────
    if not no_migrate:
        _header("bench migrate")
        ok, out = _run("bench migrate", bench_path, dry_run)
        if ok:
            _ok("migrate complete")
        else:
            _err(f"migrate failed\n{out}")
            failed.append("bench migrate")

    # ── bench build ───────────────────────────────────────────────────────────
    if not skip_build:
        _header("bench build")
        ok, out = _run("bench build --app frappe", bench_path, dry_run)
        if ok:
            _ok("build complete")
        else:
            _err(f"build failed\n{out}")
            failed.append("bench build")

    # ── bench restart ─────────────────────────────────────────────────────────
    _header("bench restart")
    ok, out = _run("bench restart", bench_path, dry_run)
    if ok:
        _ok("restarted")
    else:
        _warn(f"restart returned non-zero (may be OK in dev)\n{out}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = round(time.time() - start, 1)
    click.echo(f"\n{BOLD}{'─' * 55}{RESET}")
    if failed:
        click.echo(f"{BOLD}  Update complete with errors  ({elapsed}s){RESET}")
        click.echo(f"  {RED}Failed:{RESET} {', '.join(failed)}")
    else:
        click.echo(f"{BOLD}  {GREEN}Update complete{RESET}{BOLD}  ({elapsed}s){RESET}")
    click.echo(f"{BOLD}{'─' * 55}{RESET}\n")


def _find_bench_path() -> str | None:
    """Walk up from cwd to find the bench root (contains Procfile + apps/)."""
    path = os.getcwd()
    for _ in range(6):
        if os.path.isfile(os.path.join(path, "Procfile")) and os.path.isdir(
            os.path.join(path, "apps")
        ):
            return path
        path = os.path.dirname(path)
    return None

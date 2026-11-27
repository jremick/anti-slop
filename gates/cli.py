#!/usr/bin/env python3
"""Unified agent-friendly CLI entrypoint for anti-slop (`anti-slop`).

Dispatches to all anti-slop subcommands with zero third-party dependencies:
  - review: plain-English code review (shortcuts + structural risks + learned rules)
  - diff:   deterministic diff and Markdown prose gate
  - learn:  verified human-gated self-learning loop, optional library, and mining
  - mutate: diff-scoped AST mutation testing in an isolated temp copy
  - hook:   Claude Code, Antigravity, and Codex lifecycle hooks + installer
  - api:    model API and harness configuration validator
  - skill:  inspect or install the bundled agent workflow skill (SKILL.md)
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.resources
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)


DEFAULT_VERSION = "0.7.0"
SKILL_INSTALL_CHOICES: Tuple[str, ...] = ("claude", "antigravity", "codex")

SUBCOMMAND_TARGETS: Dict[str, Tuple[str, str]] = {
    "review": ("gates.review", "Run plain-English change review (shortcuts + structural + learned rules)."),
    "diff": ("gates.diff_check", "Run deterministic diff and Markdown prose gate."),
    "learn": ("gates.learn", "Manage verified self-learning rules, optional packs, and pattern mining."),
    "mutate": ("gates.mutate", "Run diff-scoped Python AST mutation testing in an isolated temp copy."),
    "hook": ("gates.hooks.run_diff_gate_hook", "Run or install Claude Code, Antigravity, and Codex lifecycle hooks."),
    "api": ("gates.api_checks", "Validate model API and harness JSON configs."),
}


def get_version(*, version_file: Optional[Path] = None) -> str:
    """Resolve the anti-slop version from repo VERSION, installed metadata, or fallback."""
    candidate = (
        version_file
        if version_file is not None
        else (Path(__file__).resolve().parents[1] / "VERSION")
    )
    try:
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass

    if version_file is None:
        try:
            return importlib.metadata.version("anti-slop")
        except importlib.metadata.PackageNotFoundError:
            pass

    return DEFAULT_VERSION


def load_bundled_skill() -> str:
    """Load the bundled skills/anti-slop/SKILL.md from checkout or installed package data."""
    local_path = Path(__file__).resolve().parents[1] / "skills" / "anti-slop" / "SKILL.md"
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8")

    try:
        resource = (
            importlib.resources.files("skills")
            .joinpath("anti-slop")
            .joinpath("SKILL.md")
        )
        return resource.read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, OSError, AttributeError) as exc:
        raise FileNotFoundError(
            f"Unable to locate bundled skills/anti-slop/SKILL.md: {exc}"
        ) from exc


def resolve_skill_install_path(
    target: str,
    *,
    home: Optional[Path] = None,
    dest: Optional[Path | str] = None,
) -> Path:
    """Resolve destination SKILL.md path for target agent harness or explicit --dest override."""
    if dest is not None:
        dest_path = Path(dest).expanduser()
        if dest_path.suffix.lower() == ".md" or dest_path.is_file():
            return dest_path
        return dest_path / "SKILL.md"

    base_home = home if home is not None else Path.home()
    if target == "claude":
        return base_home / ".claude" / "skills" / "anti-slop" / "SKILL.md"
    if target == "antigravity":
        return base_home / ".gemini" / "config" / "skills" / "anti-slop" / "SKILL.md"
    if target == "codex":
        return base_home / ".codex" / "skills" / "anti-slop" / "SKILL.md"
    raise ValueError(f"Unsupported skill install target: {target}")


def _skill_result(
    *,
    ok: bool,
    target: str,
    dest_path: Optional[Path] = None,
    backup_path: Optional[Path] = None,
    changed: bool = False,
    dry_run: bool = False,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "target": target,
        "dest_path": str(dest_path) if dest_path is not None else None,
        "backup_path": str(backup_path) if backup_path is not None else None,
        "changed": changed,
        "dry_run": dry_run,
        "error": error,
    }


def _write_skill_with_backup(
    target_path: Path,
    skill_text: str,
    backup_path: Optional[Path],
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path is not None:
        shutil.copy2(target_path, backup_path)
    target_path.write_text(skill_text, encoding="utf-8")


def install_skill(
    target: str,
    *,
    dry_run: bool = False,
    dest: Optional[Path | str] = None,
    home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Install bundled SKILL.md safely with backup on diff, idempotency, and dry-run support."""
    if target not in SKILL_INSTALL_CHOICES:
        err = f"Unsupported target '{target}'. Choose from: {', '.join(SKILL_INSTALL_CHOICES)}."
        return _skill_result(ok=False, target=target, dry_run=dry_run, error=err)

    try:
        skill_text = load_bundled_skill()
        target_path = resolve_skill_install_path(target, home=home, dest=dest)
    except (OSError, ValueError) as exc:
        return _skill_result(ok=False, target=target, dry_run=dry_run, error=str(exc))

    if target_path.is_dir():
        err = f"Destination path is a directory, not a file: {target_path}"
        return _skill_result(ok=False, target=target, dest_path=target_path, dry_run=dry_run, error=err)

    file_exists = target_path.exists()
    try:
        changed = (target_path.read_text(encoding="utf-8") != skill_text) if file_exists else True
    except OSError as exc:
        err = f"Failed to read existing skill file {target_path}: {exc}"
        return _skill_result(ok=False, target=target, dest_path=target_path, dry_run=dry_run, error=err)

    backup_path = target_path.with_name(target_path.name + ".bak-antislop") if (file_exists and changed) else None
    if changed and not dry_run:
        try:
            _write_skill_with_backup(target_path, skill_text, backup_path)
        except OSError as exc:
            err = f"Failed to write skill file {target_path}: {exc}"
            return _skill_result(
                ok=False, target=target, dest_path=target_path, backup_path=backup_path, dry_run=dry_run, error=err
            )

    return _skill_result(
        ok=True, target=target, dest_path=target_path, backup_path=backup_path, changed=changed, dry_run=dry_run
    )


def _run_skill_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="anti-slop skill",
        description="Inspect or install the bundled anti-slop agent workflow skill (SKILL.md).",
    )
    sub = parser.add_subparsers(dest="skill_command", required=True)
    sub.add_parser("show", help="Print the bundled skills/anti-slop/SKILL.md content.")

    p_install = sub.add_parser(
        "install",
        help="Install SKILL.md for claude, antigravity, or codex (with *.bak-antislop backup).",
    )
    p_install.add_argument(
        "target",
        choices=SKILL_INSTALL_CHOICES,
        help="Target agent harness (claude, antigravity, or codex).",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview destination and backup behavior without writing to disk.",
    )
    p_install.add_argument(
        "--dest",
        default=None,
        help="Optional destination file or directory override (defaults to harness skills directory).",
    )

    args = parser.parse_args(argv)
    if args.skill_command == "show":
        try:
            content = load_bundled_skill()
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        sys.stdout.write(content if content.endswith("\n") else content + "\n")
        return 0

    res = install_skill(args.target, dry_run=args.dry_run, dest=args.dest)
    if not res["ok"]:
        print(f"error: {res['error']}", file=sys.stderr)
        return 1

    prefix = "[dry-run] " if args.dry_run else ""
    if not res["changed"]:
        print(f"{prefix}anti-slop skill already up to date at {res['dest_path']} (no changes).")
        return 0

    if args.dry_run:
        action = "update" if res["backup_path"] else "install"
        backup_note = f" (backup: {res['backup_path']})" if res["backup_path"] else ""
        print(f"{prefix}Would {action} {res['dest_path']}{backup_note}")
        return 0

    if res["backup_path"]:
        print(f"Backed up existing skill to {res['backup_path']}")
    print(f"Installed anti-slop skill for {args.target} at {res['dest_path']}")
    return 0


def _format_top_level_help() -> str:
    lines = [
        f"usage: anti-slop [--version] <subcommand> [args...]",
        "",
        "Agent-first, human-guided anti-slop CLI.",
        "",
        "subcommands:",
    ]
    for name, (_, desc) in SUBCOMMAND_TARGETS.items():
        lines.append(f"  {name:<8} {desc}")
    lines.append(
        "  skill    Show or install the bundled SKILL.md for claude, antigravity, or codex."
    )
    lines.extend([
        "",
        "options:",
        "  -h, --help     Show this help message and exit.",
        "  -V, --version  Show program version and exit.",
        "",
        "Run 'anti-slop <subcommand> --help' for subcommand options.",
    ])
    return "\n".join(lines)


def _dispatch_subcommand(name: str, rest: Sequence[str]) -> int:
    if name == "skill":
        return _run_skill_cli(rest)
    mod_name, _ = SUBCOMMAND_TARGETS[name]
    module = importlib.import_module(mod_name)
    entry_fn: Callable[[Optional[Sequence[str]]], int] = getattr(module, "main")
    return int(entry_fn(list(rest)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(_format_top_level_help())
        return 0

    if args[0] == "help":
        if len(args) >= 2 and (args[1] in SUBCOMMAND_TARGETS or args[1] == "skill"):
            return _dispatch_subcommand(args[1], ["--help"])
        print(_format_top_level_help())
        return 0

    if args[0] in ("-V", "--version"):
        print(f"anti-slop {get_version()}")
        return 0

    cmd = args[0]
    rest = args[1:]
    if cmd in SUBCOMMAND_TARGETS or cmd == "skill":
        return _dispatch_subcommand(cmd, rest)

    print(
        f"anti-slop: unknown subcommand '{cmd}'. Run 'anti-slop --help' for available subcommands.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

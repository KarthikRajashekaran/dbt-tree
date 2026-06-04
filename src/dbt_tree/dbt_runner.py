"""Run `dbt ls --output json` and parse the result into Node objects.

We deliberately let dbt own selector parsing: whatever the user passes through
(`model+`, `+model`, `tag:x+`, set unions, ...) is forwarded verbatim, so the
tool matches dbt's selection exactly with zero re-implementation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

from .graph import DEFAULT_RESOURCE_TYPES, Node

OUTPUT_KEYS = [
    "unique_id",
    "name",
    "resource_type",
    "depends_on",
    "config",
    "original_file_path",
    "tags",
    "package_name",
]


class DbtError(RuntimeError):
    """Raised when the dbt executable is missing or `dbt ls` fails hard."""


@dataclass
class DbtInvocation:
    dbt: str
    project_dir: str | None = None
    target: str | None = None
    profiles_dir: str | None = None
    extra_args: list[str] | None = None


def _is_fusion(dbt_path: str) -> bool:
    """dbt Fusion (Rust) is stricter and has a different `ls` surface; detect it."""
    try:
        out = subprocess.run(
            [dbt_path, "--version"], capture_output=True, text=True, timeout=15
        )
    except Exception:  # pragma: no cover - best-effort probe
        return False
    return "dbt-fusion" in (out.stdout + out.stderr).lower()


def find_dbt(explicit: str | None = None) -> str:
    # Explicit wins. Then $DBT_TREE_DBT. Then the *active virtualenv* (what
    # `source .../activate` sets VIRTUAL_ENV), so dbt-tree follows the
    # same dbt you'd get by typing `dbt` in that shell. PATH is the last resort.
    explicit_choice = explicit or os.environ.get("DBT_TREE_DBT")
    if explicit_choice:
        resolved = shutil.which(explicit_choice)
        if resolved:
            return resolved
        if os.path.sep in explicit_choice and os.path.exists(explicit_choice):
            return explicit_choice
        raise DbtError(
            f"could not find dbt executable '{explicit_choice}' "
            "(from --dbt-executable / $DBT_TREE_DBT)."
        )

    candidates: list[str] = []
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidates.append(os.path.join(venv, "bin", "dbt"))
    # Common dbt-core venv locations, so it still works if you forget to activate.
    home = os.path.expanduser("~")
    for sub in ("dbt-venv", ".dbt-venv", "venv", ".venv"):
        candidates.append(os.path.join(home, sub, "bin", "dbt"))
    path_dbt = shutil.which("dbt")
    if path_dbt:
        candidates.append(path_dbt)

    seen: set[str] = set()
    ordered = [c for c in candidates if c and c not in seen and not seen.add(c)]
    existing = [c for c in ordered if os.path.exists(c)]

    for cand in existing:
        if not _is_fusion(cand):
            return cand

    if existing:
        # Only Fusion is available; Fusion isn't supported yet, so fail clearly
        # rather than emit confusing parse errors.
        raise DbtError(
            "the only dbt found is dbt Fusion, which is not supported yet "
            f"({existing[0]}).\nPoint dbt-tree at dbt-core:\n"
            "  - activate your dbt-core venv first, or\n"
            "  - set $DBT_TREE_DBT=/path/to/dbt-core/bin/dbt, or\n"
            "  - pass --dbt-executable /path/to/dbt-core/bin/dbt"
        )

    raise DbtError(
        "could not find a dbt executable. Activate your dbt virtualenv, "
        "or pass --dbt-executable / set $DBT_TREE_DBT."
    )


def _base_cmd(inv: DbtInvocation) -> list[str]:
    cmd = [inv.dbt, "--quiet", "ls", "--output", "json"]
    if inv.project_dir:
        cmd += ["--project-dir", inv.project_dir]
    if inv.target:
        cmd += ["--target", inv.target]
    if inv.profiles_dir:
        cmd += ["--profiles-dir", inv.profiles_dir]
    return cmd


def parse_nodes(stdout: str, *, resource_types: frozenset[str]) -> list[Node]:
    nodes: list[Node] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rtype = obj.get("resource_type")
        if rtype not in resource_types:
            continue
        config = obj.get("config") or {}
        depends_on = (obj.get("depends_on") or {}).get("nodes") or []
        uid = obj.get("unique_id") or obj.get("name")
        if not uid:
            continue
        nodes.append(
            Node(
                unique_id=uid,
                name=obj.get("name") or uid,
                resource_type=rtype,
                materialized=config.get("materialized"),
                tags=list(obj.get("tags") or config.get("tags") or []),
                path=obj.get("original_file_path"),
                package=obj.get("package_name"),
                depends_on=list(depends_on),
            )
        )
    return nodes


def list_nodes(
    selector: str,
    inv: DbtInvocation,
    *,
    resource_types: frozenset[str] = DEFAULT_RESOURCE_TYPES,
) -> list[Node]:
    cmd = _base_cmd(inv)
    cmd += ["--output-keys", *OUTPUT_KEYS]
    cmd += ["--select", selector]
    if inv.extra_args:
        cmd += inv.extra_args

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise DbtError(str(exc)) from exc

    nodes = parse_nodes(proc.stdout, resource_types=resource_types)
    # dbt returns 0 for an empty selection; only treat a non-zero exit with no
    # parseable nodes as a real failure.
    if not nodes and proc.returncode != 0:
        raise DbtError(_summarize_failure(inv.dbt, proc.returncode, proc.stderr, proc.stdout))
    return nodes


def _summarize_failure(dbt: str, code: int, stderr: str, stdout: str) -> str:
    blob = (stderr or stdout or "").strip()
    error_lines = [ln for ln in blob.splitlines() if "[error]" in ln.lower()]
    tail = error_lines[-3:] if error_lines else blob.splitlines()[-3:]
    msg = f"`dbt ls` exited with code {code} and produced no nodes."
    if tail:
        msg += "\n  " + "\n  ".join(line.strip() for line in tail)
    if "dbt-fusion" in blob.lower() or "dbt1060" in blob or "dbt1159" in blob:
        msg += (
            "\n\nThis looks like dbt Fusion (stricter parsing). Point dbt-tree at your "
            "dbt-core install:\n"
            "  - activate your dbt venv first, or\n"
            "  - pass --dbt-executable /path/to/dbt-core/bin/dbt, or\n"
            "  - set $DBT_TREE_DBT."
        )
    return msg


def list_all_model_names(inv: DbtInvocation) -> list[str]:
    """Used only to power 'did you mean ...' suggestions on an empty selection."""
    cmd = _base_cmd(inv)
    cmd[3:5] = ["--output", "name"]  # swap json -> name
    cmd += ["--select", "*"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:  # pragma: no cover - suggestions are best-effort
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip() and " " not in ln.strip()]

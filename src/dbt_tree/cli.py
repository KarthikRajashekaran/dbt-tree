"""Command-line entry point for dbt-tree."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .dbt_runner import DbtError, DbtInvocation, find_dbt, list_all_model_names, list_nodes
from .graph import (
    DEFAULT_RESOURCE_TYPES,
    build_forest,
    build_graph,
    extract_focal_names,
    parse_direction,
)
from .render import print_no_match, render_static, suggest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbt-tree",
        description="Interactive terminal lineage tree for dbt selectors.",
        epilog='example: dbt-tree "my_model+"',
    )
    parser.add_argument("--version", action="version", version=f"dbt-tree {__version__}")
    parser.add_argument(
        "selector",
        help='dbt selector, forwarded verbatim to `dbt ls -s` (e.g. "model+", "+model+", "tag:x+").',
    )
    parser.add_argument("--target", help="dbt target (passed to dbt ls).")
    parser.add_argument("--project-dir", help="dbt project directory.")
    parser.add_argument("--profiles-dir", help="dbt profiles directory.")
    parser.add_argument(
        "--dbt-executable", help="Path to dbt (default: $DBT_TREE_DBT or `dbt` on PATH)."
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include data tests / unit tests as nodes (off by default).",
    )
    parser.add_argument(
        "--max-depth", type=int, default=0, help="Limit tree depth (0 = unlimited)."
    )
    parser.add_argument(
        "--max-nodes", type=int, default=5000, help="Safety cap on rendered nodes."
    )
    parser.add_argument("--no-color", action="store_true", help="Disable color in plain output.")
    return parser


def _resource_types(include_tests: bool) -> frozenset[str]:
    if include_tests:
        return DEFAULT_RESOURCE_TYPES | {"test", "unit_test"}
    return DEFAULT_RESOURCE_TYPES


def main(argv: list[str] | None = None) -> int:
    args, extra = build_parser().parse_known_args(argv)

    try:
        dbt = find_dbt(args.dbt_executable)
    except DbtError as exc:
        print(f"dbt-tree: {exc}", file=sys.stderr)
        return 2

    inv = DbtInvocation(
        dbt=dbt,
        project_dir=args.project_dir,
        target=args.target,
        profiles_dir=args.profiles_dir,
        extra_args=extra or None,
    )

    try:
        nodes = list_nodes(args.selector, inv, resource_types=_resource_types(args.include_tests))
    except DbtError as exc:
        print(f"dbt-tree: {exc}", file=sys.stderr)
        return 2

    focal = extract_focal_names(args.selector)

    if not nodes:
        names = list_all_model_names(inv)
        suggestions: list[str] = []
        for want in focal:
            suggestions += suggest(want, names)
        print_no_match(args.selector, list(dict.fromkeys(suggestions)), no_color=args.no_color)
        return 1

    graph = build_graph(nodes)
    direction = parse_direction(args.selector)

    if direction == "both":
        focal_ids = [uid for uid, n in graph.nodes.items() if n.name in focal]
        if focal_ids:
            up_forest, up_tr = build_forest(
                graph, direction="up", roots=focal_ids,
                max_depth=args.max_depth, max_nodes=args.max_nodes,
            )
            down_forest, down_tr = build_forest(
                graph, direction="down", roots=focal_ids,
                max_depth=args.max_depth, max_nodes=args.max_nodes,
            )
            render_static(up_forest, focal, no_color=args.no_color, truncated=up_tr,
                          header="\u25b2 ancestors")
            render_static(down_forest, focal, no_color=args.no_color, truncated=down_tr,
                          header="\u25bc descendants")
            return 0
        direction = "down"  # fall back when focal can't be identified

    forest, truncated = build_forest(
        graph, direction=direction, max_depth=args.max_depth, max_nodes=args.max_nodes
    )
    render_static(forest, focal, no_color=args.no_color, truncated=truncated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

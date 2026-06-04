"""Graph model: nodes, adjacency, and the duplicated display forest.

The display forest intentionally *duplicates* shared subtrees (Unix `tree`
style) so the output mirrors how a node is reached through every path, while a
visited-path guard keeps cycles (and runaway diamonds) from exploding.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

# Resource types we treat as real lineage nodes by default. Tests / exposures /
# metrics are excluded unless the caller opts in.
DEFAULT_RESOURCE_TYPES = frozenset({"model", "seed", "snapshot", "source"})


@dataclass
class Node:
    unique_id: str
    name: str
    resource_type: str
    materialized: str | None = None
    tags: list[str] = field(default_factory=list)
    path: str | None = None
    package: str | None = None
    depends_on: list[str] = field(default_factory=list)

    @property
    def label_suffix(self) -> str:
        """`(table)` / `(view)` / `(source)` shown after the name."""
        return self.materialized or self.resource_type


@dataclass
class TreeLine:
    """One rendered row: a node plus its (duplicated) children."""

    node: Node
    children: list["TreeLine"] = field(default_factory=list)
    truncated: bool = False  # hit max_depth / max_nodes; subtree elided


@dataclass
class Graph:
    nodes: dict[str, Node]
    children: dict[str, list[str]]  # parent -> children (downstream)
    parents: dict[str, list[str]]  # child -> parents (upstream)
    down_roots: list[str]  # no selected parent (sources/focal of `model+`)
    up_roots: list[str]  # no selected child (focal of `+model`)


def build_graph(nodes: list[Node]) -> Graph:
    """Build both adjacency directions *within the selected set* and find roots.

    Edges are kept only between nodes that are both present in the selection. For
    ``model+`` the focal node has no selected parent (a ``down_root``); for
    ``+model`` it has no selected child (an ``up_root``).
    """
    by_id = {n.unique_id: n for n in nodes}
    selection = set(by_id)

    children: dict[str, list[str]] = defaultdict(list)
    parents: dict[str, list[str]] = defaultdict(list)
    has_parent: set[str] = set()
    has_child: set[str] = set()

    for node in nodes:
        for parent in node.depends_on:
            if parent in selection:
                children[parent].append(node.unique_id)
                parents[node.unique_id].append(parent)
                has_parent.add(node.unique_id)
                has_child.add(parent)

    def name_key(uid: str) -> str:
        return by_id[uid].name.lower()

    for adj in (children, parents):
        for key in adj:
            adj[key].sort(key=name_key)

    down_roots = sorted((uid for uid in by_id if uid not in has_parent), key=name_key)
    up_roots = sorted((uid for uid in by_id if uid not in has_child), key=name_key)
    return Graph(
        nodes=by_id,
        children=dict(children),
        parents=dict(parents),
        down_roots=down_roots,
        up_roots=up_roots,
    )


def build_forest(
    graph: Graph,
    *,
    direction: str = "down",
    roots: list[str] | None = None,
    max_depth: int = 0,
    max_nodes: int = 5000,
) -> tuple[list[TreeLine], bool]:
    """Expand the graph into a duplicated display forest.

    ``direction`` is ``"down"`` (walk children) or ``"up"`` (walk parents). When
    ``roots`` is None, structural roots for that direction are used.
    ``max_depth=0`` means unlimited depth. Returns ``(forest, truncated)``.
    """
    adjacency = graph.children if direction == "down" else graph.parents
    if roots is None:
        roots = graph.down_roots if direction == "down" else graph.up_roots

    budget = {"left": max_nodes}
    hit_budget = {"value": False}

    def expand(uid: str, depth: int, path: frozenset[str]) -> TreeLine:
        node = graph.nodes[uid]
        line = TreeLine(node=node)

        if budget["left"] <= 0:
            hit_budget["value"] = True
            line.truncated = True
            return line
        budget["left"] -= 1

        if max_depth and depth >= max_depth:
            if adjacency.get(uid):
                line.truncated = True
            return line

        # Cycle guard: never re-enter a node already on the current path.
        next_path = path | {uid}
        for next_uid in adjacency.get(uid, []):
            if next_uid in next_path:
                line.children.append(TreeLine(node=graph.nodes[next_uid], truncated=True))
                continue
            line.children.append(expand(next_uid, depth + 1, next_path))
        return line

    forest = [expand(uid, 0, frozenset()) for uid in roots]
    return forest, hit_budget["value"]


def parse_direction(selector: str) -> str:
    """Infer orientation from a selector: 'up', 'down', or 'both'.

    Leading ``+`` (incl. ``N+model``) means ancestors; trailing ``+`` (incl.
    ``model+N``) means descendants; ``@`` implies both. A bare name is 'down'.
    """
    up = down = False
    for token in re.split(r"[\s,]+", selector.strip()):
        if not token:
            continue
        if "@" in token:
            up = down = True
        if re.match(r"^\d*\+", token):
            up = True
        if re.search(r"\+\d*$", token):
            down = True
    if up and down:
        return "both"
    if up:
        return "up"
    return "down"


_OP = re.compile(r"^\d*\+?|\+?\d*$")


def extract_focal_names(selector: str) -> set[str]:
    """Best-effort: pull bare model names out of a selector for `*` marking.

    Strips graph operators (`+`, leading/trailing depth digits) and ignores
    method selectors (`tag:`, `path:`, ...) and set operators.
    """
    focal: set[str] = set()
    for token in re.split(r"[\s,]+", selector.strip()):
        if not token or ":" in token or "@" in token:
            continue
        bare = token.strip("+")
        bare = re.sub(r"^\d+", "", bare)
        bare = re.sub(r"\d+$", "", bare)
        bare = bare.strip("+")
        if bare:
            focal.add(bare.split(".")[-1])
    return focal

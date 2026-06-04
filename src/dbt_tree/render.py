"""Static (non-interactive) rendering with rich, plus not-found suggestions."""

from __future__ import annotations

import difflib

from rich.console import Console
from rich.tree import Tree as RichTree

from .graph import Node, TreeLine

RESOURCE_STYLE = {
    "model": "cyan",
    "source": "green",
    "seed": "yellow",
    "snapshot": "magenta",
}


def node_label(node: Node, focal: set[str]) -> str:
    style = RESOURCE_STYLE.get(node.resource_type, "white")
    star = " [bold yellow]*[/bold yellow]" if node.name in focal else ""
    return f"[{style}]{node.name}[/{style}] [dim]({node.label_suffix})[/dim]{star}"


def _attach(parent: RichTree, line: TreeLine, focal: set[str]) -> None:
    for child in line.children:
        branch = parent.add(node_label(child.node, focal))
        if child.truncated:
            branch.add("[dim]…[/dim]")
        _attach(branch, child, focal)


def render_static(
    forest: list[TreeLine],
    focal: set[str],
    *,
    no_color: bool = False,
    truncated: bool = False,
    header: str | None = None,
) -> None:
    console = Console(no_color=no_color, highlight=False)
    if header:
        console.print(f"[bold]{header}[/bold]")
    if not forest:
        console.print("[yellow]0 nodes matched the selector.[/yellow]")
        return
    for root in forest:
        tree = RichTree(node_label(root.node, focal))
        if root.truncated:
            tree.add("[dim]…[/dim]")
        _attach(tree, root, focal)
        console.print(tree)
    if truncated:
        console.print("[dim]…output truncated (node limit reached; raise --max-nodes).[/dim]")


def suggest(name: str, candidates: list[str], n: int = 5) -> list[str]:
    return difflib.get_close_matches(name, candidates, n=n, cutoff=0.5)


def print_no_match(selector: str, suggestions: list[str], *, no_color: bool = False) -> None:
    console = Console(no_color=no_color, stderr=True, highlight=False)
    console.print(f"[yellow]0 nodes matched[/yellow] selector: [bold]{selector}[/bold]")
    if suggestions:
        console.print("did you mean:")
        for s in suggestions:
            console.print(f"  [cyan]{s}[/cyan]")

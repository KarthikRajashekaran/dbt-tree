from dbt_tree.graph import (
    Node,
    build_forest,
    build_graph,
    extract_focal_names,
    parse_direction,
)


def _n(uid, name, deps=(), rtype="model", mat="table"):
    return Node(
        unique_id=uid,
        name=name,
        resource_type=rtype,
        materialized=mat,
        depends_on=list(deps),
    )


def test_roots_and_children_within_selection():
    # a -> b -> c ; a's real parents are not in the selection, so a is a root.
    nodes = [
        _n("model.p.a", "a"),
        _n("model.p.b", "b", deps=["model.p.a", "source.p.x.t"]),
        _n("model.p.c", "c", deps=["model.p.b"]),
    ]
    graph = build_graph(nodes)
    assert graph.down_roots == ["model.p.a"]
    assert graph.up_roots == ["model.p.c"]
    assert graph.children["model.p.a"] == ["model.p.b"]
    assert graph.children["model.p.b"] == ["model.p.c"]
    assert graph.parents["model.p.c"] == ["model.p.b"]


def test_upstream_orientation_roots_at_focal():
    # +c : root should be c, expanding UP to its ancestors b then a.
    nodes = [
        _n("model.p.a", "a"),
        _n("model.p.b", "b", deps=["model.p.a"]),
        _n("model.p.c", "c", deps=["model.p.b"]),
    ]
    forest, _ = build_forest(build_graph(nodes), direction="up")
    (root,) = forest
    assert root.node.name == "c"
    assert root.children[0].node.name == "b"
    assert root.children[0].children[0].node.name == "a"


def test_parse_direction():
    assert parse_direction("model+") == "down"
    assert parse_direction("+model") == "up"
    assert parse_direction("+model+") == "both"
    assert parse_direction("2+model") == "up"
    assert parse_direction("model+3") == "down"
    assert parse_direction("model") == "down"
    assert parse_direction("@model") == "both"


def test_forest_duplicates_shared_subtree():
    # diamond: a -> b, a -> c, b -> d, c -> d  => d appears under both b and c.
    nodes = [
        _n("model.p.a", "a"),
        _n("model.p.b", "b", deps=["model.p.a"]),
        _n("model.p.c", "c", deps=["model.p.a"]),
        _n("model.p.d", "d", deps=["model.p.b", "model.p.c"]),
    ]
    forest, truncated = build_forest(build_graph(nodes))
    assert not truncated
    (root,) = forest
    child_names = [c.node.name for c in root.children]
    assert child_names == ["b", "c"]
    assert [g.node.name for g in root.children[0].children] == ["d"]
    assert [g.node.name for g in root.children[1].children] == ["d"]


def test_max_depth_truncates():
    nodes = [
        _n("model.p.a", "a"),
        _n("model.p.b", "b", deps=["model.p.a"]),
        _n("model.p.c", "c", deps=["model.p.b"]),
    ]
    forest, _ = build_forest(build_graph(nodes), max_depth=1)
    (root,) = forest
    assert root.children[0].node.name == "b"
    assert root.children[0].children == []
    assert root.children[0].truncated is True


def test_cycle_guard_does_not_recurse_forever():
    # a -> b -> c -> b (back edge). a is the only root; the b re-entry must stop.
    nodes = [
        _n("model.p.a", "a"),
        _n("model.p.b", "b", deps=["model.p.a", "model.p.c"]),
        _n("model.p.c", "c", deps=["model.p.b"]),
    ]
    forest, _ = build_forest(build_graph(nodes), max_nodes=50)
    (root,) = forest
    assert root.node.name == "a"
    b = root.children[0]
    c = b.children[0]
    assert c.node.name == "c"
    # c -> b is a back edge onto the current path: rendered once, truncated.
    assert [g.node.name for g in c.children] == ["b"]
    assert c.children[0].truncated is True


def test_extract_focal_names():
    assert extract_focal_names("model_a+") == {"model_a"}
    assert extract_focal_names("+model_a+") == {"model_a"}
    assert extract_focal_names("2+model_a+3") == {"model_a"}
    assert extract_focal_names("tag:nightly+") == set()

import json

from dbt_tree.dbt_runner import parse_nodes
from dbt_tree.graph import DEFAULT_RESOURCE_TYPES


def _line(**kw):
    return json.dumps(kw)


def test_parse_filters_tests_by_default():
    stdout = "\n".join(
        [
            "Running with dbt=1.10.9",  # log preamble, must be ignored
            _line(
                unique_id="model.p.a",
                name="a",
                resource_type="model",
                config={"materialized": "view"},
                depends_on={"nodes": ["source.p.s.t"]},
                tags=["nightly"],
                original_file_path="models/a.sql",
                package_name="p",
            ),
            _line(
                unique_id="test.p.not_null_a",
                name="not_null_a",
                resource_type="test",
                config={},
                depends_on={"nodes": ["model.p.a"]},
            ),
        ]
    )
    nodes = parse_nodes(stdout, resource_types=DEFAULT_RESOURCE_TYPES)
    assert [n.unique_id for n in nodes] == ["model.p.a"]
    node = nodes[0]
    assert node.materialized == "view"
    assert node.tags == ["nightly"]
    assert node.depends_on == ["source.p.s.t"]


def test_parse_includes_tests_when_requested():
    stdout = _line(
        unique_id="test.p.x",
        name="x",
        resource_type="test",
        config={},
        depends_on={"nodes": []},
    )
    nodes = parse_nodes(stdout, resource_types=DEFAULT_RESOURCE_TYPES | {"test"})
    assert [n.unique_id for n in nodes] == ["test.p.x"]


def test_parse_skips_garbage_lines():
    assert parse_nodes("not json\n\n{bad}\n", resource_types=DEFAULT_RESOURCE_TYPES) == []

# dbt-tree

Pretty terminal lineage tree for dbt selectors. Run a selector, get a readable
tree of the resulting DAG right in your terminal — no docs server, no browser.

```bash
dbt-tree "my_model+"
```

`dbt-tree` forwards the selector **verbatim** to `dbt ls`, so every dbt selector
works exactly as it does in dbt itself: `model+`, `+model`, `+model+`,
`2+model+3`, `tag:nightly+`, `path:models/marts`, set unions, and so on.

## Requirements

- A working **dbt-core** install that you can run as `dbt` (any virtualenv tool is
  fine — `venv`, `virtualenv`, `conda`, `poetry`, `uv`, …). The only requirement
  is that the `dbt` executable is reachable (active venv, on `PATH`, or via
  `$DBT_TREE_DBT` / `--dbt-executable`).
- Python 3.10+.

`dbt ls` is parse-only, so **no warehouse connection is needed** to draw the tree.

## Install

Install into the **same environment as your dbt** so they share a `PATH`:

```bash
pip install dbt-tree
# or, latest from source:
pip install "git+https://github.com/KarthikRajashekaran/dbt-tree.git"
```

`dbt` itself is **not** a Python dependency — `dbt-tree` shells out to your
existing dbt rather than pinning a version.

### Which dbt does it use?

Resolution order:

1. `--dbt-executable`
2. `$DBT_TREE_DBT`
3. **the active virtualenv** (`$VIRTUAL_ENV/bin/dbt`) — so once you activate your
   dbt venv, dbt-tree uses the same dbt as your shell
4. `dbt` on `PATH`

dbt-tree prefers **dbt-core** and will skip a **dbt Fusion** binary when a core
install is available (Fusion's stricter parsing and different `ls` surface aren't
supported yet). 

### Recommended workflow:

```bash
gva # activate your dbt venv (dbt-core)
dbt-tree "my_model+"
```

Tip: `pip install` dbt-tree *into that same dbt venv* so `gva` puts both `dbt` and
`dbt-tree` on your `PATH` together.

## Usage

```bash
# Downstream lineage
dbt-tree "my_model+"

# Upstream lineage
dbt-tree "+my_model"

# Scope / dbt passthrough
dbt-tree "tag:nightly+" --target prod --project-dir dbt/my_project
```

Example output:

```text
my_model (view) *
└── stg_orders (table)
    └── int_orders_joined (table)
        ├── fct_orders (table)
        │   ├── mart_revenue (table)
        │   └── ...
        └── fct_order_items (table)
```

The originally-selected model is marked with `*`. Nodes are colored by resource
type; the suffix shows materialization (`table`/`view`) or resource type
(`source`/`seed`/`snapshot`).

### Orientation follows the selector

The tree is rooted so the focal model is always at the top:

- `model+` (downstream) — root is the model, children are its descendants.
- `+model` (upstream) — root is the model, children are its **ancestors** (up to
  sources/seeds).
- `+model+` (both) — two sections: `▲ ancestors` then `▼ descendants`.

## How it works

1. Runs `dbt --quiet ls --output json --output-keys ... --select <selector>`.
2. Keeps models, sources, seeds, and snapshots (tests off unless `--include-tests`).
3. Builds child adjacency **within the selected set**, finds roots, and expands a
   duplicated tree (Unix `tree` style) with cycle and node-count guards.
4. Renders a `rich` tree (duplicating shared subtrees, `tree`-command style).

## Options

| flag | default | meaning |
|---|---|---|
| `--target` | — | dbt target |
| `--project-dir` | — | dbt project directory |
| `--profiles-dir` | — | dbt profiles directory |
| `--dbt-executable` | `dbt` | path to dbt |
| `--include-tests` | off | include data/unit tests as nodes |
| `--max-depth` | `0` | limit depth (0 = unlimited) |
| `--max-nodes` | `5000` | safety cap on rendered nodes |
| `--no-color` | off | disable color in plain output |

Unknown flags are forwarded to `dbt ls` as an escape hatch.

## Limitations

- **Single project.** Lineage covers whatever `dbt ls` resolves in the active
  project; it does not stitch across sibling projects in a monorepo.
- Selector parsing is dbt's, so behavior matches your installed dbt version.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

Apache-2.0

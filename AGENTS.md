# AGENTS.md

ComfyUI custom node pack built on the V3 node API (`comfy_api.latest`). Follow https://docs.comfy.org/custom-nodes/walkthrough.

## Layout

```
__init__.py                 # ComfyUI entrypoint: comfy_entrypoint() -> ComfyExtension
supernova/nodes/__init__.py # NODES list: register every node here
supernova/nodes/<name>.py   # io.ComfyNode: schema + thin execute()
supernova/core/<name>.py    # logic. Imports torch only, never comfy / comfy_api
tests/test_<name>.py        # tests for supernova/core
pyproject.toml              # metadata, version, deps, ruff/pytest config
```

`example_invert` is a template. Copy it for a new node, then delete it.

## Setup

Needs [uv](https://docs.astral.sh/uv/) (Windows: `winget install astral-sh.uv`).

```
uv sync                 # creates .venv with Python, pytest, ruff, CPU torch
uv run pytest
uv run ruff check --fix . && uv run ruff format .
```

Commit `uv.lock` whenever it changes.

## New node

1. `supernova/core/<name>.py`: pure functions that do the work.
2. `supernova/nodes/<name>.py`: a `io.ComfyNode` subclass with:
   - `define_schema()` returns `io.Schema(node_id=, display_name=, category=, description=, inputs=[...], outputs=[...])`
   - `node_id="Supernova<Name>"`, `display_name="<Name> (Supernova)"`, `category="Supernova/<group>"`
   - a `tooltip` on every input and output
   - `execute(...)` calls the core function and returns `io.NodeOutput(...)`
3. Add the class to `NODES` in `supernova/nodes/__init__.py`.
4. Add tests and docs (below).

Rules:
- Renaming a `node_id`, input or output breaks saved workflows. If a rename seems important, ask the user first. Alternatives: `is_deprecated=True` plus a new node, or register an `io.NodeReplace` via `ComfyAPI().node_replacement.register(...)` in `ComfyExtension.on_load()` (see ComfyUI's `comfy_extras/nodes_replacements.py`).
- Follow ComfyUI tensor formats: `IMAGE` is `[B,H,W,C]` float 0–1, `MASK` is `[B,H,W]`, `LATENT` is `{"samples": ...}`.
- Don't mutate inputs; return new tensors.
- In nodes, use `comfy.model_management` for devices. Don't hardcode `cuda`.
- Use `logging`, not `print`.
- No network calls or telemetry unless the user asks for them.

## Tests

- Test every `supernova/core` function: normal path, edge cases (batch size 1 and >1, alpha channel, odd sizes), invalid input, no input mutation.
- Tests run on CPU without ComfyUI. Don't import `supernova.nodes` or `comfy*` in tests.
- The root `__init__.py` needs ComfyUI to import. `tests/root_dir_plugin.py` (loaded via `-p root_dir_plugin` in `pyproject.toml`) stops pytest from importing it. Don't remove it.
- `uv run pytest` and `ruff` must pass before committing. CI runs both.

## Docs

Update these in the same change:
- Node info: `description`, `tooltip`s, `category`.
- `README.md`: node table (name, category, purpose), install steps.
- `AGENTS.md`: update it when conventions, layout or tooling change.
- `pyproject.toml`: bump `version` (semver) for releases.

## Git

- Never commit directly to `main`.
- Branches: `feat/<short-desc>`, `fix/…`, `docs/…`, `test/…`, `chore/…`, `refactor/…` (kebab-case).
- Commits use [Conventional Commits](https://www.conventionalcommits.org): `feat(node-name): add X`. Imperative mood, subject ≤ 72 chars.
- One logical change per commit.

## Ask the user

- Adding a runtime dependency needs the user's approval: say why it's needed and what the alternatives are. Once approved, add it to `[project].dependencies`. Never list torch, numpy or PIL there (ComfyUI provides them). Dev-only tools go in `[dependency-groups].dev`.
- When you need input from the user, ask through the IDE's question UI (multiple choice where possible), not in plain chat text.
- Also ask before: renaming or removing nodes, bumping the version, publishing, force-pushing.

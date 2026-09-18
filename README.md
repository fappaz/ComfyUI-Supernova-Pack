# ComfyUI-Supernova-Pack
Pack of nodes with useful features not available natively in ComfyUI

## Install

Clone into `ComfyUI/custom_nodes/` and restart ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/fappaz/ComfyUI-Supernova-Pack.git
```

## Nodes

| Node | Category | Purpose |
|---|---|---|
| Example Invert (Supernova) | Supernova/examples | Template to copy for new nodes. Delete it along with the example. |

## Development

Requires [uv](https://docs.astral.sh/uv/) (Windows: `winget install astral-sh.uv`).

```
uv sync          # dev env: Python, pytest, ruff, CPU torch
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

See [AGENTS.md](AGENTS.md) for conventions.

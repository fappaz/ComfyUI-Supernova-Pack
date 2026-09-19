"""Helpers for reading the submitted workflow (ComfyUI's hidden PROMPT input)."""

from __future__ import annotations


def used_outputs(prompt: dict | None, node_id: str | None) -> set[int] | None:
    """Indices of a node's outputs that other nodes in the workflow read. None if unknown."""
    if not prompt or node_id is None:
        return None
    used = set()
    for node in prompt.values():
        for value in node.get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) == str(node_id):
                used.add(value[1])
    return used

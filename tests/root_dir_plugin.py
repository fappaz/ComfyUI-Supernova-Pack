from pathlib import Path

import pytest


def pytest_collect_directory(path, parent):
    # The repo root's __init__.py is the ComfyUI entrypoint and needs ComfyUI to import.
    # Collect the root as a plain directory so pytest doesn't import it.
    if path == Path(__file__).parent.parent:
        return pytest.Dir.from_parent(parent, path=path)

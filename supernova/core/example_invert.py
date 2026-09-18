"""TEMPLATE: example logic module. Copy it for new nodes, then delete it."""

import torch


def invert(image: torch.Tensor) -> torch.Tensor:
    """Invert the RGB channels of an IMAGE tensor ([B,H,W,C], 0-1), keeping alpha."""
    out = image.clone()
    out[..., :3] = 1.0 - out[..., :3]
    return out

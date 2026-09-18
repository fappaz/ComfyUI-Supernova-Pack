import torch

from supernova.core.example_invert import invert


def test_inverts_rgb():
    image = torch.tensor([[[[0.0, 0.25, 1.0]]]])
    assert torch.allclose(invert(image), torch.tensor([[[[1.0, 0.75, 0.0]]]]))


def test_keeps_alpha_and_shape():
    image = torch.rand(2, 4, 3, 4)
    out = invert(image)
    assert out.shape == image.shape
    assert torch.equal(out[..., 3], image[..., 3])


def test_does_not_mutate_input():
    image = torch.rand(1, 2, 2, 3)
    before = image.clone()
    invert(image)
    assert torch.equal(image, before)

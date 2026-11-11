"""Tiny float autoencoder in PyTorch.

The network sees a window of four readings (eight numbers) and tries to rebuild
it. Normal windows rebuild well; a spike, a stuck sensor or a humidity jump does
not, so the reconstruction error is the anomaly score.
"""
import numpy as np
import torch
from torch import nn

from .data import FEATURES

# Layer widths: 8 inputs -> 8 -> 4 (bottleneck) -> 8 outputs. Two ReLU layers and one linear output.
LAYER_SIZES = (FEATURES, 8, 4, FEATURES)


class Autoencoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc1 = nn.Linear(LAYER_SIZES[0], LAYER_SIZES[1])
        self.enc2 = nn.Linear(LAYER_SIZES[1], LAYER_SIZES[2])
        self.out = nn.Linear(LAYER_SIZES[2], LAYER_SIZES[3])

    def forward(self, x):
        x = torch.relu(self.enc1(x))
        x = torch.relu(self.enc2(x))
        return self.out(x)


def train(features, seed=3, epochs=2500, learning_rate=1e-2):
    """Train on normal windows only, so the model learns what a normal room looks like."""
    torch.manual_seed(seed)
    model = Autoencoder()
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    data = torch.tensor(features, dtype=torch.float32)
    loss_fn = nn.MSELoss()
    for _ in range(epochs):
        optimiser.zero_grad()
        loss = loss_fn(model(data), data)
        loss.backward()
        optimiser.step()
    model.eval()
    return model


def affine(x, weight, bias):
    """x @ weight.T + bias in float32, checked for finite results.

    On macOS, NumPy's Accelerate BLAS sets spurious floating-point flags on some
    large matrices (the result is still correct), so the warnings are muted here
    and the finite check does the real guarding.
    """
    with np.errstate(divide='ignore', over='ignore', invalid='ignore'):
        result = x @ weight.T + bias
    if not np.isfinite(result).all():
        raise FloatingPointError('non-finite activation in the float model')
    return result


def float_weights(model):
    """Return [(weight[out,in], bias[out], relu)] as float32 numpy arrays."""
    layers = [(model.enc1, True), (model.enc2, True), (model.out, False)]
    return [(layer.weight.detach().numpy().astype(np.float32),
             layer.bias.detach().numpy().astype(np.float32), relu)
            for layer, relu in layers]


def float_scores(weights, features):
    """Mean squared reconstruction error per window, computed in float."""
    x = features.astype(np.float32)
    activation = x
    for weight, bias, relu in weights:
        activation = affine(activation, weight, bias)
        if relu:
            activation = np.maximum(activation, 0)
    return np.mean((activation - x) ** 2, axis=1)

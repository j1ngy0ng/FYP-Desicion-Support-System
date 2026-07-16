import numpy as np
import torch
from torch import nn


def fit_temperature(logits: list[np.ndarray], labels: list[int]) -> float:
    values = torch.tensor(np.array(logits), dtype=torch.float32)
    targets = torch.tensor(labels, dtype=torch.long)
    log_temperature = torch.zeros(1, requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], lr=.05, max_iter=60)

    def closure() -> torch.Tensor:
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(values / log_temperature.exp(), targets)
        loss.backward()
        return loss

    optimizer.step(closure)
    return float(log_temperature.exp().clamp(.5, 5).item())

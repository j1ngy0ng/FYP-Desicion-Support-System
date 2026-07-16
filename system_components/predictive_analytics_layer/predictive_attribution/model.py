from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn

from system_components.data_management_layer.data_preprocessing import FEATURES
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import ACTIONS


class CampaignNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(len(FEATURES), 16), nn.ReLU(), nn.Linear(16, len(ACTIONS)))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.layers(features)


class PredictiveAttribution:
    def __init__(self, train: pd.DataFrame) -> None:
        self.scaler = StandardScaler().fit(train[list(FEATURES)])
        self.model = CampaignNet()
        inputs = torch.tensor(self.scaler.transform(train[list(FEATURES)]), dtype=torch.float32)
        labels = torch.tensor([ACTIONS.index(label) for label in train.model_label], dtype=torch.long)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=.015, weight_decay=1e-4)
        for _ in range(220):
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(self.model(inputs), labels)
            loss.backward()
            optimizer.step()
        self.model.eval()
        self.channel_evidence = self._channel_evidence(train)

    @staticmethod
    def _channel_evidence(frame: pd.DataFrame) -> dict[str, float]:
        values: dict[str, list[float]] = {}
        for row in frame.itertuples():
            score = float(row.ROI) + 5 * float(row.Conversions / row.Clicks if row.Clicks else 0)
            for channel in str(row.Channel_Used).split(","):
                values.setdefault(channel.strip(), []).append(score)
        means = {key: float(np.mean(value)) for key, value in values.items()}
        low, high = min(means.values()), max(means.values())
        return {key: (value - low) / (high - low or 1) for key, value in means.items()}

    def evidence(self, features: dict[str, float], explain: bool = False) -> tuple[np.ndarray, list[dict[str, float | str]]]:
        scaled = self.scaler.transform(pd.DataFrame([[features[name] for name in FEATURES]], columns=FEATURES))
        tensor = torch.tensor(scaled, dtype=torch.float32, requires_grad=explain)
        logits = self.model(tensor)[0]
        probabilities = torch.softmax(logits, dim=0)
        if not explain:
            return probabilities.detach().numpy(), []
        logits[probabilities.argmax()].backward()
        impacts = np.abs(tensor.grad.detach().numpy()[0] * scaled[0])
        impacts /= impacts.sum() or 1
        attribution = sorted(
            ({"feature": name, "contribution": round(float(value), 4)} for name, value in zip(FEATURES, impacts)),
            key=lambda item: item["contribution"],
            reverse=True,
        )
        return probabilities.detach().numpy(), attribution[:5]

    def channels(self, case: dict[str, Any]) -> list[dict[str, float | str]]:
        names = [name.strip() for name in str(case.get("channels", case.get("Channel_Used", ""))).split(",") if name.strip()]
        return sorted(
            ({"channel": name, "contribution": round(self.channel_evidence.get(name, .5), 4)} for name in names),
            key=lambda item: item["contribution"],
            reverse=True,
        )

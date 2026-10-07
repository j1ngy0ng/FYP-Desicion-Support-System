from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn

from system_components.data_management_layer.data_preprocessing import FEATURES


PREDICTIVE_FEATURES = tuple(
    feature for feature in FEATURES if feature not in {"ROI", "Revenue"}
)
ACTION_CLASSES = ("Increase", "Maintain", "Reduce", "Investigate")
INTENT_CLASSES = ("Survival", "Retention", "Growth")


class CampaignNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(len(PREDICTIVE_FEATURES), 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.layers(features)


class ActionNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(len(FEATURES) + len(INTENT_CLASSES), 24),
            nn.ReLU(),
            nn.Linear(24, len(ACTION_CLASSES)),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.layers(features)


class PredictiveAttribution:
    def __init__(self, train: pd.DataFrame) -> None:
        self.scaler = StandardScaler().fit(train[list(PREDICTIVE_FEATURES)])
        self.model = CampaignNet()
        inputs = torch.tensor(
            self.scaler.transform(train[list(PREDICTIVE_FEATURES)]),
            dtype=torch.float32,
        )
        roi = train.ROI.astype(float).clip(train.ROI.quantile(.01), train.ROI.quantile(.99))
        self.target_mean = float(roi.mean())
        self.target_std = float(roi.std() or 1.0)
        targets = torch.tensor(
            ((roi - self.target_mean) / self.target_std).to_numpy(),
            dtype=torch.float32,
        )
        optimizer = torch.optim.Adam(self.model.parameters(), lr=.015, weight_decay=1e-4)
        epochs = 80 if len(train) > 5_000 else 220
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = nn.functional.mse_loss(self.model(inputs).squeeze(1), targets)
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
        scaled = self.scaler.transform(
            pd.DataFrame(
                [[features[name] for name in PREDICTIVE_FEATURES]],
                columns=PREDICTIVE_FEATURES,
            )
        )
        tensor = torch.tensor(scaled, dtype=torch.float32, requires_grad=explain)
        predicted_roi = self.model(tensor)[0, 0] * self.target_std + self.target_mean
        logits = torch.stack(
            (
                (predicted_roi - 1.25) / 1.5,
                .8 - torch.abs(predicted_roi - 1.0) / 1.5,
                (.5 - predicted_roi) / 1.2,
                predicted_roi.new_tensor(-.1),
            )
        )
        probabilities = torch.softmax(logits, dim=0)
        if not explain:
            return probabilities.detach().numpy(), []
        logits[probabilities.argmax()].backward()
        impacts = np.abs(tensor.grad.detach().numpy()[0] * scaled[0])
        impacts /= impacts.sum() or 1
        attribution = sorted(
            (
                {"feature": name, "contribution": round(float(value), 4)}
                for name, value in zip(PREDICTIVE_FEATURES, impacts)
            ),
            key=lambda item: item["contribution"],
            reverse=True,
        )
        return probabilities.detach().numpy(), attribution[:5]

    def channels(self, case: dict[str, Any]) -> list[dict[str, float | str]]:
        value = case.get("channels", case.get("Channel_Used", ""))
        items = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
        names = [str(name).strip() for name in items if str(name).strip()]
        return sorted(
            ({"channel": name, "contribution": round(self.channel_evidence.get(name, .5), 4)} for name in names),
            key=lambda item: item["contribution"],
            reverse=True,
        )


class SupervisedActionEvidence:
    """Action evidence learned only from a chronological annotation training split."""

    def __init__(self, train: pd.DataFrame) -> None:
        required = {"Reviewer_Intent", "Reviewer_Action"}
        if not required.issubset(train.columns):
            raise ValueError("Action supervision requires Reviewer_Intent and Reviewer_Action.")
        intents = train["Reviewer_Intent"].astype(str).str.title()
        actions = train["Reviewer_Action"].astype(str).str.title()
        if not intents.isin(INTENT_CLASSES).all():
            raise ValueError("Unsupported Reviewer_Intent value.")
        if not actions.isin(ACTION_CLASSES).all():
            raise ValueError("Unsupported Reviewer_Action value.")

        self.scaler = StandardScaler().fit(train[list(FEATURES)])
        numeric = self.scaler.transform(train[list(FEATURES)])
        intent_values = np.zeros((len(train), len(INTENT_CLASSES)), dtype=np.float32)
        for index, intent in enumerate(intents):
            intent_values[index, INTENT_CLASSES.index(intent)] = 1.0
        inputs = torch.tensor(
            np.concatenate((numeric, intent_values), axis=1),
            dtype=torch.float32,
        )
        targets = torch.tensor(
            [ACTION_CLASSES.index(action) for action in actions],
            dtype=torch.long,
        )
        self.model = ActionNet()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=.012, weight_decay=1e-4)
        epochs = 80 if len(train) > 5_000 else 220
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(self.model(inputs), targets)
            loss.backward()
            optimizer.step()
        self.model.eval()

    def evidence(
        self,
        features: dict[str, float],
        intent: str | None,
    ) -> np.ndarray:
        numeric = self.scaler.transform(
            pd.DataFrame(
                [[features[name] for name in FEATURES]],
                columns=FEATURES,
            )
        )
        intent_values = np.zeros((1, len(INTENT_CLASSES)), dtype=np.float32)
        if intent in INTENT_CLASSES:
            intent_values[0, INTENT_CLASSES.index(intent)] = 1.0
        inputs = torch.tensor(
            np.concatenate((numeric, intent_values), axis=1),
            dtype=torch.float32,
        )
        return torch.softmax(self.model(inputs)[0], dim=0).detach().numpy()

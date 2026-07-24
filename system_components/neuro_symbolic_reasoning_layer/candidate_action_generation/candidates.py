import numpy as np


ACTIONS = ("Increase", "Maintain", "Reduce", "Investigate")


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max()
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum()


def rank_actions(scores: np.ndarray, temperature: float) -> list[dict[str, float | str]]:
    probabilities = softmax(scores / temperature)
    return sorted(
        ({"action": action, "score": round(float(probabilities[index]), 4)} for index, action in enumerate(ACTIONS)),
        key=lambda item: float(item["score"]),
        reverse=True,
    )

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from quant_agents.ml.preprocessing import make_preprocessor


def make_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("prep", make_preprocessor()),
            ("clf", LogisticRegression(random_state=0, max_iter=200)),
        ]
    )

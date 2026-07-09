# Trains the optional scam classifier (model/scam_model.joblib).
# Usage: python train_model.py  (needs requirements-ml.txt)
#
# Char n-grams work for Chinese and English without word segmentation, and
# logistic regression keeps the saved model tiny. Scores below are cross-
# validated, not training-set, so they're a fair estimate of generalisation.

import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

from model.train_data import TRAIN

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "scam_model.joblib")


def build_pipeline():
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1),
            ),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000)),
        ]
    )


def main():
    texts = [t for t, _ in TRAIN]
    labels = [y for _, y in TRAIN]

    pipe = build_pipeline()

    scores = cross_val_score(pipe, texts, labels, cv=5, scoring="f1")
    print(
        f"Training examples: {len(TRAIN)} ({sum(labels)} scam / {len(labels) - sum(labels)} not)"
    )
    print(f"5-fold cross-validated F1: {scores.mean():.2f} (+/- {scores.std():.2f})")

    pipe.fit(texts, labels)
    joblib.dump(pipe, MODEL_PATH)
    print(f"Saved model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()

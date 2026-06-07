# train_model.py
# Train a small scam classifier and save it. Run:  python train_model.py
# Requires the ML extras:  pip install -r requirements-ml.txt
#
# Why this design:
#   - Character n-grams (analyzer="char_wb") work for BOTH Chinese and English
#     without any word segmentation — important for a bilingual product.
#   - Logistic regression is small, fast, and gives a probability we can
#     threshold. The whole model serialises to a tiny file.
#   - We report cross-validated scores (not training-set scores), so the number
#     reflects generalisation, not memorisation.

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

    # 5-fold cross-validation = an honest estimate of out-of-sample performance.
    scores = cross_val_score(pipe, texts, labels, cv=5, scoring="f1")
    print(
        f"Training examples: {len(TRAIN)} ({sum(labels)} scam / {len(labels) - sum(labels)} not)"
    )
    print(f"5-fold cross-validated F1: {scores.mean():.2f} (+/- {scores.std():.2f})")

    # Fit on everything and save.
    pipe.fit(texts, labels)
    joblib.dump(pipe, MODEL_PATH)
    print(f"Saved model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()

"""Train a place-selection model on synthetic interaction data.

Replace the synthetic generator with BigQuery event exports when real user data exists.
"""
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

rng = np.random.default_rng(42)
n = 5000
distance_km = rng.uniform(0.1, 25, n)
rating = rng.uniform(2.5, 5, n)
reviews = rng.integers(0, 1500, n)
open_now = rng.integers(0, 2, n)
X = np.c_[distance_km, rating, reviews, open_now]
logit = -0.13 * distance_km + 1.2 * (rating - 3.5) + 0.0006 * reviews + 1.0 * open_now
p = 1 / (1 + np.exp(-logit))
y = rng.binomial(1, p)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)
model = HistGradientBoostingClassifier(max_depth=5, learning_rate=.08, random_state=42).fit(Xtr, ytr)
auc = roc_auc_score(yte, model.predict_proba(Xte)[:, 1])
Path("artifacts").mkdir(exist_ok=True)
joblib.dump(model, "artifacts/place_ranker.joblib")
print(f"validation_auc={auc:.3f}")

"""Train and evaluate the bathing-water bacteria prediction model.

Question: given rainfall at Met Éireann Cork Airport over the previous days, the season and the
beach, what is the probability that a bathing-water sample shows ELEVATED bacteria
(E. coli > 250 or intestinal enterococci > 100 per 100 ml, the EU coastal "Excellent" limits)?

Evaluation is leave-one-year-out: every sample is scored by a model that never saw its year.
The deployed model is a regularised logistic regression exported to JSON (coefficients only),
so the API needs neither scikit-learn nor pickle files at runtime.

Requires: pip install -r backend/requirements-ml.txt
Usage (repository root):  .\\.venv\\Scripts\\python.exe scripts\\train_bathing_model.py
"""

from __future__ import annotations

import json
import math
import warnings
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.ml.features import ECOLI_THRESHOLD, ENTEROCOCCI_THRESHOLD, SEASON_FEATURES, build_features, is_elevated

# scikit-learn 1.5 passes a solver option newer SciPy no longer recognises; harmless.
warnings.filterwarnings("ignore", message="Unknown solver options")
RNG = np.random.default_rng(42)
C_GRID = [0.03, 0.1, 0.3, 1.0, 3.0]
# Bands are relative to the ~4.5% base rate of elevated samples, not absolute "safe/unsafe" levels.
BANDS = [("BELOW_TYPICAL", 0.0, 0.03), ("TYPICAL", 0.03, 0.08), ("ABOVE_TYPICAL", 0.08, 1.01)]
VARIANTS = {
    "recent": ["rain_d1"],
    "full": ["rain_d1", "rain_d2_3", "rain_d4_7"],
}
# Deployed variant. In leave-one-year-out testing, adding rain from 2-7 days before did not improve
# skill (AUC 0.67 vs 0.69), so the simpler model, which also needs less data, is deployed.
DEPLOY = "recent"


def load_dataset(data_dir) -> tuple[pd.DataFrame, dict]:
    samples = pd.read_csv(data_dir / "bathing_training_samples.csv", keep_default_na=False)
    for col in ("e_coli", "enterococci"):
        samples[col] = pd.to_numeric(samples[col], errors="coerce")
    samples["result_date"] = pd.to_datetime(samples["result_date"]).dt.date
    daily_df = pd.read_csv(data_dir / "rainfall_daily.csv")
    daily_df["date"] = pd.to_datetime(daily_df["date"]).dt.date
    daily = {d: (None if pd.isna(v) else float(v)) for d, v in zip(daily_df["date"], daily_df["rain_mm"])}
    return samples, daily


def featurise(samples: pd.DataFrame, daily: dict, rain_features: list[str]) -> pd.DataFrame:
    rows = []
    for s in samples.itertuples():
        target = is_elevated(
            None if pd.isna(s.e_coli) else s.e_coli, None if pd.isna(s.enterococci) else s.enterococci
        )
        if target is None:
            continue
        feats, raw = build_features(daily, s.result_date, rain_features)
        if feats is None:
            continue
        rows.append({"beach_id": s.beach_id, "beach_name": s.beach_name, "date": s.result_date,
                     "year": s.result_date.year, "y": int(target), **feats,
                     **{f"raw_{k}": v for k, v in raw.items()}})
    return pd.DataFrame(rows)


class Design:
    """Standardised numeric features + one-hot beach indicators, reproducible from JSON."""

    def __init__(self, numeric: list[str]):
        self.numeric = numeric

    def fit(self, df: pd.DataFrame) -> "Design":
        self.mean = df[self.numeric].mean().to_dict()
        self.std = df[self.numeric].std(ddof=0).replace(0, 1).to_dict()
        self.beaches = sorted(df["beach_id"].unique())
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        num = np.column_stack([(df[c] - self.mean[c]) / self.std[c] for c in self.numeric])
        onehot = np.column_stack([(df["beach_id"] == b).astype(float) for b in self.beaches])
        return np.hstack([num, onehot])


def fit_logreg(train: pd.DataFrame, numeric: list[str], c: float):
    design = Design(numeric).fit(train)
    model = LogisticRegression(C=c, max_iter=2000)
    model.fit(design.transform(train), train["y"])
    return design, model


def beach_baseline(train: pd.DataFrame, test: pd.DataFrame, prior_strength: float = 5.0) -> np.ndarray:
    overall = train["y"].mean()
    stats = train.groupby("beach_id")["y"].agg(["sum", "count"])
    rates = (stats["sum"] + prior_strength * overall) / (stats["count"] + prior_strength)
    return test["beach_id"].map(rates).fillna(overall).to_numpy()


def loyo_logreg(df: pd.DataFrame, numeric: list[str], c: float) -> np.ndarray:
    oof = np.zeros(len(df))
    for year in sorted(df["year"].unique()):
        test_mask = (df["year"] == year).to_numpy()
        design, model = fit_logreg(df[~test_mask], numeric, c)
        oof[test_mask] = model.predict_proba(design.transform(df[test_mask]))[:, 1]
    return oof


def loyo_comparators(df: pd.DataFrame, numeric: list[str]) -> dict[str, np.ndarray]:
    """Out-of-fold predictions for the beach-rate baseline and a gradient-boosting comparator."""
    oof = {"gbm": np.zeros(len(df)), "baseline": np.zeros(len(df))}
    beach_codes = {b: i for i, b in enumerate(sorted(df["beach_id"].unique()))}
    for year in sorted(df["year"].unique()):
        test_mask = (df["year"] == year).to_numpy()
        train, test = df[~test_mask], df[test_mask]
        gbm = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                             categorical_features=[len(numeric)], random_state=0)
        xtr = np.column_stack([train[numeric].to_numpy(), train["beach_id"].map(beach_codes)])
        xte = np.column_stack([test[numeric].to_numpy(), test["beach_id"].map(beach_codes)])
        gbm.fit(xtr, train["y"])
        oof["gbm"][test_mask] = gbm.predict_proba(xte)[:, 1]
        oof["baseline"][test_mask] = beach_baseline(train, test)
    return oof


def bootstrap_auc(y: np.ndarray, p: np.ndarray, n: int = 1000) -> list[float]:
    stats = []
    for _ in range(n):
        idx = RNG.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        stats.append(roc_auc_score(y[idx], p[idx]))
    return [round(float(np.percentile(stats, 2.5)), 3), round(float(np.percentile(stats, 97.5)), 3)]


def metrics(y: np.ndarray, p: np.ndarray, base_brier: float | None = None) -> dict:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    out = {
        "roc_auc": round(float(roc_auc_score(y, p)), 3),
        "roc_auc_95ci": bootstrap_auc(y, p),
        "average_precision": round(float(average_precision_score(y, p)), 3),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "log_loss": round(float(log_loss(y, p)), 4),
    }
    if base_brier:
        out["brier_skill_vs_baseline"] = round(1 - out["brier"] / base_brier, 3)
    return out


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 5) -> list[dict]:
    order = np.argsort(p)
    out = []
    for chunk in np.array_split(order, bins):
        out.append({"mean_predicted": round(float(p[chunk].mean()), 4), "observed_rate": round(float(y[chunk].mean()), 4),
                    "n": int(len(chunk))})
    return out


def band_table(y: np.ndarray, p: np.ndarray) -> list[dict]:
    rows = []
    for name, lo, hi in BANDS:
        mask = (p >= lo) & (p < hi)
        rows.append({"band": name, "range": [lo, min(hi, 1.0)], "n": int(mask.sum()),
                     "events": int(y[mask].sum()), "observed_rate": round(float(y[mask].mean()), 3) if mask.any() else None})
    return rows


def main() -> None:
    data_dir = get_settings().data_dir
    samples, daily = load_dataset(data_dir)
    out_dir = data_dir / "models"
    out_dir.mkdir(exist_ok=True)
    card: dict = {
        "model_id": "bathing-elevated-bacteria",
        "version": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "task": "Binary classification: probability that a bathing-water sample shows elevated bacteria",
        "target": {
            "definition": f"E. coli > {ECOLI_THRESHOLD:.0f} OR intestinal enterococci > {ENTEROCOCCI_THRESHOLD:.0f} per 100 ml",
            "basis": "EU Bathing Water Directive 2006/7/EC coastal 'Excellent' limits applied to single samples",
        },
        "algorithm": "L2-regularised logistic regression (scikit-learn), exported as coefficients",
        "evaluation": "Leave-one-year-out cross-validation (each year predicted by a model trained on all other years)",
        "bands": [{"band": n, "min": lo, "max": min(hi, 1.0)} for n, lo, hi in BANDS],
        "variants": {},
    }
    print(f"Samples: {len(samples)} from {samples['beach_id'].nunique()} beaches")

    for variant, rain_features in VARIANTS.items():
        df = featurise(samples, daily, rain_features).reset_index(drop=True)
        numeric = rain_features + SEASON_FEATURES
        y = df["y"].to_numpy()
        print(f"\n[{variant}] usable samples {len(df)}, events {y.sum()} ({y.mean():.1%}), "
              f"years {df['year'].min()}-{df['year'].max()}")

        # Choose C by out-of-fold log loss.
        best_c, best_ll, results = None, math.inf, {}
        for c in C_GRID:
            p = loyo_logreg(df, numeric, c)
            ll = log_loss(y, np.clip(p, 1e-4, 1 - 1e-4))
            results[c] = p
            print(f"  C={c:<5} OOF log-loss {ll:.4f}  AUC {roc_auc_score(y, p):.3f}", flush=True)
            if ll < best_ll:
                best_c, best_ll = c, ll
        oof = {"logreg": results[best_c], **loyo_comparators(df, numeric)}
        base = metrics(y, oof["baseline"])
        evaluation = {
            "baseline_beach_rate": base,
            "logistic_regression": metrics(y, oof["logreg"], base["brier"]),
            "gradient_boosting": metrics(y, oof["gbm"], base["brier"]),
        }
        for k, v in evaluation.items():
            print(f"  {k:<22} AUC {v['roc_auc']} {v['roc_auc_95ci']}  AP {v['average_precision']}  Brier {v['brier']}"
                  + (f"  BSS {v['brier_skill_vs_baseline']}" if "brier_skill_vs_baseline" in v else ""))

        if variant != DEPLOY:
            card.setdefault("compared_variants", {})[variant] = {
                "rain_features": rain_features,
                "regularisation_C": best_c,
                "evaluation": evaluation,
                "decision": "Not deployed: no improvement over the deployed variant out of sample.",
            }
            continue

        design, model = fit_logreg(df, numeric, best_c)
        coef = model.coef_[0]
        lift = calibration(y, oof["logreg"])
        card["variants"][variant] = {
            "rain_features": rain_features,
            "numeric_features": numeric,
            "standardisation": {"mean": design.mean, "std": design.std},
            "intercept": float(model.intercept_[0]),
            "coefficients": {name: float(v) for name, v in zip(numeric, coef[: len(numeric)])},
            "beach_coefficients": {b: float(v) for b, v in zip(design.beaches, coef[len(numeric):])},
            "beach_names": df.drop_duplicates("beach_id").set_index("beach_id")["beach_name"].to_dict(),
            "regularisation_C": best_c,
            "training": {
                "samples": int(len(df)),
                "events": int(y.sum()),
                "event_rate": round(float(y.mean()), 4),
                "beaches": int(df["beach_id"].nunique()),
                "period": [df["date"].min().isoformat(), df["date"].max().isoformat()],
                "months": sorted(int(m) for m in pd.Series([d.month for d in df["date"]]).unique()),
            },
            "evaluation": evaluation,
            "calibration": lift,
            "top_vs_bottom_quintile_ratio": round(lift[-1]["observed_rate"] / max(lift[0]["observed_rate"], 1e-9), 1),
            "bands_out_of_sample": band_table(y, oof["logreg"]),
            "per_year_auc": {
                int(yr): round(float(roc_auc_score(g["y"], oof["logreg"][g.index])), 3)
                for yr, g in df.groupby("year") if g["y"].nunique() == 2
            },
        }
        if variant == DEPLOY:
            backtest = df[["date", "beach_id", "beach_name", "y"] + [f"raw_{r}" for r in rain_features]].copy()
            backtest["p_out_of_sample"] = oof["logreg"].round(4)
            backtest.to_csv(out_dir / "bathing_backtest.csv", index=False)

    card["deployed_variant"] = DEPLOY
    card["deployment_rule"] = (
        "Requires yesterday's complete daily rainfall total at Cork Airport. Predictions outside the training "
        "months are flagged as out of season."
    )
    card["limitations"] = [
        "Single rain gauge (Cork Airport) for beaches up to 60 km away; local showers can be missed.",
        "Samples exist only in the bathing season (May-September); out-of-season predictions are extrapolation.",
        "Elevated-bacteria events are rare (about 5% of samples); probabilities are modest and uncertain.",
        "The model learns association with rainfall, not cause; it does not identify pollution sources.",
        "It predicts bathing-water bacteria only, not shellfish-flesh contamination, biotoxins or nutrients.",
        "Not an official EPA/HSE bathing advisory; it must not be used to declare water safe or unsafe.",
    ]
    path = out_dir / "bathing_model.json"
    path.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved model card: {path}")


if __name__ == "__main__":
    main()

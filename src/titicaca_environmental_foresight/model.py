"""Modelado Tier-2: calibración chl-a ~ NDCI (proxy óptico).

Regresión OLS simple (numpy, sin sklearn/scipy) entre la clorofila-a in-situ y el NDCI
satelital muestreado por estación (`tier2/sentinel2.py`). Se reportan AMBAS formas
(lineal y log10) y, dado que solo hay 2 campañas con chl-a in-situ (2018-II, 2019-II),
un holdout *leave-one-campaign-out* como señal indicativa.

Honestidad metodológica (CLAUDE.md / DECISION-005, DECISION-007): chl-a satelital es un
PROXY inferido, no una medición; con 2 fechas y las mismas estaciones no se puede separar
temporal Y espacialmente, así que el holdout arrastra leakage por colocación — se DOCUMENTA
como limitación, no se finge una validación limpia.
"""

from __future__ import annotations

import numpy as np
import polars as pl

CAVEATS = [
    "Calibración con 2 campañas (2018-II, 2019-II): es un AJUSTE, no un modelo validado.",
    "Mismas estaciones en ambas campañas → el holdout temporal comparte ubicaciones "
    "(leakage por colocación). Con 2 fechas no hay separación temporal y espacial "
    "simultánea; limitación documentada (DECISION-007), no resuelta.",
    "NDCI satura a alta biomasa; la relación con chl-a no es lineal.",
    "chl-a satelital es un PROXY óptico inferido, no medición de laboratorio (DECISION-005).",
]


def fit_ols(x, y) -> dict:
    """OLS de grado 1 (y = slope·x + intercept). Métricas in-sample.

    Devuelve `{n, slope, intercept, r2, rmse}`; slope/intercept/r2 = None si no hay
    varianza en x o n<2 (no se inventa un ajuste).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = int(x.size)
    if n < 2 or np.ptp(x) == 0:
        return {"n": n, "slope": None, "intercept": None, "r2": None, "rmse": None}
    slope, intercept = (float(v) for v in np.polyfit(x, y, 1))
    pred = slope * x + intercept
    rmse = float(np.sqrt(np.mean((y - pred) ** 2)))
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "n": n,
        "slope": round(slope, 4),
        "intercept": round(intercept, 4),
        "r2": round(r2, 4) if r2 is not None else None,
        "rmse": round(rmse, 4),
    }


def _test_metrics(fit: dict, x_test, y_test) -> dict:
    """Aplica un ajuste (slope/intercept) a un set de test y reporta n, r2, rmse."""
    x_test = np.asarray(x_test, dtype=float)
    y_test = np.asarray(y_test, dtype=float)
    n = int(x_test.size)
    if fit["slope"] is None or n == 0:
        return {"n": n, "r2": None, "rmse": None}
    pred = fit["slope"] * x_test + fit["intercept"]
    rmse = float(np.sqrt(np.mean((y_test - pred) ** 2)))
    ss_res = float(np.sum((y_test - pred) ** 2))
    ss_tot = float(np.sum((y_test - y_test.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {"n": n, "r2": round(r2, 4) if r2 is not None else None, "rmse": round(rmse, 4)}


def _report_for(x, y, campaigns) -> dict:
    """Calibración full-data + holdout leave-one-campaign-out (train 1 campaña → test resto)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    campaigns = np.asarray(campaigns, dtype=object)
    calibration = fit_ols(x, y)
    holdout: dict = {}
    uniq = sorted({str(c) for c in campaigns})
    if len(uniq) >= 2:
        for train_c in uniq:
            tr = campaigns == train_c
            te = ~tr
            fit = fit_ols(x[tr], y[tr])
            # test = complemento (las demás campañas); con 2 fechas es la otra campaña.
            holdout[f"train_{train_c}"] = _test_metrics(fit, x[te], y[te])
    return {"calibration": calibration, "holdout_loco": holdout}


def regression_report(matchup_df: pl.DataFrame) -> dict:
    """chl-a ~ NDCI sobre las filas con ambos valores. Reporta lineal y log10.

    `matchup_df` necesita columnas `chl_a_ug_l`, `ndci`, `campaign`. El bloque `log10`
    usa solo chl_a > 0 (el log de ≤0 no existe; no se imputa).
    """
    valid = matchup_df.filter(
        pl.col("ndci").is_not_null() & pl.col("chl_a_ug_l").is_not_null()
    )
    ndci = valid["ndci"].to_numpy()
    chl = valid["chl_a_ug_l"].to_numpy()
    camp = valid["campaign"].to_list()

    linear = _report_for(ndci, chl, camp)

    pos = chl > 0
    log10 = _report_for(ndci[pos], np.log10(chl[pos]), [c for c, p in zip(camp, pos) if p])

    return {
        "n_matchup": int(valid.height),
        "target_note": "x = NDCI (proxy); y = chl_a_ug_l (in-situ).",
        "linear": linear,
        "log10": log10,
        "caveats": CAVEATS,
    }

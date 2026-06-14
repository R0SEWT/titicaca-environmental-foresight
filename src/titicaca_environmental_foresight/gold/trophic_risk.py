"""Tier-1: riesgo trófico del lago desde el panel silver ana_observatorio.

Métrica: índice de estado trófico de Carlson (TSI) sobre clorofila-a y
transparencia (Secchi), escalado por hipoxia (OD bajo el ECA) y acompañado de
flags de excedencia ECA-Agua. El TSI es una INFERENCIA de estado trófico, no una
medición directa de "riesgo".

Funciones puras (tsi_*, classify, eca_exceed, escalate) separadas de la
construcción/IO para testear en CI sin datos.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import polars as pl

ROOT = Path(__file__).parents[3]
OUT_PATH = ROOT / "outputs" / "trophic_risk.json"

# Parámetros que el modelo consume del panel silver.
_USED_PARAMS = ["chlorophyll_a", "secchi_m", "do_mg_l", "total_phosphorus", "total_nitrogen"]

# Dirección del límite ECA por parámetro canónico: "max" (excede si value > X) o
# "min" (incumple si value < X). Solo se evalúan parámetros con dirección conocida.
ECA_DIRECTION = {
    "chlorophyll_a": "max",
    "total_phosphorus": "max",
    "total_nitrogen": "max",
    "do_mg_l": "min",
}

RISK_ORDER = ["bajo", "medio", "alto"]


def tsi_chl(chl_ug_l: float | None) -> float | None:
    """TSI de Carlson por clorofila-a (µg/L). None si no positivo/ausente."""
    if chl_ug_l is None or chl_ug_l <= 0:
        return None
    return 9.81 * math.log(chl_ug_l) + 30.6


def tsi_sd(secchi_m: float | None) -> float | None:
    """TSI de Carlson por transparencia Secchi (m). None si no positivo/ausente."""
    if secchi_m is None or secchi_m <= 0:
        return None
    return 60 - 14.41 * math.log(secchi_m)


def combine_tsi(t_chl: float | None, t_sd: float | None) -> float | None:
    """Media de los TSI disponibles; None si ninguno."""
    vals = [v for v in (t_chl, t_sd) if v is not None]
    return sum(vals) / len(vals) if vals else None


def classify(tsi: float | None) -> tuple[str | None, str | None]:
    """TSI → (trophic_state, risk_level). oligo<40=bajo, meso<50=medio, eu/hiper>=50=alto."""
    if tsi is None:
        return (None, None)
    if tsi < 40:
        return ("oligotrophic", "bajo")
    if tsi < 50:
        return ("mesotrophic", "medio")
    if tsi < 70:
        return ("eutrophic", "alto")
    return ("hypereutrophic", "alto")


def _threshold_number(threshold: str | None) -> float | None:
    if threshold is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(threshold))
    return float(m.group().replace(",", ".")) if m else None


def eca_exceed(parameter: str, value: float | None, threshold: str | None) -> bool | None:
    """¿`value` incumple el ECA del parámetro? None si no evaluable.

    Dirección por ECA_DIRECTION: "max" → incumple si value > límite; "min" → si value < límite.
    """
    direction = ECA_DIRECTION.get(parameter)
    limit = _threshold_number(threshold)
    if direction is None or limit is None or value is None:
        return None
    return value > limit if direction == "max" else value < limit


def escalate(risk_level: str, *, hypoxia: bool) -> str:
    """Sube un nivel de riesgo si hay hipoxia (tope 'alto')."""
    if not hypoxia:
        return risk_level
    i = RISK_ORDER.index(risk_level)
    return RISK_ORDER[min(i + 1, len(RISK_ORDER) - 1)]


def _worst(levels: list[str | None]) -> str | None:
    idx = [RISK_ORDER.index(lvl) for lvl in levels if lvl in RISK_ORDER]
    return RISK_ORDER[max(idx)] if idx else None


def build_trophic_risk(silver_df: pl.DataFrame) -> dict:
    """Panel silver long → dict de riesgo trófico (records por estación×campaña + rollup).

    Dedup por (station_id, datetime, parameter); agrupa por registro; calcula TSI,
    flags ECA e hipoxia; clasifica y escala. lat/lon no se incluyen (pendientes).
    """
    df = (
        silver_df.filter(pl.col("parameter").is_in(_USED_PARAMS))
        .unique(subset=["station_id", "datetime", "parameter"], keep="first")
        .sort("station_id", "datetime", "parameter")
    )

    # Agrupa por registro: {(station, datetime, water_body, campaign): {param: (value, threshold)}}
    groups: dict[tuple, dict] = {}
    for row in df.iter_rows(named=True):
        key = (row["station_id"], row["datetime"], row["water_body"], row["campaign"])
        groups.setdefault(key, {})[row["parameter"]] = (row["value"], row["eca_threshold"])

    records = []
    for (station_id, datetime_, water_body, campaign), params in groups.items():
        chl_mg = params.get("chlorophyll_a", (None, None))[0]
        chl_ug = chl_mg * 1000 if chl_mg is not None else None
        secchi = params.get("secchi_m", (None, None))[0]
        do_val, do_thr = params.get("do_mg_l", (None, None))

        t_chl, t_sd = tsi_chl(chl_ug), tsi_sd(secchi)
        tsi = combine_tsi(t_chl, t_sd)
        trophic_state, base_risk = classify(tsi)

        hypoxia = eca_exceed("do_mg_l", do_val, do_thr) is True
        risk_level = escalate(base_risk, hypoxia=hypoxia) if base_risk is not None else None

        exceedances = sorted(
            p for p, (val, thr) in params.items() if eca_exceed(p, val, thr) is True
        )

        records.append({
            "station_id": station_id,
            "water_body": water_body,
            "campaign": campaign,
            "datetime": datetime_.isoformat() if datetime_ is not None else None,
            "chl_a_ug_l": round(chl_ug, 3) if chl_ug is not None else None,
            "secchi_m": secchi,
            "do_mg_l": do_val,
            "tsi_chl": round(t_chl, 1) if t_chl is not None else None,
            "tsi_sd": round(t_sd, 1) if t_sd is not None else None,
            "tsi": round(tsi, 1) if tsi is not None else None,
            "trophic_state": trophic_state,
            "base_risk": base_risk,
            "hypoxia": hypoxia,
            "eca_exceedances": exceedances,
            "risk_level": risk_level,
        })

    records.sort(key=lambda r: (r["station_id"], r["campaign"]))

    # Rollup por estación: peor caso del risk_level entre campañas.
    summary = []
    for station_id in sorted({r["station_id"] for r in records}):
        sr = [r for r in records if r["station_id"] == station_id]
        tsis = [r["tsi"] for r in sr if r["tsi"] is not None]
        summary.append({
            "station_id": station_id,
            "water_body": sr[0]["water_body"],
            "n_campaigns": len(sr),
            "risk_level": _worst([r["risk_level"] for r in sr]),
            "tsi_max": max(tsis) if tsis else None,
            "hypoxia_any": any(r["hypoxia"] for r in sr),
            "eca_exceed_any": any(r["eca_exceedances"] for r in sr),
        })

    return {
        "meta": {
            "method": "Carlson TSI (clorofila-a, Secchi) + escalado por hipoxia (OD<ECA) + flags ECA-Agua",
            "n_stations": len(summary),
            "n_records": len(records),
            "campaigns": sorted({r["campaign"] for r in records}),
            "caveats": [
                "TSI es una inferencia de estado trófico, no una medición de 'riesgo'.",
                "Umbral de OD = ECA-Agua Cat.4-E1 (referencia legal); el lago a ~3810 m tiene saturación de OD reducida.",
                "Clorofila-a solo disponible en campañas 2018-II/2019-II.",
                "Sin coordenadas: resultado por estación/cuerpo de agua, no mapa geográfico.",
                "Ríos (Cat.3) sin clorofila-a quedan fuera del TSI.",
            ],
        },
        "records": records,
        "station_summary": summary,
    }


def main() -> None:
    from titicaca_environmental_foresight.silver import ana_observatorio as ao

    silver = ao.build_silver(out_path=None)
    out = build_trophic_risk(silver)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    by_risk: dict[str | None, int] = {}
    for s in out["station_summary"]:
        by_risk[s["risk_level"]] = by_risk.get(s["risk_level"], 0) + 1
    print(f"\n{'='*60}\n  Tier-1 riesgo trófico → {OUT_PATH.name}\n{'='*60}")
    print(f"  registros (estación×campaña): {out['meta']['n_records']}")
    print(f"  estaciones:                   {out['meta']['n_stations']}")
    print(f"  campañas:                     {', '.join(out['meta']['campaigns'])}")
    print(f"  riesgo por estación:          {by_risk}")
    print(f"\n  escrito en {OUT_PATH}\n")


if __name__ == "__main__":
    main()

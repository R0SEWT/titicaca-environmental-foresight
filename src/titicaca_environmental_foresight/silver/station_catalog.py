"""Catálogo consolidado de coordenadas de estaciones (multi-fuente, con evidencia).

Extiende la extracción del protocolo binacional (bead drt → LTit01-73) con las fuentes
que cubren la red expandida (bead dij): el IT ANA de la UH Coata (LTiti74-77, RCoat) y la
RED MONITOREO (ríos RDesa/RCoat). Produce UNA tabla versionada por estación con columnas
de evidencia y un `status` ∈ {resolved, ambiguous, missing}.

Principios (no negociables):
- NO se infieren ni inventan coordenadas. Estación sin fuente en disco → `missing`.
- Coordenadas incompatibles entre fuentes (> UMBRAL) → `ambiguous` (se reporta, no se elige).
- Se conserva la evidencia: texto original, archivo fuente, método y datum.

Las funciones de parseo/consolidación son puras (testeadas en CI); la lectura de PDF/xlsx
es IO. Reutiliza utm19s_to_wgs84 / _canon_station_id de `station_coords`.
"""

from __future__ import annotations

import re

import polars as pl

from titicaca_environmental_foresight.silver import station_coords as sc

ROOT = sc.ROOT
SILVER_PATH = sc.SILVER_PATH
CATALOG_CSV = ROOT / "data" / "sources" / "station_coords_catalog.csv"

COATA_PDF = (
    ROOT / "data" / "bronze" / "data_limpia" / "Data limpia "
    / "Estado de la calidad del agua"
    / "84172-2021_IT N° 085-2021-ANA.AAA.TIT-RWAA_MON UH COATA MAYO 2021.pdf"
)
RED_MONITOREO_XLS = (
    ROOT / "data" / "bronze" / "data_limpia" / "Data limpia "
    / "Data para herramienta" / "RED MONITOREO UNIDADES HIDROGRAFICAS - TITICACA_.xls"
)

# Bounding box razonable de la cuenca del Titicaca (lado PE), para validar resultados.
BBOX_LAT = (-17.5, -14.8)
BBOX_LON = (-70.6, -68.4)
# Dos fuentes que difieren más que esto (metros, en UTM) → ambiguo, no se elige.
AMBIG_THRESHOLD_M = 300.0

CATALOG_SCHEMA: dict[str, pl.DataType] = {
    "station_id": pl.String,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "utm_este": pl.Int64,
    "utm_norte": pl.Int64,
    "datum": pl.String,
    "water_body": pl.String,
    "coord_original_text": pl.String,
    "coord_source": pl.String,
    "coord_source_file": pl.String,
    "extraction_method": pl.String,
    "confidence": pl.String,
    "status": pl.String,
    "notes": pl.String,
}

# Prioridad de fuente cuando varias son consistentes (el protocolo define la red del lago).
_SOURCE_PRIORITY = ["protocolo_binacional", "coata_it_2021", "red_monitoreo"]


# --------------------------------------------------------------------------- #
# Parseo (puro)                                                               #
# --------------------------------------------------------------------------- #
def _despace_int(token: str) -> int | None:
    """'8 275 843' / '8\xa0275 843' → 8275843; None si no es entero con separadores de millar.

    Quita TODO whitespace, incluido el no-separable (\xa0) que usan las tablas ANA.
    """
    t = re.sub(r"\s", "", token)
    return int(t) if t.isdigit() else None


_COATA_CODE = re.compile(r"^(LTiti\d+|RCoat\d+|RDesa\d+)\b")


def parse_coata_points(text: str) -> list[dict]:
    """Tabla de puntos del IT Coata → filas {station_id, utm_este, utm_norte, coord_original_text}.

    Layout `pdftotext -layout`: `código  ...  Este  Norte  Altitud  Cat.X`, con números que
    traen espacios de millar (`402 395`). Toma los 3 numéricos antes de `Cat`; ignora prosa
    (líneas que empiezan con código pero sin tabla de coordenadas válida).
    """
    rows = []
    for line in text.splitlines():
        s = line.strip()
        m = _COATA_CODE.match(s)
        if not m:
            continue
        fields = re.split(r"\s{2,}", s)
        cat_idx = next((i for i, f in enumerate(fields) if f.startswith("Cat")), None)
        if cat_idx is None or cat_idx < 3:
            continue
        este = _despace_int(fields[cat_idx - 3])
        norte = _despace_int(fields[cat_idx - 2])
        if este is None or norte is None:
            continue
        if not (100_000 <= este <= 999_999 and 7_000_000 <= norte <= 9_999_999):
            continue
        rows.append({
            "station_id": sc._canon_station_id(m.group(1)),
            "utm_este": este,
            "utm_norte": norte,
            "coord_original_text": f"{fields[cat_idx - 3]} {fields[cat_idx - 2]} (UTM 19S)",
        })
    return rows


# --------------------------------------------------------------------------- #
# Consolidación + validación (puro)                                           #
# --------------------------------------------------------------------------- #
def in_titicaca_bbox(lat: float, lon: float) -> bool:
    """¿(lat, lon) cae en el bounding box razonable de la cuenca del Titicaca?"""
    return BBOX_LAT[0] <= lat <= BBOX_LAT[1] and BBOX_LON[0] <= lon <= BBOX_LON[1]


def consolidate(station_ids: list[str], sources: dict[str, dict]) -> list[dict]:
    """Une las fuentes por estación y asigna status.

    `sources`: {nombre_fuente: {station_id: {utm_este, utm_norte, water_body,
    coord_original_text, coord_source_file, extraction_method, confidence}}}.

    - Sin fuente → status=missing (lat/lon null).
    - Varias fuentes incompatibles (> AMBIG_THRESHOLD_M en UTM) → status=ambiguous.
    - Si no, status=resolved con la fuente de mayor prioridad; UTM 19S → WGS84.
    """
    rows = []
    for sid in station_ids:
        hits = [(name, sources[name][sid]) for name in _SOURCE_PRIORITY
                if name in sources and sid in sources[name]]
        if not hits:
            rows.append(_row_missing(sid))
        elif _is_ambiguous([h[1] for h in hits]):
            rows.append(_row_ambiguous(sid, hits))  # no se elige una coord
        else:
            rows.append(_row_resolved(sid, hits))
    return rows


def _row_resolved(sid: str, hits: list[tuple[str, dict]]) -> dict:
    name, rec = hits[0]  # mayor prioridad
    lat, lon = sc.utm19s_to_wgs84(rec["utm_este"], rec["utm_norte"])
    agree = " | ".join(sorted({h[0] for h in hits}))
    return {
        "station_id": sid,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "utm_este": rec["utm_este"],
        "utm_norte": rec["utm_norte"],
        "datum": "UTM 19S (EPSG:32719) → WGS84",
        "water_body": rec.get("water_body"),
        "coord_original_text": rec.get("coord_original_text"),
        "coord_source": name,
        "coord_source_file": rec.get("coord_source_file"),
        "extraction_method": rec.get("extraction_method"),
        "confidence": "high" if len(hits) > 1 else rec.get("confidence", "medium"),
        "status": "resolved",
        "notes": f"consistente en {agree}" if len(hits) > 1 else None,
    }


def _row_ambiguous(sid: str, hits: list[tuple[str, dict]]) -> dict:
    """Fuentes en conflicto: NO se elige coord (lat/lon/utm null); se reporta la evidencia."""
    detail = "; ".join(f"{name}: {r['utm_este']},{r['utm_norte']}" for name, r in hits)
    return {
        "station_id": sid, "lat": None, "lon": None, "utm_este": None, "utm_norte": None,
        "datum": None, "water_body": None, "coord_original_text": None,
        "coord_source": " | ".join(sorted({h[0] for h in hits})),
        "coord_source_file": None, "extraction_method": None, "confidence": "low",
        "status": "ambiguous",
        "notes": f"coords incompatibles entre fuentes (no se elige): {detail}",
    }


def _is_ambiguous(recs: list[dict]) -> bool:
    """¿Las coords UTM de las fuentes difieren más que el umbral entre sí?"""
    pts = [(r["utm_este"], r["utm_norte"]) for r in recs]
    return any(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 > AMBIG_THRESHOLD_M
        for i, a in enumerate(pts) for b in pts[i + 1:]
    )


def _row_missing(sid: str) -> dict:
    return {
        "station_id": sid, "lat": None, "lon": None, "utm_este": None, "utm_norte": None,
        "datum": None, "water_body": None, "coord_original_text": None,
        "coord_source": None, "coord_source_file": None, "extraction_method": None,
        "confidence": None, "status": "missing",
        "notes": "sin coordenada en fuentes en disco; requiere SNIRH/partner (red expandida)",
    }


def status_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


# --------------------------------------------------------------------------- #
# IO + build                                                                  #
# --------------------------------------------------------------------------- #
def _protocol_source() -> dict:
    """{station_id: rec} desde el protocolo binacional (reusa station_coords)."""
    df = sc.coords_dataframe(sc.extract_pdf_text(sc.PROTOCOL_PDF))
    return {
        r["station_id"]: {
            "utm_este": r["utm_este"], "utm_norte": r["utm_norte"],
            "water_body": r["water_body_proto"],
            "coord_original_text": f"{r['utm_este']} {r['utm_norte']} (UTM 19S)",
            "coord_source_file": sc.PROTOCOL_PDF.name,
            "extraction_method": "pdftotext_table", "confidence": "high",
        }
        for r in df.iter_rows(named=True)
    }


def _coata_source() -> dict:
    out = {}
    for r in parse_coata_points(sc.extract_pdf_text(COATA_PDF)):
        out[r["station_id"]] = {
            "utm_este": r["utm_este"], "utm_norte": r["utm_norte"], "water_body": None,
            "coord_original_text": r["coord_original_text"],
            "coord_source_file": COATA_PDF.name,
            "extraction_method": "pdftotext_table", "confidence": "high",
        }
    return out


def _red_monitoreo_source() -> dict:
    """Ríos (RDesa/RCoat) desde RED MONITOREO; Este/Norte traen espacios de millar."""
    d = pl.read_excel(RED_MONITOREO_XLS, sheet_id=1)
    out = {}
    for row in d.iter_rows(named=True):
        code = str(row.get("Código Final") or "").strip()
        if not re.match(r"^(RDesa|RCoat|RIla|RSuch|RHuan)\d+$", code):
            continue
        este = _despace_int(str(row.get("Este") or ""))
        norte = _despace_int(str(row.get("Norte ") or ""))
        if este is None or norte is None:
            continue
        out[code] = {
            "utm_este": este, "utm_norte": norte, "water_body": str(row.get("Nombre del Recurso Hídrico") or "") or None,
            "coord_original_text": f"{row.get('Este')} {row.get('Norte ')} (UTM 19S)",
            "coord_source_file": RED_MONITOREO_XLS.name,
            "extraction_method": "xlsx_table", "confidence": "medium",
        }
    return out


def build_catalog(station_ids: list[str]) -> pl.DataFrame:
    sources = {
        "protocolo_binacional": _protocol_source(),
        "coata_it_2021": _coata_source(),
        "red_monitoreo": _red_monitoreo_source(),
    }
    rows = consolidate(sorted(station_ids), sources)
    return pl.DataFrame(rows, schema=CATALOG_SCHEMA)


def main() -> None:
    if not SILVER_PATH.exists():
        raise SystemExit(
            f"No existe el panel silver ({SILVER_PATH}). Corre primero "
            "python -m titicaca_environmental_foresight.silver.ana_observatorio"
        )
    silver = pl.read_parquet(SILVER_PATH)
    station_ids = silver["station_id"].unique().to_list()
    catalog = build_catalog(station_ids)

    # Validaciones (fallan ruidosamente: el catálogo no debe contener coords absurdas).
    resolved = catalog.filter(pl.col("status") == "resolved")
    bad_bbox = resolved.filter(
        ~pl.struct("lat", "lon").map_elements(
            lambda s: in_titicaca_bbox(s["lat"], s["lon"]), return_dtype=pl.Boolean
        )
    )
    if bad_bbox.height:
        raise SystemExit(f"Coords fuera del bbox del Titicaca:\n{bad_bbox.select('station_id','lat','lon')}")
    dup = (resolved.group_by("lat", "lon").len().filter(pl.col("len") > 1))
    if dup.height:
        print(f"  ⚠ coords duplicadas en {dup.height} grupos (revisar)")

    CATALOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_csv(CATALOG_CSV)

    counts = status_counts(catalog.to_dicts())
    chl = set(silver.filter(
        (pl.col("parameter") == "chlorophyll_a") & pl.col("value").is_not_null()
    )["station_id"])
    chl_resolved = catalog.filter(
        pl.col("station_id").is_in(list(chl)) & (pl.col("status") == "resolved")
    ).height
    print(f"\n{'='*60}\n  station_catalog → {CATALOG_CSV.name}\n{'='*60}")
    print(f"  estaciones:        {catalog.height}")
    print(f"  status:            {counts}")
    print(f"  chl-a resueltas:   {chl_resolved}/{len(chl)}")
    by_src = catalog.filter(pl.col("coord_source").is_not_null()).group_by("coord_source").len()
    print(f"  por fuente:        {dict(by_src.iter_rows())}")
    print(f"\n  escrito en {CATALOG_CSV.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()

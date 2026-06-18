"""Limnología in-situ del lago (PEBLT/IMARPE + ANA binacional) → panel silver long.

Las tablas fuente viven en PDFs **escaneados sin capa de texto** (ver DECISION-009):
cruceros hidroquímicos y monitoreos de bahía con resultados por estación. No hay forma
fiable de parsearlos con `pdftotext`/pdfplumber (0 chars) ni con OCR limpio a la calidad
de escaneo disponible, así que la extracción es **transcripción asistida por visión** a
CSV versionados (`data/sources/limnology_insitu/<vintage>.csv`), uno por campaña×informe.

Este módulo NO parsea PDFs: carga esos CSV transcritos (formato wide, una fila por
estación, columnas de parámetro ya en nombre canónico del master schema), los funde a
long y los lleva al master schema, igual que `ana_observatorio`. Las coordenadas se
transcriben como UTM 19S y se convierten a WGS84 reutilizando `station_coords`; un gate
de plausibilidad (bbox del lago) marca lat/lon fuera de rango como sospechosa.

El artefacto reproducible es el **CSV transcrito + este loader** (no un parser de PDF).
Cada valor lleva `qa_flag`: `ok` (celda nítida) / `uncertain` (dígito ambiguo en el
escaneo) / `not_measured` (vacío). Las celdas `uncertain` se dejan en null para no
publicar números que no se pueden leer con confianza; quedan trazadas para una segunda
lectura. Las funciones puras (fundido, plausibilidad, tipado) se testean en CI sin disco.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from titicaca_environmental_foresight.silver.station_coords import utm19s_to_wgs84

ROOT = Path(__file__).parents[3]
VINTAGE_DIR = ROOT / "data" / "sources" / "limnology_insitu"
OUT_PATH = ROOT / "data" / "silver" / "limnology_insitu.parquet"

# Columnas de parámetro admitidas en el CSV wide → ya en nombre canónico del master
# schema (mismas etiquetas que produce ana_observatorio.canon, para unir ambos paneles).
PARAM_UNITS: dict[str, str] = {
    # campo / fisicoquímicos
    "secchi_m": "m",
    "water_temp_c": "°C",
    "ph": "pH",
    "do_mg_l": "mg/L",
    "conductivity_us_cm": "µS/cm",
    "bod5_mg_l": "mg/L",
    "cod_mg_l": "mg/L",
    "tss_mg_l": "mg/L",
    # nutrientes
    "phosphate_mg_l": "mg/L",
    "total_phosphorus": "mg/L",
    "ammonia_n": "mg/L",
    "total_nitrogen": "mg/L",
    # biológico (clorofila reportada en mg/m³ ≡ µg/L; ver README/DECISION-010)
    "chlorophyll_a": "µg/L",
    # metales (mismas etiquetas canónicas que ana_observatorio.CANON donde existen)
    "aluminum": "mg/L",
    "antimony": "mg/L",
    "arsenic": "mg/L",
    "barium": "mg/L",
    "beryllium": "mg/L",
    "boron": "mg/L",
    "cadmium": "mg/L",
    "calcium": "mg/L",
    "cobalt": "mg/L",
    "copper": "mg/L",
    "chromium_total": "mg/L",
    "iron": "mg/L",
    "lithium": "mg/L",
    "magnesium": "mg/L",
    "manganese": "mg/L",
    "mercury": "mg/L",
    "nickel": "mg/L",
    "silver": "mg/L",
    "lead": "mg/L",
    "selenium": "mg/L",
    "sodium": "mg/L",
    "thallium": "mg/L",
    "uranium": "mg/L",
    "vanadium": "mg/L",
    "zinc": "mg/L",
}

# Metadata por estación (no son parámetros); el resto de columnas se funden a long.
META_COLS = (
    "station_id",
    "station_name",
    "utm_este",
    "utm_norte",
    "monitoring_date",
    "monitoring_time",
)

# Bounding box del lago Titicaca (mismo criterio que el test de station_coords).
LAKE_LAT = (-16.7, -15.0)
LAKE_LON = (-70.3, -68.5)

# Esquema final del panel (master schema primero; luego parámetro/trazabilidad), alineado
# con ana_observatorio para permitir un union/concat directo de ambos silver.
SILVER_SCHEMA: dict[str, pl.DataType] = {
    "station_id": pl.String,
    "datetime": pl.Datetime,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "depth_m": pl.Float64,
    "qa_flag": pl.String,
    "sampling_agency": pl.String,
    "campaign": pl.String,
    "station_name": pl.String,
    "parameter": pl.String,
    "unit": pl.String,
    "value": pl.Float64,
    "detection_limit": pl.Float64,
    "censored": pl.Boolean,
    "source_file": pl.String,
    "source_page": pl.String,
}
_MASTER_FIRST = list(SILVER_SCHEMA)[:7]


def coords_plausible(lat: float | None, lon: float | None) -> bool:
    """True si (lat, lon) cae dentro del bbox del lago Titicaca."""
    if lat is None or lon is None:
        return False
    return LAKE_LAT[0] < lat < LAKE_LAT[1] and LAKE_LON[0] < lon < LAKE_LON[1]


def _coord_to_float(raw: object) -> float | None:
    """Celda UTM transcrita → float, o None si no parsea (vacío, guion, no-numérico)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if s == "" or set(s) <= {"-"}:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def station_latlon(utm_este: object, utm_norte: object) -> tuple[float | None, float | None, str]:
    """UTM 19S transcrito → (lat, lon, qa). qa: ok / off_lake / no_coords.

    Las celdas UTM llegan transcritas (pueden ser str, traer coma decimal o venir vacías);
    se castean a número antes del transform porque `utm19s_to_wgs84` exige floats. Si no
    parsean → `no_coords`, sin romper el resto del registro.

    No descarta la coord fuera de bbox (puede ser un error de un dígito); la devuelve
    igual pero la marca `off_lake` para revisión, sin contaminar el resto del registro.
    """
    este = _coord_to_float(utm_este)
    norte = _coord_to_float(utm_norte)
    if este is None or norte is None:
        return (None, None, "no_coords")
    lat, lon = utm19s_to_wgs84(este, norte)
    lat, lon = round(lat, 6), round(lon, 6)
    return (lat, lon, "ok" if coords_plausible(lat, lon) else "off_lake")


def _parse_cell(raw: object) -> tuple[float | None, str, float | None, bool]:
    """Celda de parámetro transcrita → (value, qa_flag, detection_limit, censored).

    - número                 → (value, "ok", None, False)
    - "<X" (bajo detección)  → (None, "censored", X, True)  no detectado al LD reportado
    - "?"/sufijo "?"/"~"     → (None, "uncertain", None, False)  dígito ambiguo en el escaneo
    - ""/None/"-"/"R.N.D."   → (None, "not_measured", None, False)
    Las celdas `uncertain` y `censored` no aportan número publicable: value queda null pero
    trazado (el LD se conserva en detection_limit). Alineado con ana_observatorio.
    """
    if raw is None:
        return (None, "not_measured", None, False)
    s = str(raw).strip()
    if s == "" or set(s) <= {"-"} or s.upper().replace(".", "").replace(" ", "") in {"RND", "ND", "NR"}:
        return (None, "not_measured", None, False)
    if s == "?":
        return (None, "uncertain", None, False)
    if s.startswith("<") or s.startswith(">"):
        try:
            limit = float(s[1:].strip().replace(",", "."))
        except ValueError:
            return (None, "parse_error", None, False)
        return (None, "censored", limit, True)
    uncertain = s.endswith("?") or s.startswith("~")
    s = s.lstrip("~").rstrip("?").strip()
    try:
        value = float(s.replace(",", "."))
    except ValueError:
        return (None, "uncertain" if uncertain else "parse_error", None, False)
    if uncertain:
        return (None, "uncertain", None, False)
    return (value, "ok", None, False)


def melt_station_row(
    row: dict, *, campaign: str, sampling_agency: str | None, source_file: str, source_page: str
) -> list[dict]:
    """Fila wide (una estación) → registros long (uno por parámetro presente).

    Puro: no toca disco. lat/lon se resuelven desde el UTM transcrito; la metadata
    compartida se repite en cada registro. `depth_m` queda null (muestreo superficial /
    profundidad de la sonda no transcrita en esta vintage).
    """
    lat, lon, coord_qa = station_latlon(row.get("utm_este"), row.get("utm_norte"))
    base = {
        "station_id": row["station_id"],
        "lat": lat,
        "lon": lon,
        "depth_m": None,
        "sampling_agency": sampling_agency,
        "campaign": campaign,
        "station_name": row.get("station_name"),
        "monitoring_date": row.get("monitoring_date"),
        "monitoring_time": row.get("monitoring_time"),
        "source_file": source_file,
        "source_page": source_page,
    }
    records: list[dict] = []
    for param, unit in PARAM_UNITS.items():
        if param not in row:
            continue
        value, qa, detection_limit, censored = _parse_cell(row[param])
        if qa == "not_measured":
            continue  # no se emite registro para celdas vacías (incl. R.N.D.)
        # qa del registro combina lectura del valor y plausibilidad de la coord.
        qa_flag = qa if coord_qa == "ok" else f"{qa}|{coord_qa}"
        records.append({
            **base,
            "parameter": param,
            "unit": unit,
            "value": value,
            "detection_limit": detection_limit,
            "censored": censored,
            "qa_flag": qa_flag,
        })
    return records


def build_silver(vintage_dir: Path = VINTAGE_DIR, out_path: Path | None = OUT_PATH) -> pl.DataFrame:
    """Carga los CSV transcritos de `vintage_dir` → panel long silver (+ escribe parquet).

    Cada CSV es una vintage (campaña×informe). El nombre de campaña, archivo fuente y
    página se leen de columnas homónimas si están presentes; si no, del nombre del CSV.
    """
    records: list[dict] = []
    for csv_path in sorted(Path(vintage_dir).glob("*.csv")):
        df = pl.read_csv(csv_path, infer_schema_length=0)  # todo como String: lo tipa _parse_cell
        drop = ("campaign", "sampling_agency", "source_file", "source_page")
        for r in df.iter_rows(named=True):
            campaign = r.get("campaign") or csv_path.stem
            records.extend(
                melt_station_row(
                    {k: v for k, v in r.items() if k not in drop},
                    campaign=campaign,
                    sampling_agency=r.get("sampling_agency"),
                    source_file=r.get("source_file") or csv_path.name,
                    source_page=str(r.get("source_page") or ""),
                )
            )
    return _to_silver(records, out_path)


def _to_silver(records: list[dict], out_path: Path | None) -> pl.DataFrame:
    """Registros long → DataFrame tipado en el master schema (+ datetime, escritura)."""
    if not records:
        df = pl.DataFrame(schema=SILVER_SCHEMA)
    else:
        df = pl.DataFrame(records)
        # datetime tipado desde "YYYY-MM-DD" + "HH:MM" (medianoche si falta hora); ambos
        # opcionales en la vintage → datetime null si no se transcribió la fecha.
        date = pl.col("monitoring_date") if "monitoring_date" in df.columns else pl.lit(None, dtype=pl.String)
        time = pl.col("monitoring_time") if "monitoring_time" in df.columns else pl.lit(None, dtype=pl.String)
        df = df.with_columns(
            (date.fill_null("") + " " + time.fill_null("00:00"))
            .str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M", strict=False)
            .alias("datetime")
        )
        for col, dtype in SILVER_SCHEMA.items():
            if col not in df.columns:
                df = df.with_columns(pl.lit(None, dtype=dtype).alias(col))
        df = df.select(list(SILVER_SCHEMA)).cast(SILVER_SCHEMA)
        rest = [c for c in df.columns if c not in _MASTER_FIRST]
        df = df.select(_MASTER_FIRST + rest)

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out_path)
    return df


def main() -> None:
    if not VINTAGE_DIR.exists():
        raise SystemExit(f"No existe el directorio de vintages transcritas: {VINTAGE_DIR}")
    df = build_silver(VINTAGE_DIR, OUT_PATH)
    vc = df["qa_flag"].value_counts(sort=True) if df.height else None
    qa = dict(zip(vc["qa_flag"], vc["count"])) if vc is not None else {}
    params = sorted(p for p in df["parameter"].unique().to_list() if p is not None)
    print(f"\n{'='*60}\n  limnology_insitu → silver\n{'='*60}")
    print(f"  filas:        {df.height}")
    print(f"  estaciones:   {df['station_id'].n_unique()}")
    print(f"  campañas:     {', '.join(sorted(c for c in df['campaign'].unique().to_list() if c))}")
    print(f"  parámetros:   {', '.join(params)}")
    print(f"  con lat/lon:  {df.filter(pl.col('lat').is_not_null()).height}/{df.height}")
    print(f"  qa_flag:      {qa}")
    print(f"\n  escrito en {OUT_PATH}\n")


if __name__ == "__main__":
    main()

"""Tier-2: adquisición Sentinel-2 L2A + proxies ópticos de clorofila-a (NDCI/MCI).

Esta iteración entrega la ADQUISICIÓN + ÍNDICES + resúmenes por zona del lago para
las 2 campañas con chl-a in-situ (2018-II: 2018-11-22, 2019-II: 2019-10-31). El
matchup por estación y la regresión chl-a quedan DIFERIDOS: las estaciones del
observatorio (LTit##) no tienen coordenadas en disco (viven en tablas de PDFs ANA),
así que aquí solo se emite un *scaffold* de matchup keyed by station_id con ndci=None.

Regla CLAUDE.md / DECISION-005: chlorophyll_a vía satélite es un PROXY óptico inferido,
NO una medición de laboratorio.

Diseño: funciones PURAS (ndci, mci, water_mask, zonal_stats, build_matchup_scaffold)
operan sobre numpy/polars y se testean en CI sin red. Las funciones IO/red
(query_stac, load_scene, main) importan las deps satelitales de forma LAZY para no
exigirlas en CI (ver extra `satellite` en pyproject).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).parents[3]
AOI_PATH = ROOT / "data" / "sources" / "aoi" / "titicaca_pe.geojson"
SILVER_PATH = ROOT / "data" / "silver" / "ana_observatorio.parquet"
GOLD_DIR = ROOT / "data" / "gold"
MATCHUP_PATH = GOLD_DIR / "matchup_sentinel2.parquet"
OUT_JSON = ROOT / "outputs" / "sentinel2_ndci.json"

# Copernicus Data Space Ecosystem — STAC público; assets vía S3 eodata (auth CDSE).
STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
COLLECTION = "sentinel-2-l2a"
# Endpoint S3 de CDSE para descargar los assets (JP2). Requiere credenciales S3
# generadas en el dashboard CDSE, expuestas como AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY.
CDSE_S3_ENDPOINT = "eodata.dataspace.copernicus.eu"
# Claves de asset del STAC CDSE (por resolución, formato JP2). 20 m es común a B04/B05/B06/SCL.
BANDS = {"b04": "B04_20m", "b05": "B05_20m", "b06": "B06_20m", "scl": "SCL_20m"}

# Campañas con chl-a in-situ (ana_observatorio). Ventana ±días por revisita ~5 d.
CAMPAIGNS: dict[str, dt.date] = {
    "2018-II": dt.date(2018, 11, 22),
    "2019-II": dt.date(2019, 10, 31),
}
WINDOW_DAYS = 7
MAX_CLOUD = 40

# Sentinel-2 L2A: clase 6 = agua en la Scene Classification Layer (SCL).
SCL_WATER = 6
# Longitudes de onda (nm) de las bandas red-edge usadas por NDCI/MCI.
_B04_NM, _B05_NM, _B06_NM = 665, 705, 740
_MCI_FACTOR = (_B05_NM - _B04_NM) / (_B06_NM - _B04_NM)
# L2A escala reflectancia a 0..10000 con offset -1000 desde baseline 04.00.
_REFL_SCALE = 10000.0
_REFL_OFFSET = -1000.0


# --------------------------------------------------------------------------- #
# Funciones puras (testeables en CI sin red ni assets satelitales)            #
# --------------------------------------------------------------------------- #
def ndci(b04: np.ndarray, b05: np.ndarray) -> np.ndarray:
    """Normalized Difference Chlorophyll Index = (B05 - B04) / (B05 + B04).

    NaN donde la suma es 0 (no se inventa un cociente). Proxy primario de chl-a
    en aguas interiores (Mishra & Mishra 2012).
    """
    b04 = np.asarray(b04, dtype=float)
    b05 = np.asarray(b05, dtype=float)
    denom = b05 + b04
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(denom != 0, (b05 - b04) / denom, np.nan)
    return out


def mci(b04: np.ndarray, b05: np.ndarray, b06: np.ndarray) -> np.ndarray:
    """Maximum Chlorophyll Index (adaptación red-edge S2): B05 - B04 - (B06 - B04)·f.

    f = (705-665)/(740-665). Proxy secundario; sensible a alta biomasa algal.
    """
    b04 = np.asarray(b04, dtype=float)
    b05 = np.asarray(b05, dtype=float)
    b06 = np.asarray(b06, dtype=float)
    return b05 - b04 - (b06 - b04) * _MCI_FACTOR


def water_mask(scl: np.ndarray) -> np.ndarray:
    """Máscara de agua desde SCL L2A (clase 6). Excluye nube/cirros/sombra/nieve/tierra."""
    return np.asarray(scl) == SCL_WATER


def zonal_stats(index: np.ndarray, mask: np.ndarray) -> dict:
    """Estadísticos de un índice sobre los píxeles enmascarados y finitos.

    Devuelve n_px y mean/median/p10/p90 (None si no hay píxeles válidos).
    """
    vals = np.asarray(index, dtype=float)[np.asarray(mask, dtype=bool)]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {"n_px": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n_px": int(vals.size),
        "mean": float(np.mean(vals)),
        "median": float(np.median(vals)),
        "p10": float(np.percentile(vals, 10)),
        "p90": float(np.percentile(vals, 90)),
    }


def build_matchup_scaffold(silver_df: pl.DataFrame) -> pl.DataFrame:
    """Panel silver → scaffold de matchup (estación×campaña con chl-a in-situ).

    Solo filas de `chlorophyll_a` con valor; chl-a a µg/L (mg/L·1000). lat/lon/ndci
    quedan en None: se completan en el paso diferido (coords desde PDFs ANA → extraer
    el píxel NDCI en la posición de la estación). Convierte el contrato en un join.
    """
    return (
        silver_df.filter(
            (pl.col("parameter") == "chlorophyll_a") & pl.col("value").is_not_null()
        )
        .unique(subset=["station_id", "datetime", "campaign"], keep="first")
        .select(
            "station_id",
            "campaign",
            "datetime",
            (pl.col("value") * 1000).alias("chl_a_ug_l"),
        )
        .with_columns(
            pl.lit(None, dtype=pl.Float64).alias("lat"),
            pl.lit(None, dtype=pl.Float64).alias("lon"),
            pl.lit(None, dtype=pl.Float64).alias("ndci"),
        )
        .sort("station_id", "campaign")
    )


def to_reflectance(dn: np.ndarray) -> np.ndarray:
    """DN L2A (baseline ≥04.00) → reflectancia de superficie: (DN + offset) / scale."""
    return (np.asarray(dn, dtype=float) + _REFL_OFFSET) / _REFL_SCALE


# --------------------------------------------------------------------------- #
# Funciones IO / red (imports lazy; NO cubiertas por CI)                      #
# --------------------------------------------------------------------------- #
def aoi_bbox() -> list[float]:
    """[min_lon, min_lat, max_lon, max_lat] desde el AOI grueso del lago (PE).

    Falla explícito si el AOI no es un único Polygon (evita un bbox silenciosamente
    incorrecto si la estructura del geojson cambia).
    """
    features = json.loads(AOI_PATH.read_text())["features"]
    if len(features) != 1:
        raise ValueError(f"AOI esperado con 1 feature, encontrado {len(features)}")
    geom = features[0]["geometry"]
    if geom["type"] != "Polygon":
        raise ValueError(f"AOI esperado Polygon, recibido {geom['type']!r}")
    ring = geom["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def query_stac(bbox: list[float], date: dt.date, window_days: int = WINDOW_DAYS,
               max_cloud: int = MAX_CLOUD) -> list:
    """Items SENTINEL-2 L2A del Copernicus Data Space en ±window_days de `date`.

    Ordenados por nubosidad ascendente. Import lazy de pystac-client.
    """
    from pystac_client import Client

    start = (date - dt.timedelta(days=window_days)).isoformat()
    end = (date + dt.timedelta(days=window_days)).isoformat()
    client = Client.open(STAC_URL)
    search = client.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = list(search.items())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100.0))
    return items


def configure_cdse_s3() -> None:
    """Configura el acceso S3 a CDSE (eodata) para rasterio/GDAL.

    Lee credenciales de AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY del entorno (las
    genera el usuario en el dashboard CDSE). Lanza si faltan: el pipeline de rásters
    no puede leer los JP2 sin auth. Import lazy de odc.stac.
    """
    import os

    if not (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")):
        raise RuntimeError(
            "Faltan credenciales S3 de CDSE. Genera las llaves en el dashboard de "
            "Copernicus Data Space y expórtalas como AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY antes de correr el pipeline de rásters."
        )
    import odc.stac

    odc.stac.configure_rio(
        cloud_defaults=True,
        aws={"aws_unsigned": False},
        AWS_S3_ENDPOINT=CDSE_S3_ENDPOINT,
        AWS_VIRTUAL_HOSTING="FALSE",
        AWS_HTTPS="YES",
        GDAL_HTTP_TCP_KEEPALIVE="YES",
    )


def load_scene(items: list, bbox: list[float], resolution: int = 20):
    """Carga B04/B05/B06/SCL del AOI y compone un mosaico de agua-clara.

    Enmascara por SCL POR ESCENA antes de componer: la mediana de reflectancia se
    calcula solo sobre observaciones de agua (SCL=6) — no folda píxeles nubosos/sombra —
    y un píxel es agua si lo fue en ALGUNA escena válida de la ventana. Evita el sesgo de
    promediar nubes y que un `max(SCL)` descarte agua intermitente. Devuelve
    (bandas_mediana, máscara_agua bool). Requiere `configure_cdse_s3()` antes.
    Import lazy de odc.stac / xarray.
    """
    import odc.stac
    import xarray as xr

    ds = odc.stac.load(
        items,
        bands=list(BANDS.values()),
        bbox=bbox,
        resolution=resolution,
        groupby="solar_day",
        chunks={},
    )
    # Máscara de agua por (time,y,x) reusando la regla pura water_mask (SCL=6).
    scl = ds[BANDS["scl"]]
    water = xr.DataArray(water_mask(scl.values), coords=scl.coords, dims=scl.dims)
    # Reflectancia solo sobre agua-clara por escena; mediana temporal de esos valores.
    refl = ds[[BANDS["b04"], BANDS["b05"], BANDS["b06"]]].where(water)
    bands_med = refl.median(dim="time", skipna=True)
    water_any = water.any(dim="time")
    return bands_med, water_any


def _build_zones(ds) -> dict[str, np.ndarray]:
    """Particiones provisionales del AOI: lago completo + mitades N/S por fila.

    Polígonos OAS/PNUMA TDPS aún no disponibles → N/S por la coordenada `y` (proj).
    Documentado como provisional en el meta de salida.
    """
    ny = ds.sizes["y"]
    full = np.ones((ny, ds.sizes["x"]), dtype=bool)
    norte = np.zeros_like(full)
    norte[: ny // 2, :] = True  # filas superiores = norte (y mayor en CRS proyectado)
    return {"lago_pe": full, "norte": norte, "sur": ~norte}


def main() -> None:
    import os

    bbox = aoi_bbox()
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    # El conteo/selección de escenas (STAC) es público; la lectura de píxeles (S3
    # eodata) necesita credenciales CDSE. Sin ellas, emitimos scene IDs + scaffold
    # y marcamos los rásters como bloqueados, en vez de inventar datos.
    have_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
    if have_creds:
        configure_cdse_s3()

    zonal: dict[str, dict] = {}
    scenes_meta: dict[str, dict] = {}
    for campaign, date in CAMPAIGNS.items():
        items = query_stac(bbox, date)
        scenes_meta[campaign] = {
            "target_date": date.isoformat(),
            "window_days": WINDOW_DAYS,
            "max_cloud": MAX_CLOUD,
            "scene_ids": [it.id for it in items],
        }
        if not items or not have_creds:
            zonal[campaign] = {}
            continue
        bands, water = load_scene(items, bbox)
        b04 = to_reflectance(bands[BANDS["b04"]].values)
        b05 = to_reflectance(bands[BANDS["b05"]].values)
        b06 = to_reflectance(bands[BANDS["b06"]].values)
        idx_ndci = ndci(b04, b05)
        idx_mci = mci(b04, b05, b06)
        wmask = water.values  # ya bool (agua en alguna escena válida de la ventana)

        zones = _build_zones(bands)
        zonal[campaign] = {
            zname: {
                "ndci": zonal_stats(idx_ndci, zmask & wmask),
                "mci": zonal_stats(idx_mci, zmask & wmask),
            }
            for zname, zmask in zones.items()
        }

    # Scaffold de matchup (estación×campaña con chl-a in-situ; ndci pendiente).
    if SILVER_PATH.exists():
        scaffold = build_matchup_scaffold(pl.read_parquet(SILVER_PATH))
        scaffold.write_parquet(MATCHUP_PATH)
        n_matchup = scaffold.height
    else:
        n_matchup = 0

    out = {
        "meta": {
            "method": "Sentinel-2 L2A (Copernicus DSE) → NDCI=(B5-B4)/(B5+B4), MCI red-edge",
            "aoi": str(AOI_PATH.relative_to(ROOT)),
            "aoi_bbox": bbox,
            "campaigns": scenes_meta,
            "zones_note": "Particiones provisionales (lago_pe + N/S por fila); "
                          "faltan polígonos OAS/PNUMA TDPS.",
            "rasters_status": (
                "OK" if have_creds
                else "BLOQUEADO — faltan credenciales S3 CDSE (AWS_ACCESS_KEY_ID/"
                     "AWS_SECRET_ACCESS_KEY); escenas seleccionadas pero píxeles no leídos."
            ),
            "matchup_status": "DIFERIDO — sin coords de estaciones LTit## (viven en PDFs ANA); "
                              f"scaffold con {n_matchup} estaciones-campaña en {MATCHUP_PATH.name}.",
            "caveats": [
                "chlorophyll_a satelital es un PROXY óptico inferido, no medición (DECISION-005).",
                "Corrección atmosférica sobre aguas interiores con incertidumbre apreciable.",
                "NDCI satura a alta biomasa; relación con chl-a no lineal.",
            ],
        },
        "zonal_indices": zonal,
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"\n{'='*60}\n  Tier-2 Sentinel-2 NDCI/MCI → {OUT_JSON.name}\n{'='*60}")
    for camp, meta in scenes_meta.items():
        print(f"  {camp}: {len(meta.get('scene_ids', []))} escenas (target {meta['target_date']})")
    print(f"  matchup scaffold:             {n_matchup} estaciones-campaña → {MATCHUP_PATH.name}")
    print(f"\n  escrito en {OUT_JSON}\n")


if __name__ == "__main__":
    main()

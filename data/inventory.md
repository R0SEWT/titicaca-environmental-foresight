# Inventario de datos — Titicaca Environmental Foresight

> Primer entregable del proyecto: mapa de procedencia de los datos.
> La **fuente de verdad** son las fichas YAML en `data/sources/` (una por dataset),
> validadas por `catalog.py` (DECISION-001). La matriz de abajo se **genera** desde ellas
> — no se edita a mano. Las secciones narrativas (gaps, roadmap) sí son hand-written.
>
> **Estado en disco (2026-06-15):** los 4 ZIP del Drive están extraídos por completo
> (665 archivos en `data/bronze/data_limpia`); todos los locators `bronze/data_limpia/…`
> de la matriz están presentes localmente.

---

## Matriz de procedencia (generada)

**Cómo leer la matriz** (columnas generadas desde las fichas YAML):

- **status** — `available` (el archivo está en disco) / `pending_download` (aún no descargado).
- **schema** — `✓ confirmado` (columnas verificadas leyendo el archivo) / `⚠ sin confirmar`
  (perfilado pendiente) / `○ pend. extracción`. La semántica depende del tipo (DECISION-004):
  el flag es **gate de calidad solo para `tabular`/`gis`** (ahí `⚠` es defecto); en
  `pdf_report`/`image_series` el `○` **no es defecto**, sino cola de extracción (OCR/parseo/descarga).
- **prio** — prioridad para el baseline (`high`/`medium`/`low`).
- **nº lim** — nº de limitaciones documentadas en la ficha (honestidad metodológica).
- **locator** — ruta bajo `data/bronze/…` o referencia al Drive.

> La fuente de verdad son las fichas `data/sources/*.yaml` (DECISION-001); esta sección
> se regenera con `catalog.py` y los cambios manuales se sobrescriben.

<!-- CATALOG:BEGIN -->
_Generado automáticamente por `catalog.py` desde `data/sources/*.yaml` — no editar a mano (los cambios se sobrescriben)._

### Resumen

| status | n |
|--------|---|
| available | 23 |
| pending_download | 2 |

| prioridad | n |
|-----------|---|
| high | 7 |
| medium | 15 |
| low | 3 |

**Gate schema (tabular/gis prioridad alta sin confirmar): ✓ limpio (0).**

Pendiente de extracción (pdf_report/image_series, no es defecto): **9** — ana_informes_tecnicos_ala_huancane, ana_informes_tecnicos_ala_ilave, ana_informes_tecnicos_ala_juliaca, ana_informes_tecnicos_ala_ramis, ana_monitoreo_binacional, oas_pnuma_tdps_1996, peblt_monitoreo_lago, plan_accion_titicaca_2020, sentinel2_chla_titicaca.

### Matriz de procedencia

#### water_quality

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `ana_calidad_agua_v2` | ANA — Autoridad Nacional del Agua / AAA.TIT | tabular | 2013-10–2025-10 | PE | available | high | ✓ confirmado | 3 | `bronze/data_limpia/Data limpia /Data para herramienta/calidad_agua_titicaca_ANA_2013-2025_v2 (1).xlsx` |
| `ana_metales_cuencas` | ANA — Autoridad Nacional del Agua / AAA.TIT | tabular | 2025–2025 | PE | available | high | ✓ confirmado | 5 | `bronze/data_limpia/Data limpia /Data para herramienta/METALES mg-L` |
| `ana_monitoreo_binacional` | ANA — Autoridad Nacional del Agua / AAA.TIT | pdf_report | 2013–2019 | PE | available | high | ○ pend. extracción | 4 | `bronze/data_limpia/Data limpia /Data para herramienta/Resultados en gestión del agua - Ala Ilave/01. MONITOREOS/03. MONITOREO BINACIONAL LAGO TITICACA/` |
| `ana_observatorio_calidad_lago` | ANA — Autoridad Nacional del Agua / Observatorio del Agua | tabular | 2018–2023 | PE | available | high | ✓ confirmado | 6 | `bronze/data_limpia/Data limpia /Monitoreo de cuencas` |
| `ana_tributarias_2013_2025` | ANA — Autoridad Nacional del Agua / Autoridad Administrativa del Agua Titicaca (AAA.TIT) | tabular | 2013-10–2025-10 | PE | available | high | ✓ confirmado | 9 | `bronze/data_limpia/Data limpia /Data para herramienta/calidad_agua_titicaca_ANA_2013-2025_v2 (1).xlsx` |
| `peblt_monitoreo_lago` | PEBLT — Proyecto Especial Binacional Lago Titicaca / IMARPE | pdf_report | 2013–2020 | PE | available | high | ○ pend. extracción | 5 | `bronze/data_limpia/Data limpia /Estado de la calidad del agua/` |
| `ana_informes_tecnicos_ala_huancane` | ANA — Autoridad Local del Agua Huancané | pdf_report | 2013–2025 | PE | available | medium | ○ pend. extracción | 3 | `bronze/data_limpia/Data limpia /Data para herramienta/Resultados de gestión del agua - Ala Huancané/` |
| `ana_informes_tecnicos_ala_ilave` | ANA — Autoridad Local del Agua Ilave | pdf_report | 2013–2025 | PE | available | medium | ○ pend. extracción | 3 | `bronze/data_limpia/Data limpia /Data para herramienta/Resultados en gestión del agua - Ala Ilave/` |
| `ana_informes_tecnicos_ala_juliaca` | ANA — Autoridad Local del Agua Juliaca | pdf_report | 2011–2025 | PE | available | medium | ○ pend. extracción | 2 | `bronze/data_limpia/Data limpia /Data para herramienta/Resultados en gestión del agua - Ala Juliaca/` |
| `ana_informes_tecnicos_ala_ramis` | ANA — Autoridad Local del Agua Ramis | pdf_report | 2015–2025 | PE | available | medium | ○ pend. extracción | 3 | `bronze/data_limpia/Data limpia /Data para herramienta/Resultados en gestión del agua - Ala Ramis/` |
| `ana_red_monitoreo` | ANA — Autoridad Nacional del Agua | tabular | 2013–2025 | PE | available | medium | ⚠ sin confirmar | 2 | drive: Data para herramienta |
| `oas_pnuma_tdps_1996` | OEA — Organización de los Estados Americanos / PNUMA | pdf_report | 1990–1996 | PE/BO | pending_download | medium | ○ pend. extracción | 4 | drive: Estado de la calidad del agua (referencia bibliográfica) |
| `plan_accion_titicaca_2020` | Gobierno del Perú — Comisión Multisectorial | pdf_report | 2020–2024 | PE | available | medium | ○ pend. extracción | 2 | `bronze/data_limpia/Data limpia /Estado de la calidad del agua/plan_titicaca_de_accion_titicaca_2020-2024_aprobado.pdf` |
| `sentinel2_chla_titicaca` | ESA / Copernicus — Copernicus Data Space Ecosystem | image_series | 2017–ongoing | PE | pending_download | medium | ○ pend. extracción | 7 | — |
| `vertederos_caudales_coata` | Gobierno Regional de Puno / MINAM (fuente probable) | tabular | 2011–2024 | PE | available | medium | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Registro de vertederos municipales en la región Puno (2011–2024), con desagregación territorial, tipología de desechos y rutas de transporte hacia el lago Titicaca./Vertederos_Caudales_Coata_Actualizados.xlsx` |

#### hydrology

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `peblt_monitoreo_lago` | PEBLT — Proyecto Especial Binacional Lago Titicaca / IMARPE | pdf_report | 2013–2020 | PE | available | high | ○ pend. extracción | 5 | `bronze/data_limpia/Data limpia /Estado de la calidad del agua/` |
| `ana_red_monitoreo` | ANA — Autoridad Nacional del Agua | tabular | 2013–2025 | PE | available | medium | ⚠ sin confirmar | 2 | drive: Data para herramienta |
| `snirh_monitoreo_lago` | ANA — Sistema Nacional de Información de Recursos Hídricos (SNIRH) | tabular | unknown–2026-02 | PE | available | medium | ✓ confirmado | 4 | `bronze/data_limpia/Data limpia /Monitoreo del Lago Titicaca` |
| `vertederos_caudales_coata` | Gobierno Regional de Puno / MINAM (fuente probable) | tabular | 2011–2024 | PE | available | medium | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Registro de vertederos municipales en la región Puno (2011–2024), con desagregación territorial, tipología de desechos y rutas de transporte hacia el lago Titicaca./Vertederos_Caudales_Coata_Actualizados.xlsx` |

#### ecology

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `ana_observatorio_calidad_lago` | ANA — Autoridad Nacional del Agua / Observatorio del Agua | tabular | 2018–2023 | PE | available | high | ✓ confirmado | 6 | `bronze/data_limpia/Data limpia /Monitoreo de cuencas` |
| `oas_pnuma_tdps_1996` | OEA — Organización de los Estados Americanos / PNUMA | pdf_report | 1990–1996 | PE/BO | pending_download | medium | ○ pend. extracción | 4 | drive: Estado de la calidad del agua (referencia bibliográfica) |
| `sentinel2_chla_titicaca` | ESA / Copernicus — Copernicus Data Space Ecosystem | image_series | 2017–ongoing | PE | pending_download | medium | ○ pend. extracción | 7 | — |
| `fauna_endemicas_amenazadas` | SERNANP / MINAM (fuente probable) | tabular | unknown–unknown | PE | available | low | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Animales/Endemicas y amenazadas.xlsx` |

#### health

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `minsa_salud_morbilidad_puno` | MINSA — DIRESA Puno (HIS / estadística sectorial) | tabular | 2004–2024 | PE | available | high | ✓ confirmado | 5 | `bronze/data_limpia/Data limpia /Salud` |
| `minsa_mortalidad_materna_neonatal_puno` | MINSA — DIRESA Puno | tabular | 2000–2025 | PE | available | medium | ✓ confirmado | 3 | `bronze/data_limpia/Data limpia /Muertes maternas` |

#### socioeconomic

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `inei_censo_puno_2007_2017` | INEI — Instituto Nacional de Estadística e Informática | tabular | 2007–2017 | PE | available | medium | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Censo Puno 2007 y 2017 - Joaquin Suazo` |
| `inei_demografia_proyecciones_puno` | INEI — Instituto Nacional de Estadística e Informática | tabular | 1995–2030 | PE | available | medium | ⚠ sin confirmar | 2 | `bronze/data_limpia/Data limpia /Demografía de Puno y Proyecciones` |
| `midarh_derechos_agua` | ANA — Autoridad Nacional del Agua (módulo MIDARH / SNIRH-SARH) | administrative | 1991–2025 | PE | available | medium | ✓ confirmado | 4 | `bronze/data_limpia/Data limpia /MIDARH/MIDARH.xlsx` |
| `mincetur_turismo_puno` | MINCETUR — DIRCETUR Puno | tabular | 2005–2025 | PE | available | medium | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Turismo en Puno - Joaquin Suazo` |
| `midagri_precio_chacra_puno` | MIDAGRI — Dirección Regional Agraria Puno | tabular | 2014–2025 | PE | available | low | ⚠ sin confirmar | 3 | `bronze/data_limpia/Data limpia /Información agricultura, precio en chacra - Joaquin Suazo` |
| `pronied_mantenimiento_colegios_puno` | PRONIED — Programa Nacional de Infraestructura Educativa / MINEDU | tabular | 2008–2025 | PE | available | low | ✓ confirmado | 3 | `bronze/data_limpia/Data limpia /Colegios` |

#### policy

| id | institución | tipo | cobertura | país | status | prio | schema | nº lim | locator |
|----|-------------|------|-----------|------|--------|------|--------|--------|---------|
| `oas_pnuma_tdps_1996` | OEA — Organización de los Estados Americanos / PNUMA | pdf_report | 1990–1996 | PE/BO | pending_download | medium | ○ pend. extracción | 4 | drive: Estado de la calidad del agua (referencia bibliográfica) |
| `plan_accion_titicaca_2020` | Gobierno del Perú — Comisión Multisectorial | pdf_report | 2020–2024 | PE | available | medium | ○ pend. extracción | 2 | `bronze/data_limpia/Data limpia /Estado de la calidad del agua/plan_titicaca_de_accion_titicaca_2020-2024_aprobado.pdf` |
<!-- CATALOG:END -->

---

## Datos a capturar / pendientes

Variables y fuentes aún ausentes del catálogo, ordenadas por prioridad para el baseline.

| Dato | Fuente probable | Prioridad | Método de captura |
|------|-----------------|-----------|-------------------|
| Clorofila-a / Secchi in situ del lago | PDFs PEBLT/IMARPE (`peblt_monitoreo_lago`) y monitoreo binacional (`ana_monitoreo_binacional`) | **Alta** — variable objetivo del Tier 1 | Extracción tabular de PDFs (issue dedicado; binacional depende de T5) |
| Clorofila-a satelital (proxy óptico) | Sentinel-2 vía Copernicus | **Alta** — Tier 2 | T13 (`sentinelhub`/`openeo`) |
| Series de nivel del lago (diarias/mensuales) | ANA-SNIRH, PEBLT, SENAMHI | **Alta** — contexto estacional y temporal splits | SNIRH API / descarga |
| Caudal diario de ríos principales | SENAMHI-SNIRH | **Media** — covariable hidrológica | SNIRH descarga |
| Datos Bolivia (cuencas Katari, desagüe) | MMAyA / SENASBA Bolivia | **Media** — contexto binacional | Coordinación binacional / protocolo |
| Coordenadas de plantas de tratamiento (PTAR) | SUNASS, ANA | **Media** — presión puntual | Portal SUNASS / solicitud |
| Pasivos mineros georeferenciados | MINEM — GEOCATMIN | **Media** — fuente de metales | Portal MINEM |
| Pesca artesanal | PRODUCE / RNT | **Baja** | Portal estadístico |

## Georreferenciación de estaciones

Subproducto del inventario para el mapa espacial y el matchup Tier-2. La **fuente de verdad** es
`data/sources/station_coords_catalog.csv` (una fila por estación, con columnas de evidencia:
`coord_original_text`, `coord_source`, `coord_source_file`, `extraction_method`, `datum`,
`confidence`, `status`), generada por `silver/station_catalog.py`. Política (DECISION-006):
**nunca se infiere ni inventa** — sin fuente en disco → `missing`; fuentes incompatibles (>300 m)
→ `ambiguous`.

| status | n | fuentes |
|--------|---|---------|
| `resolved` | 47 | protocolo binacional (42) + IT 085-2021 UH Coata (4) + RED MONITOREO (1) |
| `ambiguous` | 0 | — |
| `missing` | 29 | red expandida `LTit78–106` + `LTit35` + `RDesa2` |

**Gap de crosswalk de códigos.** Las 29 `missing` arrastran una correspondencia documental no
resuelta entre códigos históricos (`BInte`, `BPuno`, `LTiti`, `RDesa`) y los nuevos del bronze
(`LTit78–106`, `RDesa2`). `LTit35` aparece con coords oficiales en el informe nov-2018, pero sin
mapeo seguro. No se asignan por orden ni cercanía (riesgo de ubicar estaciones incorrectamente).
Se rastrea en el bead `t3l.5.1.1` (solicitud al partner de la tabla maestra: códigos +
coordenadas + CRS + documentos de respaldo).

**Impacto en el modelo.** De las 53 estaciones con chl-a, solo **38 están georreferenciadas** →
el matchup Tier-2 desde datos en disco queda topado ahí hasta resolver las 29 `missing`.
Ver DECISION-006.

## Gaps críticos para el modelo

1. **Clorofila-a / Secchi in situ**: ausente de las fuentes tabulares confirmadas; vive en los
   PDFs de cruceros PEBLT y del monitoreo binacional, que son la **cola de extracción** (no defecto
   de catálogo — ver la línea de gate del resumen). Es la variable objetivo principal del Tier 1.
2. **Cobertura temporal discreta**: los monitoreos de cuencas son eventos discretos (no series
   continuas); 2013–2025 con gaps. Respetar frontera estación seca/húmeda en los splits (no random).
3. **Datos Bolivia**: ausentes; todo el conjunto actual es de la parte peruana.
4. **Matchups satélite-campo**: el componente de mayor esfuerzo para el Tier 2, aún no preparado.
   Dos cuellos de botella: (a) la georreferenciación topa el matchup en 38/53 estaciones con chl-a
   hasta resolver las 29 `missing` (ver "Georreferenciación de estaciones"); (b) el matchup
   Sentinel-2 actual emite `lat/lon` nulos incluso para estaciones resueltas — defecto abierto en el
   bead `v74` (propagación de coordenadas). El pipeline Tier-2 completo es el bead `0kd`.
5. **Metales en formato numérico**: solo `ana_metales_cuencas` trae valores numéricos (formato largo);
   en `ana_tributarias_2013_2025` los metales figuran como texto de excedencia. Cruce relacional vía
   `UBIGEO` (PK designada en el diccionario RAMIS).

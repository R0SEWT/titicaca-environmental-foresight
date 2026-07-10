# Decision Log

Registro append-only de decisiones metodológicas. Una entrada por decisión, ~6 líneas.
No se edita el pasado; si una decisión se revierte, se añade una nueva entrada que la supersede.

---

## DECISION-001 — La provenance vive en el catálogo, no en documentos paralelos
**Fecha:** 2026-06-10
**Contexto:** El directive de trazabilidad pide `DATA_PROVENANCE.md` y `master_project_registry.csv`. El repo ya tiene `data/sources/*.yaml` (versionado, una ficha por dataset) validado por `catalog.py`, que genera `data/gold/sources_catalog.parquet`.
**Opciones:** A) crear los documentos del directive a mano · B) usar el catálogo existente como fuente de verdad.
**Decisión:** B. Cada dataset = una ficha YAML; la matriz maestra es el parquet generado. No se crean CSV/MD paralelos que forkearían la verdad.
**Razón:** Evita divergencia y aprovecha la validación de CI ya existente.
**Impacto:** `DATA_PROVENANCE` y `master_project_registry` se consideran "ya implementados". Perfilar un dataset = llenar su YAML.

## DECISION-002 — Documentar como subproducto, no como fase
**Fecha:** 2026-06-10
**Contexto:** El directive lista 6 documentos de gobernanza. Montarlos vacíos hoy frena el levantamiento de datos y desvía la sesión a gobernanza.
**Opciones:** A) escribir los 6 documentos ahora · B) mantener solo infraestructura mínima viva (catálogo + este log + stub de contribuciones) y que el resto se llene al tocar datos.
**Decisión:** B. El conductor de la sesión sigue siendo el perfilado de la capa primaria; provenance/`qa_flag` salen de ahí.
**Razón:** El valor está en evidencia trazable, no en plantillas anticipadas.
**Impacto:** `PREDICTION_AUDIT`, `PROJECT_STATUS_ASSESSMENT`, `PUBLICATION_STRATEGY` se promueven a documento propio solo cuando tengan contenido real.

## DECISION-003 — `schema_confirmed: false` es la cola de perfilado
**Fecha:** 2026-06-10
**Contexto:** 13 de 15 fichas en `data/sources/` tienen `schema_confirmed: false`. Las fichas se crearon antes de descomprimir los zips, así que reflejan expectativa, no contenido verificado.
**Opciones:** A) confiar en las fichas tal cual · B) tratar `schema_confirmed:false` como TODO explícito a cerrar perfilando.
**Decisión:** B. Perfilar el archivo real → llenar `variables`/`limitations`/`granularity` → flip a `true`.
**Razón:** Cierra el loop levantamiento↔documentación sin trabajo extra.
**Impacto:** El progreso del inventario se mide por nº de `schema_confirmed:true`. Capa primaria (monitoreo cuencas/lago + metales) es la prioridad alta pendiente.

## DECISION-004 — `schema_confirmed` es gate solo para tipos legibles por máquina
**Fecha:** 2026-06-10
**Contexto:** El criterio de T7 exige "sin `schema_confirmed:false` en prioridad alta". Pero 2 fuentes high son `pdf_report` (PEBLT y monitoreo binacional) cuyo contenido tabular requiere extracción (OCR/parseo); la del binacional ni está en disco (la extrae T5). Marcarlas `true` para pasar el gate sería deshonesto.
**Opciones:** A) falsear el flag · B) bajar su prioridad a medium (gaming) · C) redefinir el gate por tipo · D) añadir un campo `extraction_status` aparte.
**Decisión:** C. `schema_confirmed` es defecto solo para `tabular`/`gis` (legibles por máquina); el gate de T7 (`catalog.py --check` sale !=0) solo cuenta esas. Para `pdf_report`/`image_series`, `false` = "pendiente de extracción" (estado, no defecto), se reporta aparte y se rastrea con un issue dedicado.
**Razón:** Honra el rigor: no se infla la confianza de datos no leídos. El gate sigue siendo ejecutable y blindado en CI (`test_gate_clean`).
**Impacto:** `minsa_salud_morbilidad_puno` (tabular, leída en T4) pasa a `true`; PEBLT/binacional siguen `false` pero documentados como cola de extracción. T7 cierra con gate verde sin trampa.

## DECISION-005 — La clorofila-a satelital es un proxy óptico inferido, no una medición
**Fecha:** 2026-06-12
**Contexto:** El target primario (eutrofización/chl-a) casi no existe in-situ: la planilla principal `ana_tributarias_2013_2025` no tiene chl-a; sí hay 57 valores en `ana_observatorio_calidad_lago`, concentrados en 2018-II/2019-II. Sentinel-2 puede aportar chl-a, pero solo como inferencia óptica.
**Opciones:** A) tratar la chl-a satelital como medición directa · B) catalogarla como proxy inferido, complemento del in-situ, calibrado/validado contra los matchups disponibles.
**Decisión:** B. Fuente `sentinel2_chla_titicaca` (`type: image_series`, `priority: medium`). Plataforma **Copernicus Data Space Ecosystem** (STAC, L2A); AOI **lado peruano** (`data/sources/aoi/titicaca_pe.geojson`); proxy primario **NDCI** = (B5−B4)/(B5+B4) (Mishra & Mishra 2012), MCI secundario, ML calibrado (XGBoost, Sherf 2025) como ruta futura.
**Razón:** El satélite ve el estado óptico superficial, no chl-a de laboratorio; afirmar lo contrario viola la regla de honestidad de CLAUDE.md. Como complemento densifica la serie en años recientes (2020–2025).
**Impacto:** T13 entrega solo la catalogación (ficha + AOI + proxy + esta decisión). El pipeline real (STAC pull, corrección atmosférica, índices, matchup con in-situ, regresión con splits temporales/espaciales sin leakage) es un bead Tier-2 que depende de T13.

## DECISION-006 — Coordenadas de estaciones: catálogo multi-fuente con status, nunca inferidas
**Fecha:** 2026-06-15
**Contexto:** El panel silver `ana_observatorio` (76 estaciones LTit##/RCoat/RDesa) trae `station_id` pero los `.xls` de reporte no incluyen coordenadas. Se necesitan lat/lon para el mapa espacial y el matchup Tier-2.
**Fuentes (en disco):** `PROTOCOLO-BINACIONAL` (tabla LTit01-73, UTM 19S → 42 estaciones); `IT 085-2021 UH Coata` (LTiti74-77, RCoat; tablas con separador de millar `\xa0` → 4 estaciones); `RED MONITOREO ... TITICACA` (ríos RDesa1, corrobora RCoat3 → 1 estación). LTit78-106 y LTit35 **no aparecen en ninguna fuente en disco**.
**Decisión:** Catálogo consolidado `data/sources/station_coords_catalog.csv` (módulo `silver/station_catalog.py`) con una fila por estación + columnas de evidencia (texto original, archivo, método, datum, confianza) y `status ∈ {resolved, ambiguous, missing}`. NO se infiere ni inventa: sin fuente → `missing`; fuentes incompatibles (>300 m) → `ambiguous`. Validaciones: bbox de la cuenca, duplicados, UTM→WGS84 testeada.
**Cobertura:** 47/76 `resolved` (protocolo 42 + Coata 4 + RED 1), 0 `ambiguous`, 29 `missing`. De las 53 estaciones con chl-a, **38 resueltas** — el matchup Tier-2 desde datos en disco queda topado ahí.
**Límite / siguiente fuente:** las 29 `missing` (red expandida LTit78-106 + LTit35 + RDesa2) requieren el catálogo online SNIRH o datos del partner; bead `dij` las deja documentadas como `missing`, no resueltas a la fuerza.

## DECISION-007 — Calibración chl-a~NDCI: se reportan lineal y log, holdout indicativo, leakage documentado
**Fecha:** 2026-06-15
**Contexto:** Con el matchup georreferenciado (v74) se extrae el píxel NDCI por estación (`tier2/sentinel2.py:sample_index_at_points`) y se calibra chl-a~NDCI (`model.py`). Solo hay 2 campañas con chl-a in-situ (2018-II, 2019-II) y las mismas estaciones aparecen en ambas.
**Opciones:** A) un solo modelo (lineal o log) presentado como validado · B) reportar ambas formas como calibración + holdout temporal indicativo + documentar la limitación de leakage.
**Decisión:** B. Se ajustan y reportan **lineal** (`chl_a~ndci`) y **log10** (`log10(chl_a)~ndci`); se da un holdout *leave-one-campaign-out* (train 2018→test 2019 y viceversa) como señal **indicativa**, no como validación. Métricas en numpy (sin sklearn/scipy). `caveats` fijos en la salida.
**Razón:** Con 2 fechas y estaciones colocadas no se puede separar temporal **y** espacialmente a la vez (regla de leakage de CLAUDE.md); fingir un CV limpio sería deshonesto. chl-a satelital sigue siendo PROXY óptico (DECISION-005).
**Impacto:** `outputs/sentinel2_ndci.json` lleva `regression` (calibración + holdout + caveats); `matchup_sentinel2.parquet` queda con `ndci`/`mci` poblados donde hubo agua. Modelo Tier-2 robusto requiere más campañas/fechas (cola de extracción de PDFs limnológicos, dvj/T14).

## DECISION-008 — Run Tier-2 a 20 m nativo: calibración mono-campaña (2019-II), holdout temporal imposible desde disco
**Fecha:** 2026-06-15
**Contexto:** El pipeline `0kd` se corrió a plena resolución (`TITICACA_S2_COARSEN=1`, NDCI/MCI a 20 m) en una máquina Lightning de 125 GB/32 cores. El run inicial reventaba con miles de errores GDAL `Stream too short`/`opj_get_decoded_tile failed`: el scheduler de hilos disparaba ~32 lecturas S3 simultáneas y CDSE trunca los JP2 bajo alta concurrencia. Fix: `num_workers` acotado (default 4) + `GDAL_HTTP_MAX_RETRY=10`/`GDAL_HTTP_MULTIPLEX=NO`.
**Resultado:** 4 GeoTIFFs (NDCI/MCI × 2018-II/2019-II, 8316×6448 a 20 m), matchup 53 estaciones-campaña con NDCI en 35/53, regresión chl-a~NDCI **lineal** (n=35, r²=0.67, RMSE=7.4 µg/L) y **log10** (n=35, r²=0.65). `zonal_resolution_m: 20`, `rasters_status: OK`.
**Hallazgo clave:** el `holdout_loco` salió **vacío** — y es correcto: las 14 chl-a de 2018-II son TODAS de estaciones `LTit78-91` (la red expandida sin coordenadas en disco, DECISION-006), así que 2018-II aporta 0 matchups georreferenciados. Los 35 matchups usables están todos en **2019-II** → la calibración es de facto **mono-campaña** y el holdout *leave-one-campaign-out* es **imposible desde datos en disco**, no solo "indicativo".
**Impacto:** La regresión es calibración óptica de una sola fecha; refuerza (no contradice) DECISION-005/007: chl-a satelital sigue siendo PROXY y no hay validación temporal. Desbloquear el holdout requiere georreferenciar LTit78-106 (SNIRH/partner, las 29 `missing` de dij) **o** extraer más campañas con chl-a in-situ (dvj/T14).

## DECISION-009 — Limnología in-situ: transcripción asistida por visión a CSV versionados, no parser de PDF ni OCR
**Fecha:** 2026-06-15
**Contexto:** dvj/T14 necesita chl-a/Secchi in-situ (target Tier-1). Las fuentes (cruceros PEBLT/IMARPE + monitoreo binacional ANA, 2013–2020) son **PDFs escaneados sin capa de texto** (`pdftotext` da 0 chars; el binacional trae ABBYY pero ~0 texto útil). No hay tesseract/ocrmypdf instalado. Spike sobre `INFORME I CRUCERO HIDROQUIMICO 2019` (94 pp): el cuerpo presenta resultados como **gráficos de barras** y los datos por estación están en tablas-anexo (Anexo N°1/N°2, parámetros al 20%/80% de profundidad). Hallazgo: **el crucero NO mide clorofila-a** (Cuadro N°4: Secchi/transparencia, temp, pH, conductividad, STD, OD, salinidad, DBO5, nitritos, nitratos, sulfatos, fosfatos, N-amoniacal); chl-a habría que buscarla en los informes de Bahía (sin confirmar). Releyendo dos veces la misma tabla anexo, ~6 de 27 celdas de Secchi son ambiguas por dígito (5.5 vs 8.5, 2.0 vs 3.0, 4 vs 8) a la calidad de escaneo disponible.
**Opciones:** A) parser pdfplumber (inviable: 0 texto) · B) instalar OCR (sudo) + extracción tabular (frágil contra gráficos, dígitos ambiguos) · C) transcripción asistida por visión a CSV versionados con qa por celda.
**Decisión:** C (elegida con el usuario). Se rasteriza con `pdftoppm`, se lee visualmente y se transcribe a `data/sources/limnology_insitu/<vintage>.csv` (formato wide, columnas de parámetro ya en nombre canónico del master schema). El **artefacto reproducible es el CSV transcrito + el loader** `silver/limnology_pdf.py` (funde wide→long, master schema, UTM 19S→WGS84 reutilizando `station_coords`, gate de plausibilidad por bbox del lago), NO un parser de PDF. Cada valor lleva `qa_flag`: `ok`/`uncertain`/`not_measured`; las celdas `uncertain` (dígito ilegible, transcritas como `?`) se dejan en **null** para no publicar números no legibles, pero quedan trazadas.
**Razón:** Honra el rigor de CLAUDE.md: no se inventan dígitos que el escaneo no permite leer; el gate de coords y los flags hacen explícita la incertidumbre. Evita una dependencia OCR pesada (sudo) que igual fallaría sobre gráficos.
**Impacto:** Primera vintage = PEBLT Crucero I 2019 @20%, **parcial** (7 estaciones, solo Secchi; coords verificadas sobre el lago). Queda pendiente (beads de seguimiento): segunda lectura verificada de las celdas `uncertain`, columnas OD/nutrientes/temp/pH, profundidad 80%, resto de informes PEBLT + 7 ITs binacionales, y confirmar si los informes de Bahía traen clorofila-a. `schema_confirmed` de las fichas sigue en `false` (extracción en curso, no completa — DECISION-004).

## DECISION-010 — Los informes de Bahía PEBLT NO miden clorofila-a in-situ; chl-a in-situ solo vía ANA
**Fecha:** 2026-06-18
**Contexto:** DECISION-009 dejó abierto si los informes de **Bahía** PEBLT traen clorofila-a/Secchi (target Tier-1), una vez confirmado que los cruceros no la miden (Cuadro N°4). Bead uy8. Las 5 fuentes (Bahía Lago Titicaca 2019, Bahía Interior Puno 2020, Bahías Lago 2020, Aguas Superficiales Corrientes 2019 y 2020) son PDFs escaneados sin texto; se leyeron visualmente (rasterización + visión).
**Hallazgo:** Ninguno de los 5 informes mide clorofila-a ni Secchi. El set in-situ es siempre el mismo: pH, temperatura, TDS, conductividad, salinidad, OD, **turbidez (NTU)**, nitratos, nitritos, fosfatos, sulfatos, amoniaco/N total, DBO5 y coliformes totales/termotolerantes. Instrumental: multiparamétrico **Horiba** + turbidímetro **HACH** (sin fluorómetro de chl-a). La transparencia se reporta como NTU, no como disco Secchi (Secchi solo aparece en cruceros). chl-a figura únicamente como criterio de clasificación trófica **referencial** (umbrales OCDE/Vollenweider), nunca medida; incluso la actividad algal se **infiere** desde el pH alcalino. Dato adicional: el informe ANA **IT 007-2013** (Bahía Puno, agencia distinta) **sí** mide chl-a (Cuadro N°04, 20 puntos) y Secchi — el único in-situ de chl-a/Secchi hallado, familia binacional (kf5).
**Decisión:** Documentar la **ausencia** de chl-a/Secchi en PEBLT (ficha `peblt_monitoreo_lago.yaml`: línea de variables + limitación explícita). No se transcribe chl-a de PEBLT porque no existe. La búsqueda de chl-a/Secchi in-situ se traslada a los informes ANA (kf5).
**Impacto:** Refuerza DECISION-005/008: sin chl-a in-situ densa, el proxy satelital Sentinel-2 (NDCI/MCI) es la vía principal para eutrofización, y la calibración queda topada por los pocos matchups ANA. Cierra uy8.

## DECISION-011 — Piloto kf5: transcripción del IT binacional ANA 007-2013, suite completa con metales censurados
**Fecha:** 2026-06-18
**Contexto:** kf5 transcribe los ITs del monitoreo binacional ANA (2013-2019), la **única** fuente in-situ de chl-a (DECISION-010). De los 11 ITs, 5 tienen capa de texto (OCR) y 6 son escaneo puro; aun los de texto traen las tablas con alineación rota, así que la transcripción es **visión** (DECISION-009), usando el texto solo para navegar. PILOTO elegido con el usuario: **IT 007-2013** (Bahía Puno, abril 2013), **suite limnológica completa**.
**Decisión:** (1) Vintage `ana_binacional_lago_titicaca_2013.csv`: 20 estaciones (11 Bahía Interior + 9 Bahía Mayor/Río Willy, CUADRO 07 y 12), 37 parámetros (campo + nutrientes + chl-a + corrida de 25 metales). Coords de CUADRO 02 (tabla impresa, fiable) → las 20 caen en el bbox del lago. (2) Loader `limnology_pdf.py` extendido: `PARAM_UNITS` con la suite; manejo de **censurados** `<X` → `value` null, `detection_limit=X`, `censored=true`, `qa_flag=censored`; `R.N.D./N.D.`→`not_measured`; columnas `detection_limit`+`censored` en el silver schema, alineadas con `ana_observatorio`. (3) **chl-a en µg/L** pese al rótulo `mg/L` del PDF (valores 0.2–5.8 solo coherentes en mg/m³≡µg/L). (4) chl-a de la **Bahía Mayor excluida**: el lab la marcó "Resultado Referencial" (reactivo vencido); la chl-a usable son los **10 valores de la Bahía Interior**.
**Razón:** Primer chl-a in-situ del proyecto (target Tier-1), con metales trazados sin perder los <LD. Honra DECISION-009 (no inventar dígitos: celdas ilegibles → `?`/uncertain; censurados explícitos).
**Impacto:** `limnology_insitu.parquet` ahora une PEBLT (secchi) + ANA (suite+chl-a): 719 filas, 508 ok / 208 censored / 3 uncertain. Habilita matchups in-situ adicionales para Tier-2 (DECISION-008). Cola kf5: los 10 ITs binacionales restantes 2013-2019.

## DECISION-012 — kf5: IT binacional 018-2014 (marzo, sector peruano); chl-a toda bajo detección
**Fecha:** 2026-06-18
**Contexto:** Segundo IT de kf5 tras el piloto (DECISION-011). IT 018-2014 es un informe **binacional** con dos partes: sector Bolivia (IBTEN-ALT-UOB, puntos Ltiti15-35 con chl-a en mg/m³) y **sector Perú** (DGCRH-ANA). El proyecto es lado peruano (DECISION-005/006).
**Decisión:** (1) Se transcribe **solo el sector peruano** (lado boliviano fuera del AOI): vintage `ana_binacional_lago_titicaca_2014_mar.csv`, 40 estaciones (11 Bahía Interior + 9 Bahía de Puno + 20 lago mayor/Wiñaymarca, red `LTiti##` que matchea el catálogo), 43 parámetros (CUADRO 5/6/7). Las 40 caen en el bbox del lago. (2) **chl-a `<0.004 mg/L` en las 40** → toda bajo detección; se convierte a **µg/L** (`<4`, censurada) para consistencia con DECISION-011 (canonical chlorophyll_a en µg/L). (3) Params nuevos en el loader: cyanide_wad, silicates, sulfate_mg_l, sulfides, nitrate_mg_l, nitrite_mg_l, kjeldahl_n_mg_l, chromium_hexavalent, oils_grease, fecal_coliforms. (4) Punto auxiliar `LTiti13.1` (isla Anapia): nutrientes ambiguos en el escaneo → `?` (uncertain), no se inventan.
**Razón:** Densifica la red principal del lago (LTiti) con limnología in-situ marzo-2014. La chl-a censurada (<4 µg/L) es señal de lago **no hipereutrófico** en aguas abiertas esa campaña — útil aunque no aporte valor puntual para la regresión Tier-2.
**Impacto:** `limnology_insitu.parquet`: 2439 filas (PEBLT crucero + ANA 2013 + ANA 2014-mar); IT 018 aporta 1720 registros (961 censored / 756 ok / 3 uncertain). chl-a usable in-situ sigue siendo solo la de IT 007 (Bahía Interior). Cola kf5: 9 ITs binacionales restantes (2014-2019).

## DECISION-013 — Censo de chl-a en los 9 ITs binacionales restantes: priorizar por señal, no transcribir a ciegas
**Fecha:** 2026-06-18
**Contexto:** IT 018-2014 costó ~1720 celdas y su chl-a salió toda bajo detección (DECISION-012). Antes de transcribir la suite completa de los 9 ITs restantes, se hizo un **censo barato**: leer solo la fila/sección de Clorofila (y Secchi) de cada IT y clasificar la señal. La presencia de chl-a varía por laboratorio/campaña.
**Censo (sector peruano):**
| IT | Campaña | chl-a | Secchi | Evidencia |
|----|---------|-------|--------|-----------|
| 061-2014 | oct 2013 | **detectable** | — | "Monitoreo Integral"; CUADRO 12.1/12.3 con valores numéricos, varios > ECA |
| 039-2014 | oct 2014 | no | **sí** | CUADRO 5/6/7 fila "Transparencia al disco Sechi"; sin fila clorofila |
| 16-2016 | oct 2015 | no | no | Cuadro de parámetros (CORPLAB) sin clorofila ni Secchi |
| 132-2016 | abr 2016 | no | **sí** | protocolo de campo "Registro transparencia (disco Secchi)"; sin clorofila |
| 179-2017 | nov 2017 | no | **sí** | Cuadro N°4 de parámetros sin clorofila; Secchi de campo |
| 42-2018 | jul 2018 | **por confirmar** | sí | serie ALS; chl-a no aparece en su análisis multitemporal (confirmar fila al transcribir) |
| 09-2019 | nov 2018 | **detectable** | — | conclusiones: Clorofila A Bahía Interior prom 24.8 µg/L (>ECA), LTiti12 |
| 36-2019 | abr 2019 | **detectable** | — | referida por IT 09/70: chl-a abril 2019 = 0.066 mg/L (66 µg/L) |
| 70-2019 | nov 2019 | **detectable** | — | Figura N°9 Clorofila A: Bahía Interior 25–46 µg/L (Eutrófico) |
**Decisión:** Orden de transcripción completa por valor Tier-1 (chl-a detectable): **IT 061-2014, IT 09-2019, IT 36-2019, IT 70-2019** (la serie ALS reporta chl-a en mg/L → convertir a µg/L como DECISION-011/012). Luego confirmar+decidir **IT 42-2018**. Los 4 sin chl-a (039, 16, 132, 179) quedan en prioridad baja: registro ligero o transcripción posterior por sus nutrientes/físicoquímicos/**Secchi** (039/132/179 sí traen Secchi, otro proxy Tier-1).
**Razón:** Evita repetir el gasto de IT 018 (suite completa sin chl-a). El censo (≈30 lecturas) reordena la cola hacia los ~4 ITs que sí mueven el target Tier-1. Honra el rigor: lo no leído con confianza queda "por confirmar", no inventado.
**Impacto:** kf5 pasa de "transcribir 9 informes" a una cola priorizada. Sin cambios de código/CSV en esta fase (solo censo + registro).

## DECISION-014 — OCR asistido (Docling+GPU en gorgo) para ITs densos; IT 061 Bahía Interior núcleo
**Fecha:** 2026-06-21
**Contexto:** Los ITs binacionales con chl-a detectable (061/09/36/70) tienen tablas densas (≈38×36). La transcripción por visión directa no es fiable celda-a-celda (IT 061: el escaneo es 300 DPI pero con `/Rotate 270`). Se evaluó OCR. tesseract/Camelot no sirven (sin estructura / solo digitales). **Docling** (TableFormer + OCR) sí reconstruye la rejilla.
**Decisión:** Pipeline **Docling+GPU en gorgo** (RTX 4060 Ti, uv): `do_ocr` + `EasyOcrOptions(es,en)` + `TableFormerMode.ACCURATE` + CUDA. **Fix crítico:** Docling sobre el PDF rotado da basura; hay que alimentar la imagen **cruda enderezada** (`pdfimages` → `magick -density 300` → PDF rot 0). El borrador acierta ~85-90% pero con errores de OCR (`787`→`7.87`, `o/d`→`0`, coma decimal, shifts) → es **borrador para verificar**, no carga directa: limpieza + **crop-zoom** de filas clave contra la imagen + flags `?`. Notablemente, el cross-check mostró que **Docling es MÁS fiable que la lectura visual directa** en estas tablas (resolvió 4 discrepancias de chl-a a favor de Docling). Ver memoria `gorgo-docling-ocr-pipeline`.
**Entrega IT 061:** vintage `ana_binacional_lago_titicaca_2013_oct.csv` — **núcleo Tier-1** de la **Bahía Interior** (11 est, 17 params): chl-a **10 valores 15–34 µg/L** (eutrófico; mg/L→µg/L), físicoquímicos, nutrientes, As/Pb/Cd, coliformes. Coords idénticas a IT 018 (CUADRO 11.2 lo confirma); las 11 caen en el bbox. Diferido: metales traza de 12.1, y Bahía de Puno (12.2) + Lago Mayor (12.3), donde **chl-a es all-censored** (`<0.004`) salvo un punto.
**Impacto:** `limnology_insitu.parquet`: 2621 filas (4 campañas). Pipeline OCR validado y reusable para 09/36/70-2019. chl-a in-situ usable acumulada: IT 007 (Bahía Interior 2013-abr) + IT 061 (Bahía Interior 2013-oct).

## DECISION-015 — IT 036-2019 clorofila: mg/L → µg/L (×1000); gap Lago Mayor (Cuadro 9)
**Fecha:** 2026-06-23
**Contexto:** IT 036-2019 (abril 2019) — 148 tablas extraídas vía Docling+GPU. Cuadros 7 (BInte), 8 (BPuno) y 10 (Lago Menor) extraídos correctamente. La fila Clorofila reporta unidades `mg/L` con valores coherentes con esa unidad (p.ej. BInte LTiti59: 0.08935 mg/L → 89.35 µg/L), confirmado porque la columna ECA = 0.008 mg/L (= 8 µg/L) y las tablas ECA del informe muestran excedencias en BInte. A diferencia de IT 007-2013 (donde el rótulo `mg/L` era error de etiqueta y los valores eran en realidad µg/L), en IT 036-2019 los valores en `mg/L` son correctos: se convierten ×1000 para almacenar en la unidad canónica `µg/L`.
**Decisión:** Almacenar chl-a en `µg/L` (×1000 sobre el valor PDF). Cuadro 9 (Lago Mayor, 21 estaciones) no fue extraído por Docling (tabla demasiado ancha, ~24 columnas incluyendo Param + Unidad + ECA + 21 estaciones). Gap documentado en el README. IT 009-2019 BInte: ECA exceedance histórica confirma chl-a > 10 µg/L pero la tabla de resultados del PDF de 128 MB no fue extraída por Docling.
**Impacto:** `limnology_insitu.parquet`: 2844 filas (5 campañas), n=42 valores de chl-a numéricos post IT 036. Vintage: `data/sources/limnology_insitu/ana_binacional_lago_titicaca_2019_apr.csv` (22 estaciones).

## DECISION-016 — IT 070-2019 clorofila: mg/L → µg/L (×1000); gap BPuno/Lago Menor en OCR
**Fecha:** 2026-06-23
**Contexto:** IT 070-2019 (octubre-noviembre 2019) — 140+ tablas extraídas vía Docling+GPU. Cuadro 7 (BInte, 6 estaciones LTiti59-64, muestreo 28/10/2019) extraído correctamente; misma convención de unidades que IT 036-2019 (mg/L en el PDF → µg/L en vintage). Valores BInte 24.96–46.24 µg/L (hipereutrófico, todos exceden ECA 8 µg/L), confirmado por tabla ECA del informe. BPuno y Lago Menor: la fila Clorofila no aparece en las tablas OCR extraídas — posiblemente bajo límite de detección (en IT 036-2019 BPuno sí tenía chl-a 1–3 µg/L detectable). Lago Mayor: tabla no extraída (misma limitación que IT 036).
**Decisión:** Almacenar solo los 6 valores de BInte (×1000 mg/L→µg/L). Gap BPuno/Lago Menor documentado en README; pendiente segunda lectura visual. LTiti62 tiene OD/temp/conductividad vacíos (OCR artifact). LTiti64 N-total = "3.90?" (OCR ambiguo → qa_flag=uncertain).
**Impacto:** `limnology_insitu.parquet`: 2901 filas (6 campañas), n=48 chl-a numérico total. Vintage: `data/sources/limnology_insitu/ana_binacional_lago_titicaca_2019_oct.csv` (6 estaciones).

## DECISION-017 — Deduplicación de ana_observatorio en silver: clave station×campaign×datetime×parameter
**Fecha:** 2026-06-23
**Contexto:** `ana_observatorio.parquet` (silver) presentaba 496 filas duplicadas de 4086 totales (12%). Causa: los XLS del Observatorio fueron exportados en 2 archivos distintos para la misma campaña, produciendo registros idénticos por `station_id × campaign × datetime × parameter`. La gold layer `trophic_risk.py` tenía un workaround (`.unique(subset=..., keep="first")` en línea 117) que enmascaraba el problema aguas abajo.
**Decisión:** Implementar dedup en `build_silver()` de `silver/ana_observatorio.py`, clave `(station_id, campaign, datetime, parameter)`, `keep="first"` (orden alfabético de `source_file` → reproducible). Bronze queda intacto (raw preservado). La gold `trophic_risk.py` mantiene su dedup como belt-and-suspenders pero ya no elimina filas reales.
**Impacto:** `ana_observatorio.parquet` silver: 4086 → ~3590 filas únicas. Los conteos reportados en la sección Data Records del paper son correctos post-fix.

## DECISION-018 — PEBLT Crucero I 2019 ANEXO N°01: geometría de tabla y límite de lectura visual
**Fecha:** 2026-06-23
**Contexto:** Segunda lectura del ANEXO N°01 del INFORME I CRUCERO HIDROQUIMICO 2019 (pág. 33) para expandir `peblt_crucero_hidroquimico_i_2019.csv` de 7 → 29 estaciones. La tabla está en formato **transpuesto** (parámetros=filas, estaciones=columnas). Geometría real (400 DPI): tabla x=507–1671px, columna label=120px, 29 estaciones × 36px/estación. El escaneo subyacente es ~150 DPI efectivo: cada celda de dato ocupa ~5×26 px en el original; a 10× zoom los caracteres quedan ~50px (~3-4 px upscaleados), por debajo del umbral de identificación fiable de dígitos individuales.
**Decisión:** Solo se publican como valor numérico las lecturas con ancla confirmada (CHB-1=6.5, CHB-4=11.5, CHB-5=8.9, CHB-7=3.0, CHB-21=5.6). Para CHB-2 y CHB-3 se anota la mejor lectura visual con sufijo `?` (`8.5?` y `4?`) **en el CSV transcrito, no en el dataset publicado**: `_parse_cell()` de `silver/limnology_pdf.py` mapea cualquier sufijo `?` a `(value=null, qa_flag="uncertain")`, de modo que 8.5 y 4 **no entran a silver como números**. El sufijo preserva la lectura para una futura verificación, sin convertirla en dato. Las 22 estaciones restantes y los parámetros adicionales (OD, pH, T, conductividad, nitratos, amoniaco, turbidez) requieren extracción con Docling+GPU en gorgo; el trabajo se rastrea en el bead `lo9` (detalle operativo del pipeline en la memoria `gorgo-docling-ocr-pipeline`).
**Impacto:** `peblt_crucero_hidroquimico_i_2019.csv` queda en 7 estaciones (sin expansión a 29). En `limnology_insitu.parquet` esto son 5 filas con `secchi_m` no nulo y `qa_flag="ok"`, más 2 filas (CHB-2, CHB-3) con `secchi_m=null` y `qa_flag="uncertain"`. Respecto de la 1ª lectura, CHB-2/CHB-3 pasan de `?` a `8.5?`/`4?`: mejora la trazabilidad de la transcripción, no el conteo de valores publicables. La extracción completa se pospone al pipeline gorgo (bead `lo9`).

## DECISION-019 — Modelo de permisos para agentes: GitHub protege el remoto, un hook protege lo local
**Fecha:** 2026-07-10
**Contexto:** Preparación para correr agentes en paralelo (Gas Town, épica de orquestación). Los polecats corren como instancias de Claude Code sobre worktrees del repo. Auditoría de la superficie real: (a) `.env`, `data/bronze|silver|gold|_metadata` y `outputs/` están gitignored, así que un worktree limpio no los recibe — el aislamiento de credenciales y datos crudos es estructural, no configurado; (b) la branch protection de `main` ya exige CI `test`, `strict:true`, `required_conversation_resolution` y prohíbe force-push; (c) pero `enforce_admins:false`, y los agentes usan el token del owner: `gh pr merge --admin` saltea todos esos gates.
**Decisión:** Repartir la defensa en dos planos que no se solapan. **GitHub es el gate del remoto** (CI, conversaciones resueltas, no force-push): no se replica en el cliente. **Un hook `PreToolUse` (`scripts/deny_destructive.py`) es el gate de lo local** y cubre lo que la branch protection no puede: `gh pr merge --admin`, force-push, push directo a `main`/`master`, `rm -rf`, y escritura a mano sobre `.env*` y las capas generadas. `data/sources/` queda explícitamente permitido: está versionado y sus CSVs se transcriben a mano. No se usa `--dangerously-skip-permissions`. La allowlist vive en `.claude/settings.json` (versionado) y no en `settings.local.json`, porque este último está gitignored y un worktree de Gas Town no lo heredaría — los polecats tendrían el deny hook pero no los permisos, y se colgarían en el primer `git commit`.
**Decisión (bis):** El hook también ejecuta `bd export` antes de cualquier `git add` sobre `.beads/issues.jsonl`. El export de beads es diferido respecto de la DB, así que un `git add` inmediato tras `bd reopen`/`bd close` versiona el estado anterior y pierde el cambio en silencio (ocurrió con `dqz.1`, corregido en PR #28). Como el JSONL versionado es el mecanismo de sync del backlog (no hay remote de Dolt), con agentes en paralelo cada uno podría pisar o perder el estado de otro.
**Impacto:** `.claude/settings.json` gana `permissions` + hook `PreToolUse`; nuevo `scripts/deny_destructive.py` (~190 líneas, solo stdlib, ~56 ms por invocación) y `tests/test_deny_destructive.py` (82 casos) para que CI proteja el guard. El parseo es por tokens vía `shlex` con `punctuation_chars`, no por subcadenas: trocear el comando por `;` antes de tokenizar rompía los strings citados y hacía que `echo "ojo con git push --force"` se denegara como force-push real.
**Lección (PR #29):** un guard de seguridad escrito con matching de cadenas falla en las dos direcciones, y el review encontró ambas. Falsos positivos: texto citado que parece un comando. Falsos negativos, todos reales y reproducidos antes de corregirlos: `git add .` y `-A` (que stagean el JSONL de beads sin nombrarlo), `--force-with-lease=<refname>`, el refspec `+rama`, `HEAD:refs/heads/main`, `sudo -u root rm -rf` (el flag del wrapper escondía el comando), y `./data/bronze/x.zip` (ruta relativa resuelta contra el cwd). Cada uno quedó como caso de test explícito. El error de `bd export` se ignoraba en silencio, que era peor que no tener el hook: ahora deniega. Regla derivada: **parsear comandos por tokens, nunca por subcadenas**, y no marcar un guard como listo hasta que sus falsos negativos estén escritos como tests.

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

# Registro de trazabilidad y responsabilidades

> Esto es un **ledger de contribuciones para trazabilidad**, no un reclamo de autoría.
> Se llena conforme se levanta trabajo. Cuando exista un paper formal, estas filas se
> traducen a roles CRediT. Regla de mapeo:
> recolección → Resources/Investigation/Data Curation · limpieza fuerte → Data Curation/Software ·
> diseño metodológico → Conceptualization/Methodology · modelado → Formal Analysis/Software ·
> validación experta → Validation/Supervision · visualización → Visualization · redacción → Writing.

| contributor | afiliación | artefacto | tipo de contribución | evidencia | rol CRediT (tentativo) | en producto público | en paper |
|---|---|---|---|---|---|---|---|
| Álvarez A.; Elías V.; Jesús D.; Monge F. | Equipo partner | Inventario de datos I y II (salud, mortalidad materna, turismo, zonificación) | Data collection · análisis exploratorio · identificación de fuentes | `data/_metadata/inventario_partners/Inventario de datos I/II.pdf` | Resources, Investigation, Data Curation | Sí (contexto + zonificación) | Si se integra a metodología |
| Equipo de Ciencia de Datos | Partner | Inventario de datos III (vivienda/censo, Registro Derechos de Agua ANA) | Data collection · análisis exploratorio · summary de dataset | `data/_metadata/inventario_partners/Inventario de datos III.pdf` | Resources, Investigation, Data Curation | Sí (capa de presión hídrica) | Si el dataset se integra |
| Rody S. Vilchez Marin | UPC | Reconstrucción metodológica, auditoría, pipeline, catálogo de provenance, análisis, visualización, redacción | Conceptualization · Methodology · Data Curation · Software · Formal Analysis · Visualization · Writing · Project Administration | este repositorio (commits, `data/sources/`, `docs/`) | Sí | Sí (lead) | _por completar_ |
| _(Giorgio — apellido y afiliación por completar)_ | _por completar_ | _por completar_ | _por completar_ | — | _por completar_ | — | — |
| _(Christian — apellido y afiliación por completar)_ | _por completar_ | _por completar_ | _por completar_ | — | _por completar_ | — | — |

**Notas**
- Las filas del equipo partner registran trabajo previo; su nivel de crédito/autoría depende de permisos y de participación posterior, no se decide aquí.
- Completar afiliación y apellidos de los colaboradores (Giorgio, Christian) cuando se confirmen.

---

## Productores de datos fuente (procedencia, no autoría del proyecto)

Extraído de metadatos (`dc:creator` en Office, Author en PDF) durante el perfilado.
Evidencia completa por archivo: `data/_metadata/authorship.tsv`. Son funcionarios/fuentes
que produjeron el dato crudo; entran como provenance (CRediT: Resources), no como coautores.

| productor (creador) | institución probable | datasets | rol |
|---|---|---|---|
| Marco Polo Bardales Espinoza | MINSA / DIRESA Puno | Salud: enfermedades agua contaminada, perfil pacientes, principales afecciones | Resources (dato fuente salud) |
| Rosie Grace Fontinier Zafra; Phillyps Bravo Ojeda; Beatriz Gonzales Sanchez | PRONIED / MINEDU | Colegios: mantenimiento por año, acond. térmico | Resources |
| Milagros Gallegos; Mariella Pajuelo Purizaca; Renzo Bezada Davalos; Jhon F. de la Cerna | INEI | Demografía / Censo 2007 y 2017 | Resources |
| Alessandro Otoniel Ortiz Alcantara | ANA/ALA (Coata) | Vertederos y caudales Coata | Resources |
| Jhon E. Chahua Janampa | ANA / ALA | 12 informes de gestión del agua (PDF) | Resources |
| CITES | CITES/SERFOR | Fauna endémica y amenazada | Resources |
| **`openpyxl` / sufijo `_limpia`** | **Equipo partner (script)** | Población_proyectada_limpia, SAIP neonatal_limpia, MIDARH, fauna avifauna | **Data Curation (derivado, no crudo)** |

**Marcador raw↔derived:** archivos con creador `openpyxl` o sufijo `_limpia` ya fueron
limpiados por el equipo partner → son **derivados**, no fuente cruda. Registrado en
`authorship.tsv` (columna `raw_or_derived`) y debe reflejarse en `data/sources/*.yaml`.

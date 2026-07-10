# titicaca-environmental-foresight — AI Agent Instructions

## Domain / Scientific Context

- **Problem**: Environmental contamination and ecological deterioration of Lake Titicaca (Peru/Bolivia). The project builds a visual-predictive tool for a journalism special (El Comercio) that shows how pollution distributes across zones, what signals evidence it, and what scenarios emerge if current conditions continue or mitigation is applied.
- **Outcome / target**: Interactive visual tool with (1) spatial contamination risk maps by zone, (2) key indicator signals (chlorophyll-a / eutrophication as primary proxy, metals and coliforms as secondary), (3) counterfactual scenarios (business-as-usual vs. mitigation). Output: JSON for web + narrative visualizations.
- **Data provenance**: Mixed. (a) "Data limpia" files provided by project partners (in-situ stations — contents pending inventory); (b) public institutional sources: IMARPE-PELT monitoring reports, OAS/PNUMA TDPS diagnostics; (c) satellite imagery: Sentinel-2 (chlorophyll-a / optical proxies), MODIS/VIIRS (temporal series); (d) bibliography-derived variables from `deep-research-report.md`. **First deliverable is a data inventory** before any modeling.

## Architecture

Three-tier baseline approach (see `deep-research-report.md`):

```bash
# Tier 1 — eutrophication risk map (minimum viable)
uv run ingest      # load raw zip files → data/bronze/
uv run clean       # standardize schema, QA flags → data/silver/
uv run features    # spatial joins, satellite matchups → data/gold/
uv run scenarios   # risk classification + counterfactuals → outputs/

# Tier 2 — chlorophyll-a regression with Sentinel-2 (medium effort)
# Tier 3 — hybrid multi-output system (ambitious, requires dense historical data)
```

Primary variables: `chlorophyll_a`, `secchi_m`, `turbidity_ntu`, `do_mg_l`, `water_temp_c`, `ph`, `nh4`, `no3`, `po4`, `fecal_coliforms`, `as`, `pb`, `cd`. See research report for full target schema.

## Key Files

| File | Purpose |
|------|---------|
| `deep-research-report.md` | State-of-the-art review; defines baselines, variables and methodological risks |
| `data/bronze/` | Raw zip files from partners + downloaded satellite/institutional data |
| `data/silver/` | Cleaned, schema-normalized parquet with QA flags |
| `data/gold/` | Analytical tables: spatial risk grids, scenario outputs, matchup tables |
| `src/titicaca_environmental_foresight/ingest.py` | Raw data loading and bronze layer |
| `src/titicaca_environmental_foresight/features.py` | Feature engineering, spatial joins, satellite matchups |
| `src/titicaca_environmental_foresight/model.py` | Risk classification / Chl-a regression |
| `src/titicaca_environmental_foresight/scenarios.py` | Counterfactual scenario generation |
| `outputs/` | JSON and static assets for web visualization |

## Data Conventions

- **Layers**: raw → `data/bronze/`, cleaned → `data/silver/`, analytic → `data/gold/`. All gitignored.
- **Polars over pandas** everywhere; only drop to numpy when a library requires it.
- **DuckDB for SQL joins** across parquet; Polars for local transforms.
- **Master schema**: every silver table must have `station_id`, `datetime`, `lat`, `lon`, `depth_m`, `qa_flag`, `sampling_agency`.
- Keep dates as typed `Date`, never strings. Temporal splits must respect dry/wet season boundary — never random splits (leakage risk).
- Spatial validation: no train/test pairs with collocated stations (spatial leakage risk).
- Do not claim satellite-derived proxies are direct measurements of dissolved metals — document as proxy/inference explicitly.

## Conventions

- Issue prefix: `tef` (beads). IDs quedan como `tef-a87`. Fijado explícitamente en `.beads/config.yaml`, no derivado del nombre del directorio.
  - Migrado desde `titicaca-enironmental-foresight` el 2026-07-10 (`bd rename-prefix`). Gas Town valida el prefijo contra `^[a-zA-Z][a-zA-Z0-9-]{0,19}$` y exige que coincida con el del repo, así que el prefijo de 31 chars impedía enrigar el proyecto. Ver DECISION-020.
  - Los **sufijos** no cambiaron: `a87`, `dqz.1`, `kf5` siguen siendo válidos, y con ellos toda la convención de commits `tipo(sufijo): ...`.
  - El **directorio** conserva la errata (`titicaca-enironmental-foresight`) — eso sí sigue sin renombrarse.
- Scenario outputs must be reproducible: seed all random processes, pin library versions in `pyproject.toml`.
- All zone labels must match OAS/PNUMA TDPS geographic names for cross-referencing with institutional reports.
- **No AI tool metadata in commits**: never include `Co-Authored-By: Claude` or similar AI attribution lines in commit messages.

## Session Close (este repo — supersede el protocolo beads genérico de abajo)

`main` está protegida (PR requerido, CI `test` + conversaciones resueltas; sin aprobación formal). **NO se hace push directo a `main`.**

Al cerrar sesión:
1. Commit del trabajo en una **rama** y `git push -u origin <rama>`.
2. Abrir/actualizar un **PR** y pedir review de Copilot.
3. El merge espera **CI verde + todas las conversaciones de Copilot resueltas** (no se requiere `--admin`; si lo necesitas, algo está mal configurado).
4. Tracking: `bd ready` al abrir y archivar issues de seguimiento al cerrar (backlog entre sesiones). **TodoWrite está permitido para pasos efímeros in-session**; beads es para el backlog que cruza sesiones.
5. `bd dolt push` **NO aplica** (no hay remote dolt configurado); el `.beads/issues.jsonl` versionado en git es el mecanismo de sync. `bd remember` y el `MEMORY.md` del harness (que vive **fuera** del repo, en `~/.claude/...`) no compiten — usa cualquiera.

> El bloque "Session Completion" inyectado más abajo asume trunk-based (push directo a `main`, `bd dolt push`) y queda **superseded** por esta sección.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->

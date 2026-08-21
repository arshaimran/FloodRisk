# FloodRisk codebase — technical documentation

## Scope and current architecture

This repository scores a portfolio of insured sites for flood risk in Pakistan.  It combines Earth Engine hazard/terrain/rainfall sampling, reverse geocoding, an explainable rule-based riverine/pluvial score, and historical claims validation. The model's primary deliverable is `outputs/sites_scored.csv`; a Streamlit dashboard consumes that file. Claims are deliberately split into pre-2024 history (permitted as model evidence) and 2024 holdout data (evaluation only).

All paths below are absolute relative to the repository root `C:\Users\arsha\Desktop\FloodRisk` (abbreviated as `<root>`). The `.venv/` directory is an installed environment and is not project source.

## Data-flow and recommended execution order

```text
<root>/data/sites_input.csv
  └─ scripts/pull_hazard_data.py ──Earth Engine export, manually downloaded──>
     <root>/outputs/hazard_export.csv
       └─ scripts/merge_locations.py ────────────────────────────────────────>
          <root>/outputs/sites_with_cities.csv
             ├─ scripts/eda.py ────────────────────────────────> outputs/eda_figures_claude/*
             ├─ scripts/compute_bin_edges.py ──────────────────> console percentile evidence
             └─ scripts/risk_score.py ─────────────────────────>
                <root>/outputs/sites_scored.csv
                  ├─ scripts/validate_against_claims.py + historical claims ──>
                  │  claims_matched_history.csv / unmatched_claims_history.csv /
                  │  validation_summary_history.txt
                  ├─ scripts/build_claims_features.py ──────────>
                  │  sites_with_claims_features.csv + claims feature reports
                  │       └─ scripts/risk_score.py (second run) ─> sites_scored.csv
                  ├─ scripts/validate_holdout_2024.py ──────────>
                  │  claims_matched_holdout_2024.csv / unmatched_claims_holdout_2024.csv /
                  │  validation_summary_holdout_2024.txt
                  ├─ scripts/check_drainage_claim_cities.py ────> drainage_check_claim_cities.csv
                  └─ scripts/dashboard.py ─────────────────────> interactive application

<root>/data/claims.csv
  └─ scripts/split_claims_by_date.py ──>
     claims_history_to_2023.csv ──> historical validation / feature creation
     claims_holdout_2024.csv ────> holdout-only validation

unattributed_fanned_claims_history.csv + claims_matched_history.csv
  └─ scripts/resolve_fanned_claims.py ──> fanned_claims_suggestions.csv
     (human confirmation required) ──> manual_fanned_claim_resolutions.csv
       └─ used by validation and claims-feature creation

<root>/data/aqueduct_coastal/**/*
  └─ scripts/extract_coastal_rp.py ──> outputs/coastal_rp_samples.csv
     (currently an independent exploratory coastal pathway; not merged into scoring)
```

`normalize_headers.py` is a maintenance utility that may be run before any CSV-dependent stage. `inspect_scores.py`, `inspect_risk_score_content.py`, and `diagnostic_evidence_gate.py` are read-only diagnostics normally run after scoring. Files with non-`_history` names in `outputs/` are legacy/current artifacts but are not the configured inputs of the history/holdout pipeline.

## Shared path configuration — `project_paths.py`

**Purpose.** Centralizes repository paths so the principal validation and feature scripts agree on their historical-claims filenames. `BASE_DIR`, `DATA_DIR`, and `OUTPUTS_DIR` resolve from the module's own location, avoiding dependence on the caller's current directory.

**Configured inputs/outputs.** The principal site file is `<root>/outputs/sites_scored.csv`; historical claims are `<root>/data/claims_history_to_2023.csv`. Historical validation writes `<root>/outputs/claims_matched_history.csv`, `unmatched_claims_history.csv`, and `validation_summary_history.txt`. Feature creation writes `city_claim_rates_history.csv`, `repeat_claim_clients_history.csv`, `repeat_claim_sites_history.csv`, `unattributed_fanned_claims_history.csv`, and `sites_with_claims_features.csv`. Optional human mappings are read from `<root>/outputs/manual_fanned_claim_resolutions.csv`; caches are `<root>/outputs/cache/` and `outputs/waterway_cache/`.

**Function: `ensure_outputs()`.** Creates `outputs/`, `outputs/cache/`, and `outputs/waterway_cache/` recursively if absent. It exists to make validation writes reliable without requiring manual setup; it does not create source data or validate their schemas.

## Pipeline scripts

### `scripts/pull_hazard_data.py`

**Purpose.** Authenticates to Google Earth Engine (EE), constructs a combined raster stack, samples it at insured-site points, and either writes a small synchronous test extract or starts a full asynchronous Drive export. It intentionally does not score risk; extraction is separate from policy logic.

**Inputs.** Reads `<root>/.env` for `EE_PROJECT_ID`, `<root>/data/sites_input.csv` for `Site_ID`, `Client`, `Latitude`, `Longitude`, and `net_sum_insured`, and the EE datasets JRC/CEMS GLOFAS FloodHazard v2.1, Global Flood Database MODIS Events V1, MERIT Hydro v1.0.1, and CHIRPS Daily. **Outputs.** With `TEST_MODE=True`, writes `<root>/outputs/sites_with_hazard.csv`. With the current `TEST_MODE=False`, it starts EE task `hazard_export_new`, which writes a CSV to the user's Google Drive; that download must be placed at `<root>/outputs/hazard_export.csv` for the next script. No local file is produced in production mode.

**Constants and rationale.** `TEST_MODE=False` selects EE's scalable asynchronous exporter for the roughly 2,335-site run; the synchronous `getInfo()` route is only safe for small tests. Sampling uses `scale=90` metres and `tileScale=16`, respectively matching a practical hazard sampling resolution and increasing EE tile partitioning to reduce large-job failures. Rainfall uses 2005-01-01 through 2025-12-31 and June–September, providing a long, monsoon-specific p95 extreme-rainfall indicator rather than an unstable single maximum. Local relief is elevation minus the 1-km focal minimum, a local-depression proxy. Missing/unsampled values are unmasked to `0`, except elevation, relief, and HAND use `-9999` to distinguish no land terrain data from a real zero.

**Function: `init_earth_engine()`.** Loads environment variables, requires `EE_PROJECT_ID`, calls `ee.Initialize(project=...)`, and returns the project id. This explicit guard prevents an export being launched against an unintended/default EE project.

**Function: `load_datasets(verify=True)`.** Builds the multi-band EE image: RP10/RP100/RP500 JRC depth, summed MODIS historical flood hits, MERIT elevation/HAND/local relief, and CHIRPS monsoon p95/max rainfall. Optional band-name inspection verifies dataset availability in test mode; returning one combined image ensures all layers are sampled consistently at the same points.

**Function: `build_feature_collection(sites_df)`.** Converts each site dataframe row into an EE point feature while retaining the site identifier, client, and insured value as properties. This is necessary for `sampleRegions` to carry business identifiers through to the export.

**Function: `run_test_mode(sampled)`.** Calls EE `getInfo()` synchronously, turns the returned feature properties into a dataframe, and returns it. It supplies immediate inspection for a tiny sample but is deliberately unsuitable for the full portfolio due to synchronous API limits.

**Function: `run_production_export(sampled, description="hazard_export_new")`.** Creates and starts an EE `Export.table.toDrive` CSV task and returns the task object. It makes a production request non-blocking, leaving task monitoring and download as an explicit operator responsibility.

**Function: `main()`.** Orchestrates authentication, site loading, layer construction, point sampling, and the test-versus-production branch. It creates the local output directory only on the test-write branch because the production artifact exists first in Drive.

### `scripts/merge_locations.py`

**Purpose.** Restores coordinates to the downloaded EE export and derives city, province, and country labels via offline `reverse_geocoder`; these geography columns support scoring output, claims matching, EDA, and the dashboard.

**Inputs/outputs.** Reads `<root>/outputs/hazard_export.csv` and `<root>/data/sites_input.csv`; writes `<root>/outputs/sites_with_cities.csv`. It requires `Site_ID` in both files and latitude/longitude in the site input.

**Function: `main()`.** Left-joins source coordinates onto EE samples by `Site_ID`, reverse-geocodes every coordinate pair with `mode=1`, assigns returned `name`, `admin1`, and country code to `city`, `province`, and `country`, then writes the enriched site table. `mode=1` avoids Windows multiprocessing issues; there are no geographic confidence checks or manual overrides in this script.

### `scripts/risk_score.py`

**Purpose.** Implements the current explainable, evidence-gated site score (documented in its header as v4, with v5 percentile logic comments). It produces separate riverine and pluvial scores, takes an evidence-aware final tier, marks coastal/no-terrain sites separately, and optionally incorporates historical-claims features.

**Inputs/outputs.** Reads `<root>/outputs/sites_with_cities.csv`; optionally reads `<root>/outputs/sites_with_claims_features.csv` and merges `city_claim_rate`, `repeat_claim_site`, `repeat_claim_client`, and `has_history_claim` by `Site_ID`; writes `<root>/outputs/sites_scored.csv`. Required hazard columns include `RP100_depth`, `RP500_depth`, `hand_m`, `elevation_m`, `local_relief_m`, `historical_flood_hits`, and `monsoon_p95_rainfall_mm` (plus identity/geographic data carried through).

**Constants and rationale.** `HAND_SAFE_THRESHOLD=50 m` suppresses only negligible riverine scores at sites far above drainage. `RELIEF_SAFE_THRESHOLD=3 m` is the evidence gate: it was loosened from 1 m because 13 of 17 v3 claims-based false negatives fell between 1 and 3 m. Riverine RP100 cutoffs are `0`, `0.5`, `1.5`, `2.5942` (portfolio nonzero 90th percentile), and `3.50447` (97th percentile); top bins were calibrated from 524 nonzero portfolio values, with 90th–97th treated as score 3 and >=97th as score 4. Pluvial rainfall cutoffs are `10`, `20`, `33.62616` (90th), and `39.567738` mm (97th) from 2,334 nonzero values; the lower thresholds remain unretuned because claims were too few and fell in expected bands. `-9999` always means missing terrain/coastal data, never low relief.

**Function: `riverine_score(rp100, rp500, hand_m)`.** Returns 0–4 from RP100 depth, with missing values returning `NaN`; RP500 is required but not otherwise used in the present calculation. It zeroes an otherwise 0/1 score when HAND exceeds 50 m, preventing minor modeled depth from outweighing strong vertical separation from drainage.

**Function: `relief_modifier(local_relief_m)`.** Maps usable relief to `+2` below 1 m, `+1` below 3 m, `0` below 8 m, and `-1` otherwise; `-9999` yields 0. It is a localized depression adjustment retained for explainability, although the active pluvial calculation directly applies only the <0.5/<1 portions.

**Function: `has_relief_evidence(local_relief_m)`.** Returns true only for non-sentinel relief below 3 m. It centralizes the pluvial vulnerability test so scoring and final-score gating cannot silently drift apart.

**Function: `pluvial_score(monsoon_p95_mm, local_relief_m, historical_hits, repeat_claim_site=False, repeat_claim_client=False)`.** Buckets monsoon p95 rainfall into 0–4, but caps it at 1 unless there is corroboration from a historical hit, low relief, or repeat site/client claims. With evidence it adds 2 for relief <0.5 m or 1 for <1 m and caps at 4, embodying the assumption that rainfall hazard alone is insufficient evidence of site pluvial vulnerability.

**Function: `dominant_hazard(riverine, pluvial)`.** Labels the larger valid component Riverine or Pluvial, ties as Combined, and incomplete values as Unknown. This is explanatory metadata rather than an additional scoring input.

**Function: `tier_from_evidence(final_score, riverine_score, pluvial_score, historical_hits, repeat_claim_site=False, repeat_claim_client=False, has_history_claim=False)`.** Assigns the business tier. At least two satellite hits or any repeat-claim flag force Critical; otherwise score >=4 becomes Critical with any evidence and High without it, 3 is unconditionally High, 2 is High only with evidence, 1 is Medium only with evidence, and 0 is Low. Evidence counts one satellite hit, claims flags, any historical claim match, and agreement where both component scores are >=2.

**Function: `apply_live_conditions(base_tier, current_rainfall_mm=None, active_alert=None)`.** Returns the base tier plus either a no-live-data message or a placeholder message. It defines the future integration surface but does not currently use rainfall or alerts to modify risk.

**Function: `score_site(row)`.** Applies validation and coastal handling before computing component scores, the evidence-gated final score/tier, dominant hazard, and an evidence-consistent human-readable reason. Missing required hazard inputs become `Insufficient Data`; sentinel HAND/elevation becomes the dedicated coastal/storm-surge assessment tier.

**Function: `main()`.** Loads city-enriched sites, conditionally merges claims features (otherwise defaults them to false/zero), applies `score_site` row-wise, reports distributions, sorts from Critical through insufficient data, and writes the scored portfolio. The claims feature loop requires running scoring once before historical feature construction and again after it.

### `scripts/split_claims_by_date.py`

**Purpose.** Enforces the temporal separation between claims used to construct features and claims used for an honest holdout assessment.

**Inputs/outputs.** Reads `<root>/data/claims.csv`; writes `<root>/data/claims_history_to_2023.csv` and `<root>/data/claims_holdout_2024.csv`, each with `validation_split` added.

**Constant and rationale.** `CUTOFF=2024-01-01`; loss dates before it are HISTORY and dates on/after it are HOLDOUT. This prevents 2024 outcome information from entering the current model evidence.

**Function: `main()`.** Requires `Loss Date`, parses it day-first, rejects every unparseable row with CSV row numbers, labels the two time partitions, and writes them. Strict failure is appropriate because an ambiguous date could leak a claim across the evaluation boundary.

### `scripts/validate_against_claims.py`

**Purpose.** Matches flood-relevant claims to scored portfolio clients, records candidate sites and risk tiers, detects multi-site fan-out, and writes both validation diagnostics and unresolved claims for review.

**Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv`, `<root>/data/claims_history_to_2023.csv`, and optionally `<root>/outputs/manual_fanned_claim_resolutions.csv`; writes `<root>/outputs/claims_matched_history.csv`, `unmatched_claims_history.csv`, and `validation_summary_history.txt`. The same code is reused by the holdout wrapper with 2024-specific paths.

**Constant and rationale.** `MATCH_THRESHOLD=85` on RapidFuzz token-sort ratio. A candidate below this 0–100 threshold is deliberately emitted as unmatched rather than trusted silently. Claim relevance accepts only `flood_relevant == Yes`; `Maybe` is reported but excluded, preventing ambiguous loss causes from becoming model evidence. Deduplicated tier severity ranks Critical, High, Medium, Low, Coastal, Insufficient Data, so an unresolved multi-site claim is represented once by its worst plausible tier.

**Function: `normalize(name)`.** Uppercases and removes selected legal-suffix/punctuation variants from client names. It increases fuzzy-match robustness for ordinary naming differences while intentionally leaving low-confidence cases for manual review.

**Function: `main()`.** Ensures output directories, loads sites/claims, supplies `Yes` only if the relevance column is absent (with a warning), applies optional human claim-to-site resolutions, and fuzzy-matches each remaining relevant client to all portfolio sites of the best normalized client. It writes full matched/unmatched data, calculates raw and fan-out-deduplicated tier distributions, high/critical capture ranges (unambiguous primary; all-candidate conservative/optimistic secondary), lists false negatives, and emits a relief-threshold diagnostic for them.

### `scripts/validate_holdout_2024.py`

**Purpose.** Runs the validator against the frozen 2024 holdout only and states that its outputs must never become feature inputs.

**Inputs/outputs.** Imports `validate_against_claims.py`, then temporarily sets shared paths to read `<root>/data/claims_holdout_2024.csv` and write `<root>/outputs/claims_matched_holdout_2024.csv`, `unmatched_claims_holdout_2024.csv`, and `validation_summary_holdout_2024.txt`; it still reads `<root>/outputs/sites_scored.csv` and optional manual resolutions.

**Functions.** It declares no functions. Its module-level path reassignment is intentional dependency injection: invoking `validator.main()` reuses precisely the same matching and metric logic as history without duplicating or modifying it.

### `scripts/build_claims_features.py`

**Purpose.** Converts historical matched claims into conservative site/client evidence. It fixes a former fan-out bug by treating `(Insured/Participant, Loss Date)` as the real claim identity before counting sites or cities.

**Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv`, `<root>/outputs/claims_matched_history.csv`, and optional `<root>/outputs/manual_fanned_claim_resolutions.csv`. Writes `<root>/outputs/city_claim_rates_history.csv`, `repeat_claim_clients_history.csv`, `repeat_claim_sites_history.csv`, `unattributed_fanned_claims_history.csv`, and `sites_with_claims_features.csv`.

**Constant and rationale.** `FLOOD_ONLY=True` retains only claims marked `flood_relevant=Yes` when the field is available. Repeat client/site thresholds are >=2 distinct claims: one loss is insufficient recurrence evidence; repeat-client counts remain valid under fan-out whereas repeat-site and city-rate calculations use only unambiguous claims. Claims are uniquely keyed by trimmed client plus loss date, an operational identity assumption chosen to collapse the known same-client multi-site expansion.

**Function: `main()`.** Loads inputs and its nested manual-resolution loader, normalizes city/client/date strings, applies valid mapping rows, counts candidate sites per true claim, and segregates fanned claims. It writes fanned claims for resolution; derives repeat clients from all true claims, city rates as unambiguous distinct claims divided by portfolio site count, repeat sites from unambiguous claims only, and merges those flags/rates plus a broad `has_history_claim` flag back onto every scored site.

**Nested function: `load_manual_resolutions(client_col, loss_date_col)`.** If the manual file exists, normalizes possible trailing-space headers, requires `Site_ID`, creates a client/date key, rejects duplicate keys, and returns mappings indexed by that key. It is nested because it is used solely in this one feature-build run; uniqueness protects against contradictory human decisions.

### `scripts/resolve_fanned_claims.py`

**Purpose.** Produces review suggestions for fanned historical claims; it never automatically alters matching or features.

**Inputs/outputs.** Reads `<root>/outputs/claims_matched_history.csv` and `<root>/outputs/unattributed_fanned_claims_history.csv`; writes `<root>/outputs/fanned_claims_suggestions.csv`. Confirmed human decisions must separately be entered into `<root>/outputs/manual_fanned_claim_resolutions.csv` with client, loss date, and `Site_ID`.

**Function: `main()`.** For each fanned claim, gathers candidate site rows, concatenates available `REMARKS` and cause-of-loss text, and searches each candidate city as a word-bounded keyword. Exactly one city match becomes a high-confidence-but-confirm-required Site_ID suggestion; multiple or no matches remain low/no confidence, preserving human judgment for consequential attribution.

### `scripts/check_drainage_claim_cities.py`

**Purpose.** Tests, rather than operationalizes, the hypothesis that sites with claims lie closer to OpenStreetMap waterways than non-claim sites in the same city.

**Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv` and `<root>/outputs/claims_matched_history.csv`, writes incremental and final results to `<root>/outputs/drainage_check_claim_cities.csv`, and reads/writes GeoJSON cache files under `<root>/outputs/waterway_cache/<normalized-city>.geojson`. It also queries OSM live through OSMnx.

**Constants and rationale.** Waterway types are `river`, `canal`, `stream`, `drain`, and `ditch` to cover natural and drainage pathways. `MAX_CITIES=9` bounds the initial exploratory run to cities with the most claims. A ±0.08-degree (~8–9 km) coordinate buffer avoids excluding a nearby waterway just outside the portfolio site's bounding box. Three attempts with 15-second backoff balance transient OSM failure against a bounded run; timeout is 300 seconds. Longitude <68 uses UTM 42N and otherwise UTM 43N, a sufficient city-scale Pakistan approximation.

**Function: `utm_for(lon)`.** Selects the approximate Pakistan UTM CRS from longitude, enabling metre-distance calculations rather than misleading degree distances.

**Function: `fetch_waterways(city_key, north, south, east, west, retries=3, backoff_seconds=15)`.** Reuses a cached GeoJSON if available; otherwise queries OSM with the site-derived bounding box, keeps valid geometry/type, caches it, and retries failures. Bounding boxes deliberately replace fragile place-name polygon geocoding.

**Function: `nearest_distance(lat, lon, waterways_proj, utm_crs)`.** Projects one site point into the selected UTM CRS, finds the nearest waterway geometry, and returns distance in metres rounded to one decimal plus its type.

**Function: `main()`.** Normalizes cities, selects the nine top claim-count cities, computes each scoped site's nearest waterway, flags claim-site membership, saves after each city, then prints within-city and pooled median comparisons. It is a descriptive comparison, not a statistical validation or scoring feature.

### `scripts/extract_coastal_rp.py`

**Purpose.** Samples local Aqueduct coastal inundation rasters at portfolio points for four coastal return periods. It is currently independent of `risk_score.py` and does not resolve the coastal tier.

**Inputs/outputs.** Reads `<root>/data/sites_input.csv` and searches recursively under `<root>/data/aqueduct_coastal/` for matching raster formats; writes `<root>/outputs/coastal_rp_samples.csv` with `coastal_RP2_depth_m`, `coastal_RP10_depth_m`, `coastal_RP100_depth_m`, and `coastal_RP1000_depth_m`.

**Constants and rationale.** `RPS` maps Aqueduct filename codes `rp0002`, `rp0010`, `rp0100`, and `rp1000` to clear output columns. The code searches `.tif`, `.tiff`, `.img`, `.vrt`, and `.nc` to tolerate provider packaging variations; it selects the first match, so version selection is not explicit.

**Function: `find_raster_for_rp(aqua_dir, rp_code)`.** Recursively searches the supported `inuncoast` filename patterns and returns the first raster or `None`. It isolates the variable dataset file naming from sampling logic.

**Function: `main()`.** Validates the site schema, initializes an all-NaN output, imports rasterio lazily, and for each discovered raster transforms WGS84 coordinates as needed, skips out-of-bounds/nodata/error samples, and writes valid values. If rasterio or rasters are absent it still emits a transparent NaN placeholder instead of inventing coastal data.

## Supporting and diagnostic scripts

### `scripts/normalize_headers.py`

**Purpose.** Normalizes leading/trailing whitespace in CSV headers throughout `<root>/data/` and `<root>/outputs/`, addressing legacy columns such as `Insured/Participant `.

**Inputs/outputs.** Reads every `*.csv` directly in those two directories. For each changed file it renames the original to the same path plus `.orig` (for example `data/claims.csv.orig`) if no backup exists, then rewrites the normalized CSV at the original path.

**Function: `normalize_file(path)`.** Attempts a string-preserving CSV read, compares original and stripped headers, creates the one-time backup, writes the revised header row, and returns whether it changed the file. It catches read errors and avoids needless rewrites.

**Function: `main()`.** Iterates the two existing target directories and calls `normalize_file` for sorted direct CSV entries, then reports the changed paths. This is the one intentionally mutating maintenance tool; it is not part of routine scoring.

### `scripts/compute_bin_edges.py`

**Purpose.** Prints descriptive percentiles for nonzero `RP100_depth` and `monsoon_p95_rainfall_mm`, providing the evidence used for the high score-bin cutoffs in `risk_score.py`.

**Inputs/outputs.** Reads `<root>/outputs/sites_with_cities.csv`; writes no file, only console output. **Functions.** It defines no functions; module-level code filters nonzero values and calls `describe` at 50th, 75th, 85th, 90th, 95th, 97th, and 99th percentiles. The 90th/97th results currently embedded in scoring make the highest categories rare portfolio-tail conditions.

### `scripts/eda.py`

**Purpose.** Generates exploratory tables and figures before/alongside model calibration, including distributions, correlations, city comparisons, and scatter plots.

**Inputs/outputs.** Reads `<root>/outputs/sites_with_cities.csv`; creates `<root>/outputs/eda_figures_claude/` at import/run time; writes `correlation_matrix.csv`, eight histogram PNGs where data permit, `boxplots_grid.png`, six city bar-chart PNGs, and two scatter PNGs there. **Constants and rationale.** `hazard_cols` specifies the eight core layers; `zero_heavy` uses nonzero-only histograms for RP depths and historical hits because zeros otherwise conceal their active distribution. Rows with `elevation_m` or `hand_m == -9999` are excluded from terrain/hazard plots to prevent coastal/no-data sentinels distorting statistics, while full data remains for exposure totals.

**Function: `save_bar(series, title, ylabel, filename)`.** Creates a consistently sized, labeled, rotated-axis bar chart in the EDA directory and closes it. It consolidates repeated plotting mechanics so all city charts are comparable.

### `scripts/dashboard.py`

**Purpose.** Supplies a four-page Streamlit interface: executive tier/exposure overview, interactive Folium map, filterable portfolio explorer, and descriptive analytics.

**Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv` via `project_paths.SITES_FILE`; renders a browser application and writes no project data files. It expects scoring/geography/exposure fields such as `risk_tier`, `net_sum_insured`, `province`, `Latitude`, `Longitude`, and component hazard columns.

**Constants and rationale.** `PLOTLY_TEMPLATE="plotly_dark"` and `TIER_COLORS` establish a consistent dark presentation and visual severity mapping. The map is centered on `[30.3, 69.3]`, a Pakistan-wide overview, at zoom 6. Analytics use 15 largest exposures and five histogram bins as compact default summaries rather than modelling choices.

**Function: `load_data()`.** Reads the scored CSV and is decorated with `@st.cache_data`, preventing repeated disk loads during Streamlit re-renders. Refreshing score data requires Streamlit cache invalidation/restart as appropriate.

### `scripts/inspect_scores.py`

**Purpose.** Quick console inspection of score output and a legacy `_combined` metric if present. **Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv`, writes nothing. **Functions.** None: it prints row count, `_combined` 50th/88th/98th quantiles and implied high/critical counts when that obsolete/intermediate column exists, otherwise notes its absence, then prints tier counts. The 88th/98th values are diagnostic legacy quantiles, not current `risk_score.py` thresholds.

### `scripts/inspect_risk_score_content.py`

**Purpose.** Source-level sanity check that locates tiering function references in the scoring script. **Inputs/outputs.** Reads `<root>/scripts/risk_score.py`; writes nothing. **Functions.** None: it prints the path, line count, and lines containing `tier_from`, `tier_from_score`, or `tier_from_evidence`, useful for checking which tiering implementation a file contains without executing it.

### `diagnostic_evidence_gate.py`

**Purpose.** Audits whether final-score-3 sites without counted corroborating evidence are nevertheless High, testing the explicit v5 rule that score 3 maps directly to High. **Inputs/outputs.** Reads `<root>/outputs/sites_scored.csv` using a working-directory-relative path and writes nothing. **Functions.** None: it computes an `evidence_count` from historical hits, repeat claims, and component-model agreement, then prints counts/tier distributions. Its evidence formula omits `has_history_claim`, so it is a simplified diagnostic rather than an exact duplicate of `tier_from_evidence`.

## Known limitations and deliberately deferred work

- **Unresolved fanned claims remain uncertain.** Fuzzy matching expands one claim to every site of a matching client. Feature creation excludes fanned claims from site and city signals; suggestions are not trusted until humans populate unique client/date/Site_ID mappings. `has_history_claim` is broader and can still mark all candidate sites.
- **Claim identity is an operational proxy.** `(Insured/Participant, Loss Date)` is assumed to denote one real claim. Multiple genuine same-client losses on the same date would be collapsed; client-name matching can still be wrong above the 85 threshold.
- **Historical claim relevance is manual/fragile.** `flood_relevant` must be curated as Yes/No/Maybe. If absent, the validator treats every claim as Yes after warning; Maybe is excluded rather than modeled.
- **Riverine pathway is unvalidated.** The code explicitly reports zero riverine claims in the current year's validation evidence; RP100/RP500/HAND logic should not be retuned until an external NDMA Sitrep or comparable riverine cross-check is completed. RP500 is required by `riverine_score` but currently does not affect its value.
- **Drainage proximity is not in scoring.** OSM testing showed weak/mixed evidence (documented pooled medians: claim sites 838 m vs non-claim sites 986 m, with inconsistent city direction). The exploratory run is capped to nine cities, depends on mutable OSM data, and uses median comparisons without statistical controls.
- **`city_claim_rate` is computed but unused.** It is merged into score input but never referenced in `score_site` or tiering because only a small number of claims resolve unambiguously and rates are too sparse to trust.
- **Coastal/storm-surge risk is deferred.** Sentinel terrain sites are classified as `Coastal/Marine - Requires Storm Surge Assessment`; extracted Aqueduct coastal return-period depths are not merged into sites or used to replace that tier.
- **No live-event adjustment exists.** `apply_live_conditions` is a placeholder; active alerts/current rainfall do not alter the base tier.
- **Hazard sampling has external/manual steps.** Full EE extraction writes to Google Drive and requires a manual download/placement as `hazard_export.csv`. Dataset availability, EE permission, and geographic sampling errors are not fully automated or version-pinned.
- **Geocoding has no QA/override layer.** Reverse geocoder assigns nearest labels with no confidence, spelling harmonization, or manual city correction. City string differences can cause drainage-city skips and claims-feature inconsistencies.
- **Risk calibration is partly portfolio-relative and small-sample.** The highest depth/rainfall thresholds derive from one portfolio's nonzero distribution; rainfall lower bins were deliberately left unchanged because the available claims sample is small and mostly pluvial. Validation text itself cautions that single-digit movements are noise.
- **Feedback-loop governance is procedural, not enforced.** History-derived features are meant to be built only from pre-2024 data and then rescored; scripts do not persist model version/provenance or prohibit someone from using holdout outputs manually.
- **Schema and runtime validation are incomplete.** Most scripts assume required columns; only some validate them. There are few/no automated tests, no formal data contract, and no reproducible run manifest.
- **Legacy/artifact ambiguity exists.** Some outputs lack the `_history` suffix (`claims_matched.csv`, `validation_summary.txt`, etc.), while configured code uses `_history` names. `pull_hazard_data.py` test output is `sites_with_hazard.csv`, but downstream expects manually downloaded `hazard_export.csv`; users must follow the documented handoff.
- **`normalize_headers.py` is only partly non-destructive.** It retains a `.orig` file but rewrites CSVs in place and will overwrite a normalized file when an existing backup is present; use deliberately, not as an automatic pipeline stage.
- **Dashboard limitations.** It renders one Folium marker per site and assumes non-null schema fields, so large portfolios or missing data can affect usability; its cached loader may show stale output until cache refresh.

## Runtime dependencies

`requirements.txt` names `earthengine-api`, `pandas`, and `python-dotenv`. Additional scripts require undeclared packages: `reverse_geocoder`, `rapidfuzz`, `numpy`, `osmnx`, `geopandas`, `shapely`, `rasterio`, `matplotlib`, `streamlit`, `plotly`, `folium`, and `streamlit-folium`. This discrepancy is a deployment limitation: a clean environment cannot run every script from `requirements.txt` alone.

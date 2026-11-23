# FloodRisk

FloodRisk is a Python project for assessing flood exposure at insured sites in Pakistan. It combines modeled river-flood hazard, terrain and drainage measures, monsoon rainfall, historical flood observations, and (when prepared) pre-2024 insurance-claims evidence. The main scoring output is `outputs/sites_scored.csv`, which can be explored in a Streamlit dashboard.

The score is an explainable decision-support assessment, not a deterministic forecast or a substitute for underwriting judgment. Rainfall and coastal return-period products are calculated separately for display and are not inputs to the current land-based risk score. See [methodology.md](methodology.md) for the scoring approach and limitations, and [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) for script-level details.

## Repository layout

- `scripts/` — hazard extraction, location enrichment, scoring, claims validation, analysis, and dashboard scripts.
- `data/` — local source datasets, including site and claims CSVs. These files are excluded from Git.
- `outputs/` — generated/intermediate data and reports. These files are excluded from Git.
- `project_paths.py` — shared project path configuration.
- `chatbot.py` — optional Gemini-powered question-answering interface for scored sites.
- `methodology.md` — detailed model methodology.
- `PROJECT_DOCUMENTATION.md` — technical pipeline documentation.

## Requirements

Use Python 3.10 or newer. Create an environment and install the base dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The checked-in `requirements.txt` is not a complete environment for every script. For example, location enrichment needs `reverse_geocoder`, while the dashboard needs Streamlit, Plotly, Folium, and `streamlit-folium`. Other analysis scripts may require their own libraries. Install the dependencies for the scripts you plan to run.

## Data and configuration

The pipeline expects private/local files that are not included in this repository:

- `data/sites_input.csv` with at least `Site_ID`, `Client`, `Latitude`, `Longitude`, and `net_sum_insured`.
- `data/claims.csv` for claims partitioning and validation, when using the claims workflow.
- `outputs/hazard_export.csv`, downloaded from the Google Earth Engine export, for location enrichment.

Hazard extraction requires Google Earth Engine access and an authenticated Earth Engine account. Set the project ID in a root-level `.env` file:

```dotenv
EE_PROJECT_ID=your-earth-engine-project-id
```

The optional chatbot also requires `GEMINI_API_KEY` in `.env`, plus the Google Gen AI Python package. Keep credentials and source datasets private; do not commit `.env` or local data.

## Core workflow

Run commands from the repository root. The complete data pipeline requires the source files and Earth Engine access described above. Claims are split at 2024-01-01: claims before that date can support historical features, while 2024 claims are reserved for holdout validation.

1. Split claims into historical and holdout datasets (if claims are available):

   ```powershell
   python scripts/split_claims_by_date.py
   ```

2. Run `scripts/pull_hazard_data.py` to sample hazard data. The script starts an asynchronous Google Drive export by default; monitor the Earth Engine task and download its CSV to `outputs/hazard_export.csv`. Its small test mode writes a local sample instead, which is not the production handoff file expected by the next step.

3. Enrich the hazard export with coordinates and location labels:

   ```powershell
   python scripts/merge_locations.py
   ```

4. Score the portfolio:

   ```powershell
   python scripts/risk_score.py
   ```

5. To add claims-derived evidence, run the historical claims validation/matching workflow described in `PROJECT_DOCUMENTATION.md`, then build features and score again:

   ```powershell
   python scripts/build_claims_features.py
   python scripts/risk_score.py
   ```

6. Evaluate against historical and 2024 holdout claims when those inputs have been prepared:

   ```powershell
   python scripts/validate_against_claims.py
   python scripts/validate_holdout_2024.py
   ```

The scripts write intermediate files and reports under `outputs/`; several stages depend on outputs from earlier steps. See the technical documentation for exact inputs, outputs, and ordering details.

## Dashboard

After creating `outputs/sites_scored.csv` and installing the dashboard dependencies, launch the interactive portfolio dashboard:

```powershell
streamlit run scripts/dashboard.py
```

## Optional chatbot

`chatbot.py` reads `outputs/sites_scored.csv`, optionally reads `outputs/rainfall_return_periods_chirps.csv`, and uses `methodology.md` for model explanations. It requires `GEMINI_API_KEY` in `.env` and the `google-genai` package. Run it with:

```powershell
python chatbot.py
```

## Notes

- `data/`, `outputs/`, `.env`, virtual environments, and local demo artifacts are intentionally excluded from version control; a fresh clone does not include the data needed to run the pipeline immediately.
- Earth Engine extraction, claims matching, coastal analysis, and rainfall return-period analysis have separate prerequisites and outputs. Not every utility script is part of the core scoring path.
- Review the methodology and known limitations before using site tiers in operational decisions.

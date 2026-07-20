## AIRIS Cardiff PoC — Setup and quick start

This repository contains a research proof‑of‑concept (PoC) for AIRIS (AI‑enabled Risk Intelligence Service) limited to Cardiff.

These are demonstrator materials. Station records in `data/stations.csv` are sample PoC data only.
Weather data is provided by Open-Meteo and map tiles are provided by OpenStreetMap contributors.

### Setup (Windows, Conda or venv)

1. Create and activate a Conda environment with Python 3.12:

```powershell
conda create -n airis-poc python=3.12 -y
conda activate airis-poc
```

2. Or create a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

### Run

```powershell
python -m streamlit run app.py
```

The central data-mode setting is `DATA_MODE` in `config.py`. It defaults to
the public-source verified Cardiff dataset. Demonstrative sample mode remains
available for a local run with:

```powershell
$env:AIRIS_DATA_MODE = "sample"
python -m streamlit run app.py
```

or:

```powershell
$env:AIRIS_DATA_MODE = "verified"
python -m streamlit run app.py
```

Verified mode reads `data/processed/cardiff_stations_verified.csv`. A missing,
empty, malformed, or duplicate-ID verified dataset produces an explicit error;
the application does not silently fall back to sample data.

## Test

```powershell
python -m pytest
```

## Deployment to Streamlit Community Cloud

1. Push this repository to GitHub and ensure the application root contains:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `data/stations.csv`
   - `.streamlit/config.toml`
   - `.streamlit/secrets.toml` should be excluded from Git and not committed
2. In Streamlit Community Cloud, create a new app from your GitHub repository.
3. Select the `main` branch for deployment.
4. Set the app entry point to `app.py`.
5. Use Python `3.12` for the app environment.
6. Confirm the app launches and displays the Cardiff map with the configured data mode and dashboard metrics.

## Deployment checklist

- [ ] Repository pushed to GitHub
- [ ] `main` branch selected in Streamlit Cloud
- [ ] App entry point set to `app.py`
- [ ] Python version set to `3.12`
- [ ] `requirements.txt` present and compatible
- [ ] `data/stations.csv` present
- [ ] `.streamlit/config.toml` present
- [ ] No secrets or credentials in source code
- [ ] No local absolute paths in code
- [ ] Tests pass locally
- [ ] App starts successfully

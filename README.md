# AIRIS Cardiff PoC

A research proof-of-concept for AIRIS (AI-enabled Risk Intelligence Service) focused on Cardiff. The app uses sample site data in `data/stations.csv`, Open-Meteo weather, and OpenStreetMap tiles.

## Setup

1. Create and activate a Python 3.12 environment.

Windows (Conda):

```powershell
conda create -n airis-poc python=3.12 -y
conda activate airis-poc
```

Windows (venv):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python -m streamlit run app.py
```

## Test

```powershell
python -m pytest
```

## Deployment

Deploy this app to Streamlit Community Cloud from GitHub.

- GitHub repo: `FideleA/AIRIS-PoC-V1`
- Branch: `main`
- App entry point: `app.py`
- Python version: `3.12`

Required repository files:

- `app.py`
- `requirements.txt`
- `README.md`
- `data/stations.csv`
- `.streamlit/config.toml`

Important:

- Do not commit `.streamlit/secrets.toml`
- Ensure no local absolute paths remain in code
- Verify the Cardiff map and dashboard metrics load successfully

## Notes

- `data/stations.csv` contains sample PoC site data only.
- Weather is fetched from Open-Meteo.
- Map tiles are provided by OpenStreetMap contributors.

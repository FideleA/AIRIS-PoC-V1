# AIRIS Cardiff PoC — Project Instructions

## Project purpose

Build a simple research proof of concept called AIRIS:
AI-enabled Risk Intelligence Service.

AIRIS assesses public and proposed EV charging sites in Cardiff and
presents explainable current and forecast site-risk scores.

This is a research demonstrator for insurance-facing risk intelligence.
It is not a production insurance system.

## User context

The project owner is a telecom and cybersecurity engineer, not a
professional software developer.

Therefore:

- keep the architecture simple;
- favour readable Python over advanced abstractions;
- explain major implementation decisions;
- include comments where they genuinely improve understanding;
- avoid unnecessary frameworks and infrastructure;
- provide exact commands for running and testing the application;
- do not introduce complex software patterns unless required.

## Approved technology stack

Use only:

- Python 3.12;
- Streamlit;
- pandas;
- numpy;
- requests;
- Folium;
- streamlit-folium;
- pytest for tests;
- CSV files for initial data storage;
- DuckDB only if explicitly requested later.

Do not introduce:

- React;
- Angular;
- Node.js;
- Docker;
- Kubernetes;
- microservices;
- PostgreSQL;
- cloud databases;
- authentication;
- paid APIs;
- machine-learning model training;
- insurer-system integration.

## Geographic scope

The PoC is limited to Cardiff, Wales.

The map must centre on Cardiff.

The initial station records may be demonstrative, but they must be
clearly labelled as sample data.

## Risk model

The PoC uses three factors:

1. Flood exposure
2. Temperature
3. Income deprivation

Illustrative configurable weights:

- Flood: 50%
- Temperature: 30%
- Income deprivation: 20%

The weights must be stored in one configuration file and must total 1.0.

The weighted score is:

overall score =
flood score × flood weight
+ temperature score × temperature weight
+ deprivation score × deprivation weight

All factor scores and the overall score must range from 0 to 100.

The application must calculate:

- current overall score;
- current factor contributions;
- forecast overall score;
- direction of change;
- risk category;
- model version;
- calculation timestamp.

Flood and income deprivation remain static in the initial version.
Temperature is the only dynamic forecast factor.

## Weather data

Use the Open-Meteo forecast API.

No API key should be required.

Implement:

- reasonable timeout;
- response validation;
- error handling;
- caching to reduce repeated calls;
- visible attribution.

If weather retrieval fails for one site, the application should remain
usable and display an appropriate warning.

## Dashboard requirements

The Streamlit dashboard must include:

- title and clear research-demonstrator notice;
- four portfolio summary metrics;
- interactive Cardiff map;
- colour-coded station markers;
- selected-site assessment;
- current and forecast risk scores;
- factor contribution chart;
- proposed-site coordinate entry;
- proposed-site risk calculation;
- traceability information;
- data-source attribution;
- visible limitations.

The dashboard must state clearly:

- values are illustrative;
- AIRIS does not predict claims;
- AIRIS does not calculate premiums;
- AIRIS does not automate underwriting.

## Code quality

Requirements:

- small, clearly named modules;
- type hints where practical;
- docstrings for public functions;
- input validation;
- useful error messages;
- no secrets in source code;
- no hard-coded local absolute paths;
- no silent exception swallowing;
- no duplicated scoring logic;
- no unnecessary dependencies.

## Security requirements

- Do not process personal data.
- Do not store credentials.
- Do not log confidential information.
- Validate CSV columns and score ranges.
- Use request timeouts.
- Pin sensible dependency version ranges.
- Add a .gitignore file.
- Keep the repository safe for publication with sample data only.

## Required project structure

airis-poc/
├── app.py
├── config.py
├── data_loader.py
├── scoring.py
├── weather_service.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── stations.csv
├── tests/
│   ├── test_scoring.py
│   └── test_data_loader.py
└── .streamlit/
    └── config.toml

## Completion criteria

The task is complete only when:

1. all required files exist;
2. dependencies install successfully;
3. tests pass;
4. the Streamlit app starts without errors;
5. the Cardiff map displays sample sites;
6. current and forecast scores are calculated;
7. proposed-site assessment works;
8. limitations and attribution are visible;
9. README contains exact setup and run commands.

Before making major architectural changes, explain the reason and ask
for approval.
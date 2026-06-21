# Naturalis Biodiversity Portfolio Project

This is a portfolio project I did to demonstrate my data engineering and software devlopment skills. I used the [Netherlands Biodiversity API (NBA)](https://api.biodiversitydata.nl) to ingest, transform, and serve specimen data in an interactive UI.

![Architecture diagram](Mock-up%20%26%20ETL%20processchema.drawio.png)

## Architecture

- **Data Pipeline**: Apache Airflow 3 ETL pipeline that extracts 50k Plantae specimen records from the NBA API, normalises the nested JSON, and loads the result into MySQL.
- **Backend**: Express.js REST API that queries the MySQL database with a `POST /api/species/search` endpoint.
- **Frontend**: D3.js-based interactive 3D globe with search, map pins, and specimen detail panels, built with Vite.

## Repo Structure

```
naturalis-pipeline/    Airflow DAG, Docker Compose, config
naturalis-backend/     Express API server
naturalis-frontend/    Vite + D3.js web app
```

## Quick Start

1. Start Airflow via Docker: `cd naturalis-pipeline && docker compose up -d`
2. In the Airflow UI (`http://localhost:8080`), add a MySQL connection named `mysql_localhost` pointing to `host.docker.internal:3306` (user `root`, password and database from `naturalis-pipeline/.env`).
3. Start the backend: `cd naturalis-backend && npm install && npm start`
4. Start the frontend: `cd naturalis-frontend && npm install && npm run dev`

The frontend opens at `http://localhost:5173` and expects the backend at `http://localhost:3001`.

# Kellmarks

Kellmarks is a minimal, self hosted bookmark homepage designed for speed, clarity, and local ownership of data. It provides a dark themed single page interface with hierarchical tags, advanced search, and a small Flask backend that persists everything to a single JSON file.

The project is intentionally simple. There is no build step, no database server, and no external dependencies beyond Python and Flask.

## Features

- Dark themed, single page bookmark dashboard
- Card based layout with optional icons and descriptions
- Hierarchical tags using slash notation (example: cloud/aws/iam)
- Live tag tree with entry counts
- Advanced search with AND, OR, NOT, parentheses, and quoted phrases
- Local first data model stored in `assets/data.json`
- Import and export bookmarks as JSON
- Optional DuckDuckGo search proxy
- OpenAPI specification and API documentation included

## Tech Stack

Frontend
- Vanilla HTML, CSS, and JavaScript
- No frameworks and no build tooling

Backend
- Python with Flask
- File backed persistence with atomic writes
- JSON based API

## Repository Layout
.
├── index.html
├── API.md
├── openapi.yaml
├── server/
│ └── app.py
└── assets/
├── app.js
├── app.css
└── data.json

## Running Locally

### Option 1: Static Mode (Read Only)

You can open `index.html` directly in your browser.

Note: In this mode, adding or editing bookmarks is disabled because browsers cannot write to local files.

### Option 2: Flask Server (Full CRUD)

## Requirements
- Python 3.9 or newer
- Flask

## Install dependencies:
pip install flask

## Run the server:
python server/app.py

By default, the app runs on:
http://localhost:8787

The server:
- Serves the frontend
- Enables create, update, delete, search, import, and export
- Writes changes to `assets/data.json`

## API Overview

The backend exposes a simple JSON API, including:

- `/api/items` for CRUD operations
- `/api/search` for advanced boolean search
- `/api/tags` for hierarchical tag trees
- `/api/export` and `/api/import`
- `/api/duckduckgo` for proxied search results

See `API.md` and `openapi.yaml` for full details.

## Data Model

All bookmarks are stored in a single JSON file:


Each entry includes:
- id
- title
- url
- description
- tags
- optional icon URL

This design keeps the system portable and easy to back up or version control.

## Security Notes

This project assumes a trusted environment.

Out of the box:
- No authentication is enabled
- CORS is fully open
- The DuckDuckGo proxy is unrestricted

If exposing this publicly, consider:
- Adding authentication or reverse proxy protection
- Restricting CORS to a specific domain
- Adding rate limiting
- Running behind HTTPS

## Use Cases

- Personal start page
- Self hosted bookmark manager
- Knowledge link hub
- Lightweight alternative to browser sync services
- Offline friendly reference dashboard

## Philosophy

Kellmarks favors durability over complexity. All data is readable, editable, and portable without specialized tooling. The goal is long term usefulness rather than feature churn.

## License

Unilicense

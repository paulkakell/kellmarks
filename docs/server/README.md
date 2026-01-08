# Kellmarks server

Purpose
- Serves the UI and provides a JSON backed API that reads and writes assets/data.json.

Quickstart
1) cd server
2) python -m venv .venv
3) Windows: .venv\Scripts\activate
   Linux: source .venv/bin/activate
4) pip install -r requirements.txt
5) python app.py
6) Open http://127.0.0.1:8787

Notes
- Opening index.html via file path (file://) is read only because browsers cannot write to assets/data.json.
- The API enables remote calls for every CRUD function and search, plus a DuckDuckGo proxy.

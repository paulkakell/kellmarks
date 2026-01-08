# Kellmarks

What it is
- A dark themed, tag hierarchical bookmark homepage named Kellmarks.
- Data is stored in assets/data.json when you run the server.
- The browser UI calls API endpoints for add, edit, delete, export, import, search, tag tree, and DuckDuckGo proxy.

Important
- If you open index.html via file path (file://), browsers cannot write to assets/data.json.
  Use the included server for full functionality.

Run (local or VPS)
1) cd server
2) python -m venv .venv
3) pip install -r requirements.txt
4) python app.py
5) Open http://127.0.0.1:8787

Docs
- API.md
- openapi.yaml

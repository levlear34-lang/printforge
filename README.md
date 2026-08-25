# PrintForge

A public website that turns a plain-English request ("phone stand, 2 slots,
18 degrees" or "Batman themed phone holder") into a downloadable, validated,
print-ready STL file. Visitors bring their own free Kaggle API token, which
is used to run the actual generation work on Kaggle's free GPU tier.

This is a separate, public-facing project built on top of ideas and vendored
logic from a private CLI tool (AI_3D_FACTORY) but is its own independent
codebase, repo, and deployment.

## Status

Milestone 1 (project scaffolding) in progress. See [CLAUDE.md](CLAUDE.md)
for full architecture, milestone plan, and the progress log.

## Repo layout

- `backend/` -- FastAPI service. Handles requests, job tracking, and auth.
  Does not run Blender itself -- all generation work happens inside a Kaggle
  kernel, submitted with the visitor's own Kaggle token.
  - `backend/app/vendored/` -- request parsing/classification/design logic
    copied from AI_3D_FACTORY (see CLAUDE.md for the vendoring policy).
- `frontend/` -- the public site (landing, create form, job status, result,
  accounts, dashboard, FAQ, legal pages). Built out starting Milestone 3.
- `render.yaml` / `Procfile` -- deploy config for Render/Railway free tier.

## Local development (backend)

```bash
cd backend
python -m venv venv
./venv/Scripts/pip install -r requirements.txt  # Windows
source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
uvicorn app.main:app --reload
```

Then visit `http://127.0.0.1:8000/health`.

Run tests:

```bash
cd backend
./venv/Scripts/pytest  # Windows
pytest  # macOS/Linux
```

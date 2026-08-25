# PrintForge — Project Context

## Purpose
A public website: a visitor describes an object in plain English (parametric,
e.g. "phone stand, 2 slots, 18 degrees", or vague/creative, e.g. "Batman
themed phone holder"), pastes their own Kaggle API token, and gets back a
downloadable, validated, print-ready STL file. No OrcaSlicer integration —
the product ends at download.

This is a separate, independently-hosted project. It reuses ideas and some
vendored logic from a private CLI tool (AI_3D_FACTORY, at
`C:\Users\User\Downloads\AI_3D_FACTORY` on the developer's machine) but is
its own repo, its own git history, and its own deployment — AI_3D_FACTORY is
never modified as part of this project.

## Naming
Project name is "PrintForge" — used for the repo, page titles, and site
branding throughout.

## Architecture
- **Backend** (`backend/`, FastAPI): handles HTTP requests, job tracking,
  auth, rate limiting. Does **not** run Blender itself.
- **Generation**: all actual generation work — request parsing, design
  math, Blender geometry/creative generation, validation — runs inside a
  Kaggle kernel, submitted using the **visitor's own** Kaggle API token
  (never the developer's, and never persisted outside a single request
  unless the visitor is logged in and explicitly saved it, encrypted). This
  is a deliberate departure from AI_3D_FACTORY, where Blender ran locally on
  the developer's machine — a public site can't assume visitors have Blender
  installed, and the free web-hosting tier can't run it either. Kaggle
  kernels get the actual Blender work done via the `bpy` pip package
  (headless Blender-as-a-library), not a full Blender install.
- **Frontend** (`frontend/`): the public site — landing, create form, job
  status, result/download, accounts, dashboard, feedback, FAQ, legal pages.
- **Database**: Supabase or Neon Postgres (persistent free tier — not
  Render's built-in Postgres, which expires after 30 days). Not provisioned
  until Milestone 5.
- **Hosting**: Render or Railway free tier for the web service.

## Key files
- `backend/app/main.py` — FastAPI app entry point
- `backend/app/config.py` — env-var-only configuration (no hardcoded
  secrets; required values fail loudly once they're actually needed)
- `backend/app/vendored/` — logic copied from AI_3D_FACTORY's
  `app/modules/`: `request_parser.py`, `request_classifier.py`,
  `design_agent.py`. See "Vendored modules" below for the sync policy.
- `backend/tests/` — pytest suite
- `render.yaml`, `Procfile` — deploy config for Render/Railway
- `frontend/` — placeholder until Milestone 3

## Vendored modules
`backend/app/vendored/request_parser.py`, `request_classifier.py`, and
`design_agent.py` are **copies**, not imports, of the same-named files in
AI_3D_FACTORY's `app/modules/`. This repo's copies are the source of truth
for PrintForge going forward — they will diverge over time (e.g. the parser
may need to accept a wider vocabulary for public/anonymous users than the
personal CLI tool ever needed). If a bug is found and fixed in one project's
copy, it is **not** automatically fixed in the other; check both if a
parsing/classification/design bug turns up in either. `model_specification.py`
was deliberately **not** vendored as-is — its original form only writes JSON
to a local `data/` folder, which doesn't fit a multi-tenant web backend; its
logic will be reworked into the job/database models once Milestone 2 needs
it, not carried over verbatim.

Not yet vendored (deferred to when they're actually needed, not vendored
speculatively):
- `blender_runner.py` / `app/controllers/blender/generate_model.py` and
  friends — the Blender geometry/validation logic. This has to be adapted
  to run inside a Kaggle kernel via the `bpy` pip package instead of
  shelling out to a local Blender executable, so it's a port, not a copy.
  Happens in Milestone 2.
- `kaggle_generator.py` / `pending_jobs.py` / `async_generation.py` /
  `mesh_quality.py` — will be reworked (not copied verbatim) since this
  project's job model is multi-tenant (per-visitor tokens, DB-backed job
  history) rather than AI_3D_FACTORY's single local `pending_jobs.json`.

## Status
Milestone 1 (project scaffolding) in progress.

## Current milestone: 1 — Project scaffolding
Repo structure, chosen stack (FastAPI backend, Postgres via Supabase/Neon
later, Render/Railway hosting), vendored reusable modules, and a working
local "hello world" API (`/`, `/health`, `/api/classify`) as the first
deploy-pipeline check. See Progress Log for what's actually done.

## Milestone plan
1. Project scaffolding: repo structure, stack choice, vendor reused modules,
   hello-world deploy to free hosting, confirm the deploy pipeline works.
2. Core create flow (backend): request classification (reuse vendored
   logic), Kaggle job submission using a provided token, async job
   tracking, result retrieval — anonymous only, no auth yet.
3. Core create flow (frontend): landing, create form, job status,
   result/download pages, wired to milestone 2's backend.
4. Content filter on prompts, rate limiting, custom 404, robots.txt, basic
   SEO (titles/meta/alt text/social image).
5. Database setup (Supabase/Neon), account system (signup/login, encrypted
   token storage), dashboard with history.
6. Feedback system + admin view, FAQ, Terms of Use, Privacy Policy, Kaggle
   onboarding help content.
7. Google Analytics + cookie consent, sticky mobile CTA, final polish pass,
   full manual smoke test of the entire flow (anonymous + logged-in, fast +
   refined tiers).

## Working rules
- Small, independently tested milestones. Commit + push after each passing
  milestone. Never force-push.
- Site's own secrets (DB credentials, session secret, token-encryption key)
  come from environment variables / a gitignored local `.env` — never
  hardcoded or committed. Never ask the developer to paste secret values in
  chat — only file locations or confirmation that env vars are set, same
  rule as AI_3D_FACTORY's Kaggle-token handling.
- Visitor Kaggle tokens: never logged, never written to disk outside a
  single request's execution, unless the visitor is logged in and
  explicitly chose to save it (encrypted at rest).
- Stop and ask only for: genuine technical blockers after real debugging
  effort, decisions that would meaningfully change cost (e.g. needing to
  move off a free tier), or anything destructive/irreversible.

## Known blockers / external dependencies
As of Milestone 1, this environment has no `gh` CLI and no GitHub/Render/
Railway/Supabase/Neon credentials configured — none of those can be
provisioned autonomously (account creation and OAuth connections are
explicitly outside what this assistant does without the account owner
present). Practical effect:
- The repo exists locally with a clean git history but has **not** been
  pushed to GitHub yet — needs a GitHub repo created (by the developer, or
  by providing a token) and a `git remote add origin ... && git push`.
- `render.yaml` is prepared and tested to work against the current backend,
  but an actual Render deploy needs the developer to create a Render
  account and connect the GitHub repo through Render's own dashboard —
  that connection step is an account-level OAuth action only the account
  owner can do.
- Database (Milestone 5) has the same shape of blocker: needs a
  Supabase/Neon account created and a `DATABASE_URL` provided via env var
  once that milestone starts.

## Progress Log
(Append a dated entry after each milestone — what changed, what passed,
what's next.)

- 2026-08-25: Milestone 1 (project scaffolding) — in progress.
  Created a fresh, independent git repository at
  `C:\Users\User\Downloads\PrintForge` (sibling to AI_3D_FACTORY, not a
  subfolder or worktree of it, so git history is genuinely separate from
  day one — the AI_3D_FACTORY working-session worktree this task started
  in was never modified). Judgment call, made because the user's answer
  to a clarifying question about repo location/GitHub/hosting wasn't
  available: picked the "new sibling folder + build locally, push later +
  Render" defaults, all previously flagged to the user as the recommended
  options, per the project's own "make reasonable judgment calls on
  ambiguous decisions... keep going" working-style rule.
  Vendored `request_parser.py`, `request_classifier.py`, and
  `design_agent.py` from AI_3D_FACTORY's `app/modules/` into
  `backend/app/vendored/` (verbatim except `request_classifier.py`'s
  import line, adjusted from AI_3D_FACTORY's flat `modules` package to a
  relative import within this repo's package). Deliberately did NOT vendor
  `model_specification.py` as-is (it only writes local JSON files, doesn't
  fit a multi-tenant backend) or any Blender-running code yet (needs a real
  port to Kaggle's `bpy` pip package, not a copy — see "Vendored modules"
  above) — both deferred to Milestone 2, which actually needs them.
  Built a minimal FastAPI app (`backend/app/main.py`) with `/`, `/health`,
  and a `/api/classify` smoke-test endpoint that calls the vendored
  classifier — enough to prove the vendored code actually works inside
  this new project, without building the real create flow yet (that's
  Milestone 2's job).
  Real bug hit and fixed during setup, not assumed away: this machine only
  has Python 3.14 installed (very new), and the requirements.txt versions
  written from memory (fastapi 0.115.0/pydantic 2.9.2, matching what
  AI_3D_FACTORY's era would have used) failed to install — pydantic-core
  had no prebuilt wheel for 3.14 yet and pip fell back to a Rust source
  build, which failed for lack of MSVC build tools. Fixed by installing
  latest-compatible versions instead of guessing pins, confirming they
  actually installed cleanly, then pinning requirements.txt to the exact
  versions that were verified working (fastapi 0.141.1, pydantic 2.13.4,
  uvicorn 0.52.4) rather than to guessed numbers.
  Verified for real, not just "tests pass": ran the actual FastAPI app via
  uvicorn on localhost and hit `/health`, `/`, and `/api/classify` with
  real HTTP requests (curl) — got back the correct JSON for both a
  parametric-sounding and a creative-sounding prompt. 4/4 pytest tests
  also passing (root, health, classify-parametric, classify-creative).
  Wrote `render.yaml` (Python runtime, `pip install -r requirements.txt`,
  `uvicorn app.main:app` start command, free plan) and a `Procfile` as a
  Railway-compatible fallback — both are prepared and believed correct
  against the verified-working app, but the actual deploy-pipeline
  confirmation ("hello world deploy to the free hosting tier") is blocked
  on GitHub push + a Render/Railway account connection, both of which need
  the developer (see "Known blockers" above).
  Also in place: `.gitignore` (secrets, venv, node_modules, generated
  model output, OS/editor cruft), `backend/.env.example` (documents the
  env vars Milestone 5 will need, all empty/optional for now so the app
  boots with zero config today), root `README.md`.
  Next: once the developer confirms a GitHub repo (or provides a token)
  and a Render/Railway account connection, finish confirming the actual
  hosted deploy, then move to Milestone 2 (core create flow backend —
  Kaggle job submission with a visitor-provided token, async tracking,
  result retrieval, still anonymous-only).

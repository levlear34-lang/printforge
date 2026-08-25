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
  kernels get the actual Blender work done by downloading a real portable
  Blender Linux build and driving it headless via subprocess, **not** the
  `bpy` pip package — verified via a real Kaggle run that Kaggle's kernel
  image is Python 3.12, while every `bpy` PyPI wheel targets only 3.11 (up
  to Blender 5.0) or 3.13 (5.2.1+), so `pip install bpy` fails outright
  there. See Milestone 2's Progress Log entry for the full story. Backend
  computes the design spec (parsing/dimensions/fit rules) itself before
  pushing the kernel, using the same vendored pure-Python modules as
  everywhere else — the kernel receives a finished spec and only does the
  Blender-dependent half (geometry, validation, export).
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
- `backend/app/services/kaggle_client.py` — per-request Kaggle CLI wrapper;
  every call takes the visitor's token as an explicit argument and writes
  it to a fresh temp `KAGGLE_CONFIG_DIR`, deleted immediately after
- `backend/app/services/jobs.py` — in-memory async job store (anonymous,
  Milestone 2 scope; Milestone 5 adds DB-backed history for accounts)
- `backend/app/services/kernel_builder.py` — assembles a per-job copy of a
  `kaggle_kernel/` template, rewriting the kernel id to the visitor's own
  username + a job-scoped slug before push
- `backend/app/services/generation.py` — orchestrates submit/poll/retrieve
- `backend/app/routes/create.py` — `/api/create`, `/api/jobs/{id}`,
  `/api/jobs/{id}/download`
- `kaggle_kernel/printforge_parametric/` — the parametric-tier generation
  kernel (template; job-specific copies are built at request time, never
  committed)
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

Ported (not copied) in Milestone 2:
- `app/controllers/blender/generate_model.py`'s geometry/validate/
  render_preview functions were ported into
  `kaggle_kernel/printforge_parametric/run.py`'s `INNER_SCRIPT` — same
  math, adapted to run under a downloaded Blender binary instead of a
  local install, with two real fixes found only by actually running it on
  Kaggle (not assumed from the local-Blender version): `bpy.ops.wm.stl_export`
  instead of `export_mesh.stl` (removed in the Linux 5.2.1 build Kaggle
  downloads, even though it's still present in the local Windows 5.2.0 LTS
  install AI_3D_FACTORY uses), and `CYCLES`/CPU instead of `BLENDER_EEVEE`
  for the preview render (headless-safe, no GL context needed).

Not yet vendored/ported (deferred to when they're actually needed):
- `kaggle_generator.py` / `pending_jobs.py` / `async_generation.py` /
  `mesh_quality.py` — reworked, not copied verbatim, since this project's
  job model is multi-tenant (per-visitor tokens, in-memory then DB-backed
  job history) rather than AI_3D_FACTORY's single local `pending_jobs.json`.
  See `backend/app/services/` (kaggle_client.py, jobs.py, kernel_builder.py,
  generation.py) for what replaced them.
- The Shap-E / Stable Diffusion->TripoSR creative-tier kernels — Milestone 2
  only covers parametric requests; creative is explicitly out of scope
  until those kernels get the same portable-Blender print-readiness stage
  added. See Progress Log.

## Status
Milestone 2 (core create flow, parametric only) done and verified against
real Kaggle infrastructure. Milestone 1's hosting-deploy confirmation is
still pending (see "Known blockers" below, updated as it resolves).

## Current milestone: 3 — Core create flow (frontend)
Landing page, create form, job status (polling), and result/download pages,
wired to Milestone 2's backend. See Progress Log for what's actually done.

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
This environment has no `gh` CLI and no Render/Railway/Supabase/Neon
credentials configured — none of those can be provisioned autonomously
(account creation and OAuth connections are explicitly outside what this
assistant does without the account owner present).
- GitHub: resolved. Repo is pushed to
  https://github.com/levlear34-lang/printforge (developer created the empty
  repo, Claude added the remote and pushed).
- Render: developer is setting up the account/connection on their end
  (in progress as of Milestone 2) — `render.yaml` is prepared and tested
  against the current backend. Deploy confirmation still pending a live URL.
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

- 2026-08-25: Milestone 1 GitHub push — done. Developer created an empty
  repo at github.com/levlear34-lang/printforge; Claude added it as
  `origin`, renamed the local branch to `main`, and pushed the Milestone 1
  commit. Render account/connection is in progress on the developer's end
  (separately confirmed mid-Milestone-2 work); live-deploy verification is
  still pending a URL.

- 2026-08-25: Milestone 2 (core create flow, backend, parametric only) —
  done and verified against real Kaggle infrastructure, not just mocks.
  Scope note, decided partway through and worth stating plainly: the
  milestone plan didn't explicitly split parametric from creative, but
  creative-tier generation (Shap-E / SD->TripoSR) needs its own kernel
  print-readiness work on top of everything built here, so it's deferred
  as an explicit follow-on rather than rushed in alongside proving the
  core architecture. The parametric path exercises every shared piece
  (per-visitor token handling, async job tracking, kernel push/poll/
  retrieve, result download) end to end, so it's a real, complete vertical
  slice, not a partial one.

  Architecture finding that changed the plan, verified with a real Kaggle
  run before writing any real code around it (per this project's own
  working rules): pushed a minimal probe kernel that tried
  `pip install bpy` on Kaggle. It failed outright -- Kaggle's kernel image
  runs Python 3.12, and checked bpy's PyPI release history shows every
  wheel targets either 3.11 (through Blender 5.0) or 3.13 (5.2.1+); there
  has never been a 3.12 build. Rather than fight that, switched to
  downloading a real portable Blender Linux build
  (download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz,
  ~380MB) inside the kernel and driving it headless via subprocess --
  proven via a second probe kernel that this downloads, extracts, and runs
  in a Kaggle session. This sidesteps the Python-version mismatch entirely
  (Blender bundles its own Python -- confirmed 3.13 in the extracted
  build) and mirrors AI_3D_FACTORY's own local approach
  (`blender --background --python script.py`), just against a downloaded
  Linux build instead of a local Windows install.

  Also decided along the way: parsing and design-spec computation
  (`request_parser`/`design_agent`) run backend-side, not inside the
  kernel, even though the architecture doc says "parsing, design... runs
  inside a Kaggle kernel." That line's actual goal -- not requiring a
  *local Blender install* -- is still fully honored; the parsing/design
  math has no Blender or GPU dependency, so computing it backend-side
  (instant, free, easily testable) rather than duplicating it inside
  Blender's separate bundled Python interpreter is a simplification, not
  a shortcut around the goal. Documented in the "Architecture" section
  above.

  Built: `backend/app/services/kaggle_client.py` (per-request token --
  written to a fresh temp `KAGGLE_CONFIG_DIR`, deleted immediately after
  each subprocess call, never touching this machine's real `~/.kaggle` or
  getting logged), `jobs.py` (in-memory async job store; deliberately not
  a DB yet -- Milestone 5's job, documented as a known, accepted
  limitation), `kernel_builder.py` (copies a `kaggle_kernel/` template
  into a temp dir per job, rewrites the kernel id to
  `{visitor_username}/printforge-{job_id}`, injects the computed spec),
  `generation.py` (submit/poll/retrieve orchestration), and
  `routes/create.py` (`POST /api/create`, `GET /api/jobs/{id}`,
  `GET /api/jobs/{id}/download`). `kaggle_kernel/printforge_parametric/
  run.py` is the actual generation kernel -- a direct port of
  AI_3D_FACTORY's `generate_model.py` (create_organizer/holder/stand,
  mesh_bounds, validate, render_preview), wrapped in a download-Blender/
  run-Blender-as-subprocess orchestrator.

  Real bugs found only by actually running this on Kaggle, not assumed
  from local testing (both verified as fixed via a second real run, not
  just "should be fixed"):
  1. `bpy.ops.export_mesh.stl` -- the operator AI_3D_FACTORY's local
     Blender 5.2.0 LTS install still has, confirmed working there --
     raised `AttributeError: could not be found` on the Blender 5.2.1
     Linux build Kaggle downloads. Real version-specific removal, not a
     typo: confirmed locally that Blender 5.2.0 has *both*
     `export_mesh.stl` and the newer `bpy.ops.wm.stl_export`, so switching
     to the latter (with its differently-named `export_selected_objects`
     parameter, also confirmed via the operator's own RNA properties
     rather than guessed) works on both versions. This is exactly the
     kind of local-vs-Kaggle-Blender-version drift this project's
     dual-environment design makes possible, so it's called out explicitly
     in `run.py`'s comments, not left as a silent gotcha.
  2. First real end-to-end run's kernel succeeded (correct STL, correct
     validation) but retrieval timed out client-side after 120s -- because
     `run.py` never deleted the downloaded Blender tarball and its fully
     extracted ~380MB install from `/kaggle/working` before exiting,
     so *everything* in that directory became "kernel output," not just
     the 3 files actually wanted. Fixed on both sides: `run.py` now
     deletes the tarball/extracted dir/intermediate files before
     finishing (so Kaggle never stores gigabytes of Blender internals as
     this job's output in the first place), and `retrieve_output()` also
     takes an explicit `--file-pattern` as defense in depth. Same
     category of mistake AI_3D_FACTORY hit and documented with its own
     `--file-pattern` fix for Shap-E's multi-GB weight files -- worth
     remembering as a recurring Kaggle-kernel-output gotcha, not a one-off.

  15 new/updated pytest tests in `test_generation.py`, all mocking
  `kaggle_client` -- no real Kaggle calls in the automated suite, per this
  project's working rules. 19/19 tests passing project-wide (4 pre-existing
  + 15 new).

  Then proved the real requirement -- a visitor's own token producing a
  real downloadable STL with no manual Kaggle interaction -- with an
  actual unmocked run through the real backend code (not a standalone
  script bypassing it): submitted "phone stand, 2 slots, 18 degrees, 4mm
  walls, 3mm clearance, 70x12x150mm items" using the developer's own
  Kaggle token (standing in for "a visitor's token" for this test), polled
  it through `generation.check_job()` exactly as the eventual job-status
  page will, and got back a real 3KB STL + 301KB preview PNG + report.json
  with `passed: true`, `bounds_mm` exactly matching the requested envelope
  {159.2, 45.0, 128.0}, and 0 non-manifold edges. Opened the actual PNG
  (not just checked it existed) -- a correctly-shaped two-slot phone stand
  at a visible tilt, well-lit and legible. Total wall-clock for the
  successful run: kernel queued + downloaded Blender + generated +
  validated + rendered in well under a minute of actual execution time
  once it started running.

  Deliberately out of scope, called out rather than silently skipped:
  no auth, no rate limiting, no content filter, no DB persistence (all
  per the milestone plan -- those are Milestones 4/5), and creative-tier
  requests currently return a clear 501 "not wired up yet" instead of
  attempting anything (see scope note above).

  Next: Milestone 3, core create-flow frontend (landing, create form, job
  status polling, result/download pages) wired to this backend. Creative-
  tier kernel work (Shap-E/SD->TripoSR + portable-Blender print-readiness)
  is a real gap to come back to before the product is complete, not
  forgotten -- tracked in the "Not yet vendored/ported" list above.

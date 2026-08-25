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
  every call takes the visitor's token as an explicit argument and passes
  it via the `KAGGLE_API_TOKEN` env var for that one subprocess call only
  (never written to a file — see Milestone 3's Progress Log entry for why
  `KAGGLE_CONFIG_DIR`, the first approach, silently didn't work)
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
- `backend/app/db.py` + `backend/app/schema.sql` — Postgres access layer
  (plain psycopg SQL, no ORM) and the 2-table schema (`users`,
  `job_history`). Every function here is mocked in tests, never hit for
  real in the automated suite (no Postgres available in this dev
  environment) — see the module docstring.
- `backend/app/services/auth.py` — password hashing (bcrypt) + stateless
  signed-cookie sessions (itsdangerous, no server-side session table)
- `backend/app/services/token_crypto.py` — Fernet encrypt/decrypt for
  saved Kaggle tokens at rest (`TOKEN_ENCRYPTION_KEY` must be a real
  Fernet key, not just any random string)
- `backend/app/services/accounts.py` — composes db/auth/token_crypto/
  kaggle_client into the actual signup/login/save-token/dashboard-history
  operations; routes stay thin wrappers around this
- `backend/app/routes/auth.py` — `/api/signup`, `/api/login`,
  `/api/logout`, `/api/me`
- `backend/app/routes/dashboard.py` — `/api/dashboard/jobs` (+ per-job
  preview/download), `/api/account/token` (save/delete), `/api/account`
  (delete)
- `frontend/signup.html`, `login.html`, `dashboard.html` — account pages;
  `create.html` now checks `/api/me` and offers a saved-token toggle for
  signed-in visitors instead of always requiring a pasted token
- `backend/tests/` — pytest suite
- `render.yaml`, `Procfile` — deploy config for Render/Railway
- `frontend/` — landing (`index.html`), create form (`create.html`), job
  status polling (`job.html`), result/download (`result.html`), shared
  `assets/style.css` + `assets/app.js`. Served directly by the FastAPI app
  (`main.py` mounts `/assets` and returns each page for its clean route) —
  one process, one Render service, no separate frontend deploy pipeline.

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
Milestones 2, 3, and 4 (backend + frontend create flow, content filter,
rate limiting, SEO basics) done and verified against real Kaggle
infrastructure and real HTTP requests. Milestone 5 (database, accounts,
dashboard) is built and unit-tested (all DB calls mocked, no real Postgres
available in this dev environment); live verification against a real
Supabase instance is pending the developer finishing their connection
setup (see Progress Log and "Known blockers"). Milestone 1's hosting-deploy
confirmation is also still pending.

## Current milestone: 6 — Feedback, FAQ, Terms, Privacy
Feedback form + admin view, FAQ page, Terms of Use, Privacy Policy, Kaggle
onboarding help content. See Progress Log for what's actually done.

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
- Database: developer has a Supabase project set up (in progress as of
  Milestone 5) and is working through connecting it -- Supabase's UI
  showed an IPv6-only warning under one pooler option, which would have
  been a real deploy blocker against Render (IPv4-only egress); pointed
  the developer at the free, IPv4-compatible shared Supavisor pooler
  (`aws-0-<region>.pooler.supabase.com:6543`) instead of the paid
  IPv4-add-on path, verified via Supabase's own docs before answering
  rather than guessing. `DATABASE_URL` still needs to be set once that's
  sorted; the app boots and works without it (see Progress Log), only
  account/dashboard routes are blocked in the meantime.

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

- 2026-08-25: Milestone 3 (core create-flow frontend) — done, including a
  critical security bug found and fixed only because the flow was actually
  tested through a real browser rather than trusted from passing unit
  tests. Read this one in full if touching kaggle_client.py.

  Built: plain HTML/CSS/JS (no framework, no build step) -- `index.html`
  (landing, hero CTA above the fold, sticky mobile CTA, a real example
  using the actual phone-stand preview PNG generated in Milestone 2, not a
  mockup), `create.html` (prompt textarea that live-classifies via the
  existing `/api/classify` endpoint and reveals the fast/refined tier
  picker only for creative requests, Kaggle token field with a "don't
  have an account?" onboarding `<details>`), `job.html` (polls
  `GET /api/jobs/{id}` every 6s, redirects to the result page on
  completion, shows a clear retry path on error/quality-failure),
  `result.html` (preview image + Download STL button). `main.py` now
  mounts `/assets` as static files and serves each page at a clean route
  (`/`, `/create`, `/job`, `/result`) from the same FastAPI process --
  one Render service for both frontend and backend, no separate deploy
  pipeline to keep in sync, which is why this milestone needed no new
  hosting decisions.
  `routes/create.py`'s job-status endpoint was reworked to never expose
  this server's local filesystem paths to the client -- it now returns
  `preview_url`/`download_url` (relative API paths) instead of the raw
  `result` dict with absolute paths, and a new `GET /api/jobs/{id}/preview`
  endpoint serves the preview PNG the same way `/download` already served
  the STL. 6 new HTTP-level tests in `test_routes.py` (mocked Kaggle calls)
  confirm the response never leaks a local path. 23/23 tests passing.

  THE CRITICAL BUG: while manually testing the create form in a real
  browser (per this project's own "test UI changes in a browser" rule --
  the whole reason this was caught before it caused real harm), submitted
  a deliberately fake, garbage Kaggle token to verify the form's error
  handling. It did not error. The job was accepted and a real kernel got
  pushed -- using the developer's own real Kaggle account, not "rejected
  as invalid" like it should have been. This directly violates the
  project's core security requirement (visitor jobs must run under the
  VISITOR's account, never the developer's).
  Root cause, found by reading the installed `kaggle`/`kagglesdk` package
  source rather than guessing: this machine's kaggle CLI is version 2.2.4,
  which resolves access-token auth through its own hardcoded order --
  `KAGGLE_API_TOKEN` env var, then unconditionally
  `~/.kaggle/access_token` on the real filesystem -- and never once
  consults `KAGGLE_CONFIG_DIR` for that auth method (confirmed by reading
  `kagglesdk/kaggle_env.py`'s `get_access_token_from_env()` directly).
  `kaggle_client.py`'s original design (write the token to a temp dir, set
  `KAGGLE_CONFIG_DIR` to that dir) was built against the OLDER kaggle.json
  auth convention's documented behavior and silently did nothing on this
  version -- every call fell straight through to the developer's real
  `~/.kaggle/access_token`, regardless of what token was supplied.
  Verified the diagnosis with a deliberately adversarial test before
  trusting it: a `KAGGLE_CONFIG_DIR` pointed at a fresh directory
  containing 40 random base64 bytes as the "token" still resolved to the
  developer's real username and could list the developer's real kernels.
  Fix: `kaggle_client._run_with_token` now passes the token via the
  `KAGGLE_API_TOKEN` environment variable (the mechanism this CLI version
  actually reads) for that one subprocess call, never written to any file
  at all -- simpler than the original design, not just a patch over it.
  Re-verified the fix the same adversarial way: a garbage `KAGGLE_API_TOKEN`
  now correctly fails with "Authentication required," and the developer's
  real token still resolves correctly via the same code path. Then
  verified the fix through the actual running server (not just a script):
  POSTing a fake token to `/api/create` now returns 401 as it always
  should have; POSTing the real token still succeeds.
  Practical impact of the bug, for the record: it was only ever
  exercised against the developer's own account during local manual
  testing, before any real visitor could reach this code (Render deploy
  is still not live -- see "Known blockers"), so no other person's
  request ever ran under the wrong account. Caught before it mattered
  precisely because of the "verify in a real browser" habit, not because
  the automated test suite would have caught it -- the mocked tests
  couldn't have, since the bug was entirely in how a real `kaggle` CLI
  install resolves credentials, which mocking papers over by design. That
  gap has no full mitigation without shelling out to the real CLI in a
  test, which the project's own working rules deliberately avoid for
  quota-safety reasons on kernel-run calls -- the tradeoff is documented,
  not silently accepted, since the manual-real-browser-test step is what
  actually closed it.

  Then re-ran the entire flow through the real browser end to end, for
  real, after the fix: submitted "tool organizer, 3 slots, 5mm walls, 2mm
  clearance, 60x20x180mm items" via the actual create form using the
  developer's real token, watched the job page poll and auto-redirect to
  the result page on completion, and confirmed the preview image (a
  correctly-shaped 3-compartment organizer, genuinely rendered, not a
  placeholder) and the Download STL button both served real files
  (294KB PNG, 4.3KB STL) from the actual job.

  Next: Milestone 4 -- content filter on prompts, rate limiting, custom
  404, robots.txt, SEO basics (titles/meta/alt text already mostly in
  place from this milestone; social share image and robots.txt are the
  real gaps). The Render deploy confirmation from Milestone 1 is still
  open and independent of this work.

- 2026-08-25: Milestone 4 (content filter, rate limiting, SEO basics) —
  done and verified via real HTTP requests, not just unit tests.

  `backend/app/services/content_filter.py`: whole-word, case-insensitive
  keyword match across three categories the spec names (hate speech,
  sexual content, explicit violence). Deliberately "basic" per the spec's
  own wording -- a modest starter wordlist, not a trained classifier or an
  attempt at a canonical/exhaustive list; documented in the module
  docstring as a known limitation (won't catch leetspeak/evasion) rather
  than oversold. Rejects with a clear message (never silently drops), per
  the explicit spec requirement.

  `backend/app/services/rate_limit.py` + additions to `jobs.py`
  (`has_active_job`, `count_submissions_since`, a new `ip` field on job
  records): enforces 1 concurrent job and 5 submissions/day per IP --
  judgment call on the actual numbers, documented in the module docstring
  as generous enough for real experimentation, tight enough to stop a
  single visitor from flooding the job store. IP-based, not
  session/account-based, since there's still no auth (Milestone 5 can add
  an account-based layer on top later without removing this one).
  `routes/create.py` resolves the visitor's IP from `X-Forwarded-For`
  first (Render terminates TLS at a reverse proxy, so
  `request.client.host` would otherwise always be the proxy's internal
  address, not the real visitor) with a `request.client.host` fallback for
  local dev. Both are wired into `generation.submit_request` (422 for
  filtered content, 429 for rate limit), checked before any Kaggle API
  call so a blocked/limited request never wastes a real round trip.

  Custom 404: `frontend/404.html` (styled to match the site) served via a
  FastAPI 404 exception handler that checks the request path -- `/api/*`
  routes keep returning JSON (the frontend JS already handles a job/asset
  404 as a normal response), everything else gets the styled page.
  `frontend/robots.txt` (allow everything except `/api/`, `/job`,
  `/result` -- those are per-visitor session pages, not content worth
  indexing) served at `/robots.txt`.

  SEO: added Open Graph + Twitter Card meta tags to the landing page,
  reusing the real phone-stand preview image from Milestone 2 (not a
  placeholder) as the social share image. Noted directly in the HTML as a
  comment: the image URL is relative for now since the final Render
  domain isn't confirmed yet -- switch to an absolute URL once it is,
  since some platforms only resolve absolute image URLs for link
  previews. Audited all 5 pages (`index`, `create`, `job`, `result`,
  `404`) for unique titles/meta descriptions and confirmed both `<img>`
  tags have real (not filler) alt text -- all were already in decent
  shape from Milestone 3's build, so this was mostly verification, not
  new work.

  17 new tests (`test_content_filter.py`, `test_rate_limit.py`, plus
  submit_request-level wiring tests in `test_generation.py` and
  404/robots tests in `test_health.py`). 40/40 tests passing.

  Then verified for real against a live server, not just mocks: POSTed a
  filtered term to `/api/create` and got a real 422 with the expected
  message; submitted two real jobs back-to-back using the developer's
  real Kaggle token from the same client and confirmed the second was
  rejected with a real 429 ("You already have a job in progress");
  confirmed `/robots.txt`, an unknown page route (styled 404 HTML), and
  an unknown `/api/` route (JSON 404) all behave correctly; confirmed the
  new Open Graph/Twitter meta tags render in the actual served HTML.

  Next: Milestone 5 -- Supabase/Neon Postgres, account signup/login,
  encrypted saved-token storage, dashboard with job history. This is the
  first milestone that needs a real external account/credential the
  developer has to provision (a Supabase or Neon project + DATABASE_URL),
  same shape of blocker as Milestone 1's Render deploy -- will flag which
  of Supabase/Neon to ask for once the design work makes that concrete,
  rather than guessing which free-tier Postgres host to commit to.

- 2026-08-25: Milestone 5 (database, accounts, dashboard) — built and
  unit-tested; live verification against a real Postgres instance is
  pending the developer finishing their Supabase connection setup (see
  "Known blockers"). No Docker/local Postgres was available in this
  environment either, so this is the first milestone where "manually
  verified for real" means "against the developer's real Supabase
  instance once it's ready," not something achievable solo -- documented
  honestly rather than claimed as done.

  Provider judgment call: Supabase over Neon (the spec named both as
  options), since the developer didn't have a preference ready when
  asked. Reasoning: Supabase bundles a free Storage feature alongside
  Postgres, which is architecturally useful if generated STL/preview
  files ever need to survive a Render restart (they currently don't --
  still local disk, see below) without adding a third external account.
  The actual DB access layer (`db.py`) is plain psycopg against a generic
  `DATABASE_URL`, so it would work against Neon too with zero code changes
  if that ever needs to change.

  Schema (`schema.sql`, 2 tables): `users` (email, bcrypt password hash,
  an encrypted-Kaggle-token column + its plaintext username for display,
  nullable until a token is saved) and `job_history` (mirrors a subset of
  the in-memory job record for signed-in users only -- prompt,
  classification, status, file paths, a 7-day `expires_at`). Anonymous
  jobs are never written here, per the spec's "no history saved" for
  anonymous use -- `jobs.py`'s in-memory store remains the live/polling
  source of truth for every job regardless of who submitted it;
  `job_history` is purely the persistent mirror for dashboard display,
  updated at the same points `jobs.update_job` is (see
  `generation.py`'s new `accounts.record_job_start`/`record_job_update`
  calls, gated on `user_id is not None`).

  Auth: bcrypt password hashes, stateless signed cookie sessions
  (`itsdangerous`, no server-side session table -- a deliberate
  simplicity tradeoff, documented in `auth.py`: can't force-invalidate one
  session without rotating `SESSION_SECRET` for everyone, acceptable for
  a v1 with no incident-response tooling yet). Saved Kaggle tokens are
  encrypted at rest with Fernet (authenticated encryption, not just
  reversible obfuscation) -- `TOKEN_ENCRYPTION_KEY` must be an actual
  Fernet key, documented with the exact generation command in
  `.env.example` after almost repeating Milestone 1's mistake of writing
  a plausible-sounding but wrong generation command from memory; checked
  Fernet's actual key-format requirement first this time.

  `generation.submit_request` now accepts an optional `user_id`: if the
  visitor is signed in and didn't paste a fresh token, it decrypts and
  uses their saved one (`accounts.get_saved_token_plaintext`) --
  decrypted only in-memory for that one job submission, never returned
  from any API response. `routes/create.py`'s `CreateRequest.kaggle_token`
  is now optional for exactly this reason.

  A real bug caught before it shipped, not by luck: first version let a
  missing `DATABASE_URL` bubble up as a bare, unhandled `RuntimeError` ->
  a generic FastAPI 500 with no useful message. Tested this directly
  (booted the app locally without `DATABASE_URL` set, hit `/api/signup`
  for real) rather than assuming error handling worked, saw the raw 500,
  and fixed it: `db.get_connection()` now raises a dedicated
  `DatabaseNotConfiguredError`, caught by a specific FastAPI exception
  handler that returns a clean 503 with an honest message. Re-verified
  live after the fix -- both the API response and, separately, that the
  frontend's existing generic error-banner handling displays that exact
  message to the visitor with no extra frontend code needed.

  Frontend: `signup.html`, `login.html`, `dashboard.html` (job history
  with thumbnails/status/expiry, delete-per-job, saved-token
  save/view-masked/delete, delete-account with a confirm dialog).
  `create.html` now checks `/api/me` on load and, for a signed-in visitor
  with a saved token, hides the token field behind a "use a different
  token for this request" checkbox instead of always demanding a fresh
  paste. `index.html`/`create.html` navs now show "Log in" or "Dashboard"
  based on session state (`app.js`'s new `initAuthNav`).

  32 new tests across `test_auth_service.py`, `test_token_crypto.py`,
  `test_accounts.py`, `test_auth_routes.py`, `test_dashboard_routes.py` --
  all `db.*` and `kaggle_client.*` calls mocked, consistent with this
  project's no-real-external-calls-in-automated-tests rule. Added a
  `tests/conftest.py` to set throwaway `SESSION_SECRET`/
  `TOKEN_ENCRYPTION_KEY` values before any test module imports app code
  (both are module-level singletons in `config.py`, read once at import
  time). 83/83 tests passing project-wide.

  Also verified live, beyond the DB-missing-error case above: booted the
  app locally with generated (throwaway) `SESSION_SECRET`/
  `TOKEN_ENCRYPTION_KEY` but no `DATABASE_URL`, confirmed it still boots
  cleanly and the whole non-account create flow keeps working (graceful
  degradation, not an all-or-nothing dependency); clicked through
  signup.html in a real browser and confirmed the frontend correctly
  displays the server's real error message; confirmed the auth-aware nav
  correctly shows "Log in" for a logged-out visitor on both the landing
  and create pages.

  Also fixed in passing: while answering the developer's question about a
  Supabase dashboard warning ("Transaction pooler uses IPv6 by default"),
  confirmed via Supabase's own docs (not memory, which turned out to be
  stale/imprecise on this specific point) that the warning applies to a
  newer per-project "Dedicated Pooler" option, while the classic shared
  Supavisor pooler (`aws-0-<region>.pooler.supabase.com:6543`) remains
  free and IPv4-compatible -- the one to actually use for a Render
  deployment, avoiding an unnecessary $4/mo add-on.

  Known, accepted limitation carried forward: generated STL/preview files
  still live on local disk only (`GENERATED_ROOT`), not in any persistent/
  cloud storage -- a dashboard entry can show a job as "complete" with a
  now-missing file if the Render service restarts between generation and
  a later dashboard visit (the UI already handles a missing file
  gracefully -- `preview_url`/`download_url` come back `null` -- but the
  file itself is genuinely gone). Real cloud file storage (e.g. Supabase
  Storage, now that a Supabase project exists) is a reasonable follow-up
  but deliberately out of scope here to keep this milestone's diff
  focused; flagged rather than silently accepted as permanent.

  Next: Milestone 6 -- feedback form + admin view, FAQ, Terms of Use,
  Privacy Policy, Kaggle onboarding help content. Once `DATABASE_URL` is
  confirmed working, close the loop on Milestone 5 with a real signup ->
  save token -> submit a job -> see it on the dashboard walkthrough
  against the developer's actual Supabase instance.

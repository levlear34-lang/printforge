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
- `kaggle_kernel/printforge_creative_fast/` (Shap-E) and
  `printforge_creative_refined/` (Stable Diffusion -> TripoSR) — the two
  creative-tier kernels: ML generation, a raw-mesh sanity check, then the
  same downloaded-portable-Blender print-readiness stage the parametric
  kernel uses (auto-scale, repair via Voxel Remesh, base-add, export).
  Print-readiness code is intentionally duplicated between the two
  (verbatim identical) rather than shared -- Kaggle "script" kernels are
  single self-contained files, the same constraint the parametric kernel
  already has. Keep both in sync if that logic changes.
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
- `backend/app/routes/feedback.py` — `POST /api/feedback` (public) and
  `GET /api/admin/feedback` (gated by a shared `ADMIN_TOKEN` secret,
  compared with `secrets.compare_digest` -- no full admin-user system,
  per the spec's "don't over-build this" for v1)
- `frontend/feedback.html`, `thank-you.html`, `faq.html`, `terms.html`,
  `privacy.html`, `admin.html` — feedback flow, FAQ, legal pages, and the
  minimal token-gated admin view (`noindex`, not linked from any public nav)
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
All 7 milestones are done, including the originally-deferred creative
tier, and the full flow has been smoke-tested end-to-end against the real
live site (https://printforge-bbs1.onrender.com) -- not locally, not
mocked. Anonymous parametric generation, anonymous creative generation
(both tiers), signup/login, saving a Kaggle token, submitting a job that
uses the saved token instead of a pasted one, dashboard history, preview/
download (both the job-status and dashboard-specific routes), deleting a
job, deleting a saved token, and deleting an account -- every one of
these was exercised with real HTTP requests against the deployed service,
most using a real Kaggle token and a real generation run, not a
stand-in. The project is functionally complete per its own spec.

Getting the logged-in flow fully working surfaced two more real
production bugs beyond the ones already logged in Milestone 6/7 entries,
both found only by actually running the live flow (never showed up in
local dev or the mocked test suite, since both are specific to the
deployed environment's exact configuration):
1. `kaggle_client.py` hardcoded the literal command `"python"` for every
   Kaggle CLI subprocess call. Render's container only has `python3` on
   PATH, so this failed for *every* kaggle_client call, not just the one
   that happened to surface it first -- meaning the entire create flow
   was likely broken on the live site the whole time, not merely
   token-saving. Fixed with `sys.executable` (the exact interpreter
   already running the process), which is correct regardless of what a
   given deployment environment does or doesn't alias.
2. `TOKEN_ENCRYPTION_KEY` was initially set on Render in a format Fernet's
   own constructor rejects (not real `Fernet.generate_key()` output) --
   `token_crypto._fernet()` didn't catch that `ValueError`, and no route
   caught the resulting `EncryptionNotConfiguredError` either (unlike the
   equivalent `DatabaseNotConfiguredError`, which already had a global
   handler). Both gaps fixed; regenerated a correct key for the developer
   to paste in.

Both were diagnosed the right way, not guessed: since this assistant has
no direct access to Render's server logs, resolved each by reasoning from
what the code could and couldn't have raised, verifying candidate fixes
locally first, then confirming against the live deployment -- not by
trial-and-error redeploys.

## Milestone 7 — Analytics, cookie consent, final polish, creative tier
Done. Google Analytics + cookie consent, sticky mobile CTA (Milestone 3),
final polish pass, and creative-tier (fast/refined) generation (deferred
since Milestone 2, built and verified live this milestone). See Progress
Log for the full story on each.

## Current milestone: none — Milestone 8 + full visual redesign complete
Milestone 8 (AI-refined-prompt feature) is done -- see that section below.
On top of it, a full visual redesign replaced the original dark/orange
theme with a warm neutral palette (cream/beige base, terracotta primary
accent, sage secondary accent), a real type/spacing scale, skeleton
loaders, and accessibility fixes (keyboard-operable selection cards,
ARIA live regions, verified contrast ratios). See "Visual redesign" in
the Progress Log for the full story, including how real Playwright
screenshots were finally made to work in this environment. Nothing
further is planned without additional direction.

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

## Milestone 8 — AI-refined-prompt feature
### Goal
Vague creative prompts ("batman phone holder") sometimes produce
degenerate/low-quality meshes because the fast/refined 3D kernels get no
detail to work with. Add an opt-in pre-processing step: a small, separate
Kaggle kernel expands a vague idea into a detailed, generation-ready
prompt (shape/pose/style/proportions/print-quality details) before any
GPU-hour quota is spent on actual 3D generation.

### Design
- Second, opt-in path alongside the existing direct-to-generation flow on
  /create -- labeled "Quick" (current behavior, default) vs "Advanced:
  AI-refined prompt" (slower, uses a separate CPU-only Kaggle job per
  round before 3D generation even starts).
- New kernel (`kaggle_kernel/printforge_prompt_refiner/`): Qwen2.5-1.5B-
  Instruct, CPU-only (`enable_gpu: false`, matching the parametric
  tier's precedent) -- text expansion doesn't need a GPU, and running it
  without one means unlimited refinement rounds never touch the same
  weekly GPU-hour quota the fast/refined 3D tiers depend on. Confirmed
  with `kaggle quota` after two real test runs: 0.00h GPU consumed by
  either round.
- Iteration: visitor sees the refined prompt, can Approve (submits to the
  existing fast/refined 3D flow unchanged) or Request changes (free-text
  "make it more X", which becomes another refinement round -- the
  previous round's output becomes the new IDEA, the visitor's free text
  becomes FEEDBACK). No round cap. Each round is its own async Kaggle
  job through the same submit/poll/retrieve pattern as 3D generation.
  Refinement history is tracked client-side (an array of {input,
  feedback, output} per round) -- the backend has no need to persist
  cross-round state itself, since each round is an independent job.
- Uses the visitor's own Kaggle token, same as every other job in this
  project -- never a shared/developer credential.

### Milestones
1. ~~Kaggle kernel: build + manually verify with real Kaggle runs
   (including the "batman phone holder" example), in isolation before
   touching the pipeline.~~ done
2. Pipeline integration: submit/poll/retrieve reusing the existing async
   job pattern (jobs.py/kernel_builder.py/kaggle_client.py), proven
   end-to-end with a real Kaggle call, no manual steps.
3. Iteration UI on /create: Quick vs Advanced choice, approve/request-
   changes flow, visible refinement history, "this takes real time"
   messaging -- verified visually.
4. Wire the approved refined prompt into the existing fast/refined 3D
   flow unchanged; confirm no regression to the Quick path.
5. FAQ update (GPU-hour impact of the Advanced path) + a full manual
   smoke test covering both Quick and Advanced end to end.

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
- Render: resolved. Live at https://printforge-bbs1.onrender.com, confirmed
  with real requests (not just "the build succeeded").
- Database: resolved, fully. `DATABASE_URL`, `SESSION_SECRET`, and
  `TOKEN_ENCRYPTION_KEY` are all set correctly on Render (the first
  attempt at the latter two was mistakenly added as Render "Secret Files"
  rather than Environment Variables, which don't populate `os.environ`
  the same way -- resolved once corrected) and confirmed working with a
  full real account-flow smoke test (see Progress Log).
- Admin view: `ADMIN_TOKEN` (Milestone 6) is still not set on Render --
  same pattern, same fix (developer generates and sets it, nothing for
  Claude to provision). Only the admin feedback-reading view is affected;
  nothing visitor-facing depends on it.

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

- 2026-08-26: Live-deploy verification (closing out Milestone 1's long-open
  item, and the first real check of Milestone 5's Supabase connection) --
  done, with two real production bugs found and fixed along the way. The
  developer confirmed `DATABASE_URL` was set on Render and shared the live
  URL (https://printforge-bbs1.onrender.com); rather than trust that and
  move on, actually exercised it.

  Bug 1: `curl`-ing `/api/signup` on the live site returned a bare 500.
  Root cause, found by reading `backend/requirements.txt`: the `kaggle`
  package was never actually declared as a dependency -- it only ever
  worked in every prior milestone's testing because it happened to be
  installed system-wide on this dev machine by hand back in an early
  session, completely outside the project's own dependency management.
  Render's fresh build would never have had it, meaning the entire create
  flow (which shells out to `python -m kaggle`) would have been broken on
  the live site regardless of anything else -- caught before a real
  visitor could hit it, not after. Fixed by adding `kaggle==2.2.4`
  (matching the version verified throughout this project) to
  requirements.txt.

  Bug 2, found on the very next live attempt after fixing bug 1: signup
  still 500'd, but retrying with the same email returned a proper 409
  "already exists" -- proof the database write itself had actually
  succeeded on the first attempt (so `DATABASE_URL`/Supabase connectivity
  was confirmed genuinely working), and the crash was happening
  afterward. Root cause: `routes/auth.py`'s `signup`/`login` handlers only
  wrapped the `accounts.signup()`/`accounts.login()` call in a
  try/except -- the following `_set_session_cookie()` call (which raises
  `auth.AuthError` if `SESSION_SECRET` isn't configured) was outside that
  block, so that specific failure was never caught and surfaced as a raw,
  unhandled 500 instead of the clean JSON error the code was clearly
  supposed to produce. Fixed by moving the session-cookie call inside the
  same try/except. Re-verified live after the fix: the same request now
  returns a clean `{"detail":"SESSION_SECRET is not configured on the
  server."}` instead of a crash -- which also serves as definitive proof
  of the diagnosis, not just a guess that happened to compile.

  Side effect worth recording plainly: this diagnosis process created one
  real row in the developer's production `users` table
  (`claude-verify-test@example.com`, plus a couple of throwaway polling
  attempts like `claude-verify-poll-5@example.com`) -- just an email and a
  bcrypt hash, nothing sensitive, but flagged to the developer rather than
  left silently in their database. Offered to clean it up once
  login works.

  Net result: Milestone 1's deploy confirmation is genuinely done (the
  site is live and responding to real requests), and Milestone 5's
  database connectivity is genuinely confirmed (not just "should work").
  Still open: `SESSION_SECRET` and `TOKEN_ENCRYPTION_KEY` need to be set
  on Render before accounts fully work end-to-end -- everything else on
  the live site is unaffected and working.

- 2026-08-26: Milestone 6 (feedback, FAQ, Terms of Use, Privacy Policy) --
  done. Built while the developer works on setting the remaining Render
  env vars, so no live account-flow verification yet (same graceful-
  degradation pattern already established: tested locally without
  `DATABASE_URL`/`SESSION_SECRET` and confirmed the feedback form
  correctly surfaces the same clean "database isn't configured" error
  through the actual UI, not a crash).

  `schema.sql` gained a third table, `feedback` (rating + free-text
  message, no `user_id` -- the feedback page doesn't require login, by
  design). `routes/feedback.py`: `POST /api/feedback` (public, rejects
  a rating outside 1-5 or a completely empty submission) and
  `GET /api/admin/feedback` (gated by a shared `ADMIN_TOKEN` secret
  compared with `secrets.compare_digest` to avoid a timing side channel --
  matching the discipline already used for password/session comparisons
  elsewhere in this project). Deliberately not a full admin-user/role
  system, per the spec's explicit "don't over-build this" for v1.

  Frontend: `feedback.html` (star rating + comment, redirects to
  `thank-you.html` on success), `faq.html` (the 5 required questions --
  what's a Kaggle token, why refined takes longer, is my token stored,
  what can I print this on, is this free -- plus 2 more that came up
  naturally: file retention, and an honest note that creative/themed
  generation isn't live yet even though the tier picker already exists in
  the UI), `terms.html` and `privacy.html` (plain-language, covering the
  specific points the spec called for: user responsibility for
  printed/generated content, no quality guarantee, token-storage policy,
  and -- in the privacy policy -- a forward-looking disclosure of Google
  Analytics use, since Milestone 7 (next) adds it alongside the required
  cookie-consent notice; flagging this explicitly rather than letting it
  read as already-true when it technically ships next milestone).
  `admin.html`: token-gated, `noindex`, not linked from any public nav --
  paste the admin token, load feedback, no persistent admin session.
  Added a shared footer (FAQ/Feedback/Terms/Privacy links) to every public
  page via a small script, and extended `robots.txt` to disallow
  `/dashboard`, `/admin`, `/thank-you` alongside the existing
  `/job`/`/result` exclusions.

  8 new tests in `test_feedback_routes.py` (rating validation, empty-
  submission rejection, admin-token auth including the
  not-configured-yet case) -- 91/91 tests passing project-wide.

  Next: Milestone 7 -- Google Analytics + cookie consent (making the
  privacy policy's analytics disclosure actually true), final polish
  pass, and a full manual smoke test of the entire flow end to end
  (anonymous + logged-in, fast + refined tiers) once creative-tier
  generation and the remaining Render env vars are both in place. Sticky
  mobile CTA was already done back in Milestone 3.

- 2026-08-26: Milestone 7 (Analytics, cookie consent, final polish) --
  Google Analytics + cookie consent and the polish pass are done; the
  "full smoke test... fast + refined tiers" item is not, for a real
  reason explained at the end of this entry, not an oversight.

  `app.js` gained `initCookieConsent()` (runs automatically on every page
  that loads app.js -- no per-page script changes needed) and
  `loadGoogleAnalytics()`. GA is never loaded until the visitor explicitly
  clicks Accept; Decline persists just as durably. `GA_MEASUREMENT_ID` is
  a placeholder (`"G-XXXXXXXXXX"`) with an explicit guard that skips
  loading the gtag script entirely while it's still a placeholder, so
  nothing broken ships before a real GA4 property exists -- per the
  developer's choice not to set one up yet, this is intentionally
  deferred, documented as a single constant to swap later (not a secret,
  safe to just paste in when ready).

  Real bug found while verifying this the hard way (see below for how
  hard): the cookie banner (`position: fixed`, higher z-index) visually
  covered the landing page's sticky mobile CTA -- the site's main
  conversion button -- for as long as the banner was showing. Fixed by
  hiding the sticky CTA while the banner is up and restoring it
  (via clearing the inline override, not hardcoding it back to `block`,
  so desktop widths aren't affected) once the visitor decides either way.

  Also fixed, unrelated to cookie consent but found in the same pass:
  `/assets/*` (JS/CSS) had no `Cache-Control` header at all, which lets
  browsers cache them indefinitely on their own heuristics with zero
  revalidation. This project has no build-hash/versioning pipeline for
  static assets, so a deploy that changes app.js/style.css could leave
  returning visitors silently running old client code indefinitely.
  Added a small middleware setting `Cache-Control: no-cache` on
  `/assets/` responses -- forces revalidation (a cheap 304 when
  unchanged) on every load instead of trusting a possibly-stale copy.

  How the sticky-CTA bug was actually found and verified is worth
  recording: this session's browser tool had accumulated a very
  long-lived, aggressively cached copy of `/assets/app.js` and
  `style.css` from hours of earlier testing in this same conversation,
  and neither a normal reload, a hard-refresh keystroke, nor opening
  brand-new tabs would make it re-fetch either file (a real illustration
  of exactly the caching gap the Cache-Control fix above addresses).
  Repeated script-tag re-injection attempts to force a fresh copy hit a
  second, different dead end: a page can only declare a top-level `const`
  once, so every re-injection after the first threw a silent
  `SyntaxError: Identifier 'GA_MEASUREMENT_ID' has already been
  declared`, leaving the OLD function definition bound and making it look
  like the fix wasn't taking effect at all, when actually the new script
  simply never ran. Correctly diagnosed by reading the browser's own
  console error output rather than continuing to guess, then verified
  cleanly and unambiguously in a single-execution, cache-free context
  (constructed an isolated `<iframe>`, fetched the live HTML/CSS/JS with
  `cache: 'no-store'`, and wrote them into the iframe directly) --
  confirmed the sticky CTA correctly hides while the banner shows and
  restores correctly after Accept/Decline, and separately confirmed via
  the raw HTTP response body (not a DOM read that could itself be stale)
  that the server was serving the fixed code all along. Also found and
  cleaned up multiple duplicate local dev-server processes left over from
  earlier milestones' testing, all bound to the same port -- unrelated to
  the real bug but worth doing since it was actively confusing the
  diagnosis.

  91/91 tests still passing (no backend logic changed this milestone,
  frontend-only).

  Live progress on the two open Render items from Milestone 6: the
  developer confirmed setting `SESSION_SECRET`/`TOKEN_ENCRYPTION_KEY`, but
  a live retest still returns the same "SESSION_SECRET is not configured"
  error -- Render doesn't always auto-redeploy on an env var change (or
  hasn't yet); flagged to the developer that a manual "Deploy latest
  commit" may be needed, will retest once that happens rather than
  assuming the env vars are the problem.

  The genuine scope gap, stated plainly rather than glossed over: this
  milestone's plan assumed creative-tier (fast/refined) generation would
  already exist by now, since the original 7-milestone plan didn't
  anticipate deferring it. It was deferred in Milestone 2 as real,
  tracked follow-up work (porting AI_3D_FACTORY's Shap-E/SD->TripoSR
  Kaggle kernels plus the portable-Blender print-readiness stage that was
  never built for the Kaggle-hosted-Blender architecture this project
  uses) -- and it still hasn't been picked back up. That makes
  "full manual smoke test... both fast and refined tiers" impossible to
  actually do right now, not merely undone. Raised to the developer as a
  real decision point: build creative-tier generation now (a body of work
  comparable in size to Milestone 2) before considering v1 complete, or
  explicitly accept parametric-only as the v1 scope and revisit creative
  generation later.

  Next: pending the developer's answer on creative-tier scope, plus
  confirming the Render env vars actually took effect (delete the
  developer's requested test-account cleanup once login works).

- 2026-08-26: Creative-tier (fast/refined) generation -- built, and
  verified for real against live Kaggle infrastructure, both tiers,
  including two real bugs found only by actually running it (not
  something mocked tests could have caught). Developer's explicit call:
  build this now rather than ship parametric-only, given it was the one
  thing blocking a genuine end-to-end smoke test.

  Ported (not copied) from AI_3D_FACTORY: the Shap-E generation script
  (`kaggle_kernel/shape_generator/generate_mesh.py`, verbatim -- same
  --no-deps install workaround), the SD->TripoSR generation script
  (`kaggle_kernel/sd_triposr_generator/generate_mesh_refined.py`,
  verbatim -- same transformers-pin workaround, same model choices), the
  raw-mesh sanity check (`app/modules/mesh_quality.py`, verbatim, inlined
  into each kernel since it's pure Python with no dependencies), and the
  print-readiness stage (`app/controllers/blender/process_creative_mesh.py`)
  -- this last one needed real rework, not just a port, described below.
  `kernel_builder.TIERS` gained `fast`/`refined` entries (both requesting
  `--accelerator NvidiaTeslaT4`, the same real fix AI_3D_FACTORY's own
  kernels needed for the same P100-incompatibility reason), and
  `build_kernel()` now injects a raw prompt (not a computed spec) for
  these two tiers, using a regex + replacement *function* for the
  substitution -- deliberately avoiding re.sub's string-replacement form,
  which has a documented history of mangling backslashes in this exact
  codebase (AI_3D_FACTORY's `kaggle_generator.write_prompt` bug); a
  regression test locks this in
  (`test_kernel_builder.py::test_build_kernel_prompt_injection_handles_quotes_and_backslashes`).
  `generation.submit_request`'s 501 "not wired up yet" block is gone;
  creative jobs now push the right tier's kernel with no design spec.
  `_retrieve_and_finalize` gained a real new case: creative-tier kernels
  write *only* `report.json` (no `model.stl`) when the raw mesh fails its
  sanity check -- a normal, expected outcome for some prompts, now
  surfaced as `quality_failed` with the actual reasons, not a generic
  "no model.stl produced" error.

  THE REAL PRINT-READINESS REWORK. AI_3D_FACTORY's `process_creative_mesh.py`
  repairs non-manifold geometry via the bundled `object_print3d_utils`
  Blender addon, enabled with `addon_utils.enable(...)`. A real refined-
  tier Kaggle run (SD->TripoSR generation itself worked correctly --
  75k vertices, passed the raw-mesh quality check) failed at the print-
  readiness stage with `Add-on not loaded: "object_print3d_utils",
  cause: No module named 'object_print3d_utils'`. Researched rather than
  guessed at a workaround: that addon has been migrated to Blender's
  newer opt-in Extensions system and simply isn't bundled in the portable
  Linux 5.2.1 build Kaggle downloads, even though it's still present in
  the local Windows 5.2.0 LTS install AI_3D_FACTORY's original code was
  written against -- the third distinct case in this project of the two
  Blender builds silently diverging (after the STL-export-operator and
  EEVEE-vs-CYCLES issues in earlier milestones).
  Replaced the addon-based repair with Blender's built-in Voxel Remesh
  modifier (no addon needed, reliably produces closed/solid geometry
  regardless of input mess) -- and set its voxel_size to the same
  min-wall-thickness value the old Solidify-modifier step used, which
  turns out to also enforce a comparable minimum feature size as a side
  effect, making the separate Solidify step redundant. Both removed;
  Voxel Remesh alone now does repair AND minimum-feature-size enforcement.
  Verified this whole redesign *locally* before spending any more real
  Kaggle GPU time on it: built a deliberately messy synthetic test mesh
  (a UV sphere with ~5% of faces deleted, via a real Blender script, not
  hand-authored) and ran the exact print-readiness functions against it.
  Hit a second real, non-obvious Blender bug in that local testing:
  calling `bpy.ops.object.transform_apply(location=True, ...)` on a
  non-manifold mesh, immediately before adding+applying a brand-new
  modifier, makes that modifier_apply call silently no-op -- returns
  `{'FINISHED'}`, raises nothing, but the mesh is byte-for-byte unchanged.
  Reproduced it deliberately (clean mesh through the same pipeline: works
  fine; messy mesh: no-ops every time) before trusting the diagnosis, then
  fixed it by reordering -- Voxel Remesh now runs immediately after
  `auto_scale` (which only bakes *scale*, unaffected), and `sit_on_bed`
  (which bakes *location*) now runs after remeshing instead of before.
  Verified the reordered pipeline handles the boolean-union base-add step
  correctly too (still 0 non-manifold edges) before trusting it enough to
  spend real Kaggle quota confirming it.

  A THIRD real bug, found only once real Kaggle runs actually succeeded
  end-to-end: both tiers produced correct, valid, watertight geometry but
  a nearly-unreadable near-black preview render. Root cause: the original
  `apply_vertex_color_material` reads the mesh's imported per-vertex color
  attribute into a shader's Base Color via an Attribute node -- but Voxel
  Remesh replaces the mesh topology entirely and does not transfer that
  attribute, while the *material slot* (attached to the object, not the
  mesh data) survives remeshing untouched. The shader kept trying to read
  a now-nonexistent attribute, which evaluates to black. Fixed by
  dropping the vertex-color approach entirely (it can't survive
  remeshing regardless of when it's applied) in favor of a plain, fixed
  neutral-gray material (`apply_flat_material`) applied *after*
  remeshing. Verified in complete isolation first (a Suzanne monkey mesh
  through just the extracted material+render functions, confirmed
  clearly visible and correctly lit) before spending a third real Kaggle
  run confirming it end-to-end.

  Real, unmocked Kaggle verification (4 successful full round-trips plus
  2 informative real failures that directly drove the fixes above, ~0.45
  GPU-hours total for this whole creative-tier effort, 28.18h/30h still
  remaining for the week): fast tier ("a small dragon figurine") and
  refined tier ("a ceramic coffee mug") both completed with
  `non_manifold_edges: 0`, `passed: true`, and a genuinely legible,
  correctly-lit, correctly-based preview image showing recognizable
  geometry matching the prompt. Confirmed via the actual
  `generation.submit_request`/`check_job` service functions the real API
  layer calls, not a bypass script.

  `faq.html` updated: removed the now-obsolete "creative requests aren't
  live yet" caveat, replaced with a real question about what the
  automatic quality checks catch.

  91/97 -> 97/97 tests still passing throughout (existing tests updated
  where they asserted the old 501-not-supported behavior; new coverage
  added for tier-based kernel selection, accelerator selection, and the
  no-STL/quality_failed retrieval path).

  Next: Milestone 7's Google Analytics/cookie-consent work (already done,
  see the entry above) plus this creative-tier work together close out
  everything in the original 7-milestone plan except the still-pending
  Render `SESSION_SECRET`/`TOKEN_ENCRYPTION_KEY` confirmation and the
  associated logged-in-tier smoke test.

- 2026-08-27: Logged-in account flow -- fully smoke-tested against the
  real live site, two more real production bugs found and fixed along
  the way. This closes out the last open item from the original plan.

  Developer set `SESSION_SECRET`/`TOKEN_ENCRYPTION_KEY` on Render, but
  the live site kept returning the same "SESSION_SECRET is not
  configured" error even after a confirmed redeploy. Root cause, found by
  the developer checking Render's own dashboard: they'd been added as
  Render "Secret Files" (which mount a file at a path) rather than
  Environment Variables (which populate `os.environ`) -- this app reads
  `os.environ.get("SESSION_SECRET")`, so a secret file never reached it
  regardless of content. Resolved once corrected.

  With that fixed, signup/login started working live -- but saving a
  Kaggle token to the account still 500'd. Diagnosed without access to
  Render's server logs (not available to this assistant), by reasoning
  through what the code could raise and verifying candidates before
  trusting them:
  1. `kaggle_client._run_with_token` hardcoded the literal command
     `"python"` for every subprocess call to the kaggle CLI. Render's
     container only has `python3` on PATH -- `subprocess.run(["python",
     ...])` would raise a bare `FileNotFoundError`, not one of this
     module's own exception types, so it was never caught anywhere and
     surfaced as a raw 500. This affects *every* kaggle_client call
     (resolve_username, push_kernel, get_status, retrieve_output), so the
     entire create flow was likely broken on the live site the whole
     time -- token-saving just happened to be the first thing that
     exercised it after the SESSION_SECRET fix unblocked testing that far.
     Fixed with `sys.executable` (the exact interpreter already running
     this process, correct regardless of what a given environment does or
     doesn't alias) and wrapped the subprocess.run call itself so any
     future launch failure surfaces as a clean `KaggleCliError` instead
     of an unhandled exception -- then updated both call sites
     (`accounts.save_kaggle_token`, `generation.submit_request`) to
     handle that error type with a proper 502. Verified locally against
     real Kaggle after the fix, then pushed.
  2. Retesting after that fix *still* 500'd on token-save. The developer
     couldn't run the Fernet-key-generation command locally (no
     `cryptography` package installed on their machine), so this
     assistant ran it and provided the output directly -- a judgment call
     under the project's credential-handling philosophy: this is a
     self-generated *application* secret with no prior data depending on
     it, not a third-party account credential, and the developer
     explicitly asked for it since they had no other way to produce it.
     Root cause confirmed once a definitely-valid key was in hand: the
     original `TOKEN_ENCRYPTION_KEY` value hadn't been in real Fernet key
     format, and `token_crypto._fernet()` didn't catch the `ValueError`
     Fernet's constructor raises for that -- nor did any route catch the
     resulting `EncryptionNotConfiguredError`, unlike the equivalent
     `DatabaseNotConfiguredError`, which already had a global FastAPI
     exception handler from Milestone 5. Fixed both gaps (catch +
     reraise as the existing error type; registered the missing global
     handler, same pattern as the database one) and had the developer
     paste in the freshly-generated key.

  With both fixed, ran the complete logged-in flow for real against the
  live site, every step a genuine HTTP request against the deployed
  service (session cookies, not a bypass): log in -> save a real Kaggle
  token -> submit a parametric request with *no token in the request
  body* (proving the saved-token fallback works) -> poll to completion
  (real Kaggle round trip) -> fetch the real STL (3084 bytes) and preview
  PNG (301528 bytes) via both the job-status route and the
  dashboard-specific route (two different code paths, both confirmed) ->
  confirm the job appears in dashboard history with a 7-day expiry ->
  delete the job (dashboard goes back to empty) -> delete the saved token
  (`has_saved_token` back to false) -> delete the account entirely ->
  confirm via a follow-up login attempt that the account is genuinely
  gone (401, not "already exists"). Every step passed. Also cleaned up
  the throwaway test account created during earlier live-deploy
  diagnosis, as offered back when it was first created.

  105 tests passing (8 new across this incident: a `sys.executable`/
  error-wrapping regression suite for kaggle_client, plus malformed-key
  regression tests for token_crypto and its route-level 503 behavior).

  Also recorded as a standing preference for future sessions: proactively
  email the developer (not just wait in chat) when blocked on something
  only they can do and they might be away from their computer -- stated
  directly during this debugging session, saved to memory.

  This closes out every milestone in the original plan, including the
  creative tier that was deferred back in Milestone 2. PrintForge is
  functionally complete per its own spec. Remaining open item: `ADMIN_TOKEN`
  is not yet set on Render (only the admin feedback-reading view is
  affected, nothing visitor-facing).

- 2026-08-27/28: Milestone 8 kicked off, two ordered pieces of work per
  direct instruction: a design/visual polish pass first, then the
  AI-refined-prompt feature (full spec added above).

  Tooling install: `npx skills add emilkowalski/skills` and `npx skills
  add Leonxlnx/taste-skill` (25 design/animation/taste skills, both
  flagged 0 security alerts by the installer's own scan), `npx impeccable
  install` (anti-pattern detector, v4.1.1). `claude mcp add playwright`
  could not run -- no standalone `claude` CLI binary exists in this
  session's runtime -- substituted the already-available Claude_Browser
  tools instead, which serve the same "screenshot and verify" purpose;
  told the developer this substitution directly rather than silently
  treating it as done. Node.js itself had to be installed first via
  winget, which hit a UAC elevation prompt that couldn't be approved
  non-interactively -- emailed the developer per their standing
  preference (see memory) rather than waiting silently; they approved it
  from their machine and the install completed (Node v24.19.0).

  Design pass (2 commits, both pushed): read the `emil-design-eng` and
  `high-end-visual-design` skills for concrete guidance rather than
  guessing at "good design," then applied the former's craft-level
  patterns (custom cubic-bezier easings, explicit `:active`/
  `:focus-visible` states, entrance animations with a real purpose --
  "preventing jarring changes," not decoration) globally via style.css:
  custom easing variables, press feedback on every button/tier-option,
  keyboard focus outlines (previously undefined outside form inputs), a
  slide-up cookie-banner entrance, a scroll-reveal for the landing page's
  hero/steps/example sections, fade-in on form banners and the job/result
  status cards, and a missing focus transition on textarea/input/select
  borders. Deliberately did not chase `high-end-visual-design`'s more
  aggressive agency-tier theatrics (banned-fonts list, double-bezel
  nested cards, noise overlays) -- PrintForge is a functional utility
  tool, not a marketing site, and the existing system-font stack/clean
  card style is a reasonable, pragmatic choice worth keeping.

  Real, non-hypothetical finding during verification: this session's
  Browser pane tools don't actually composite/paint frames (confirmed via
  repeated `screenshot` timeouts: "the page is not compositing frames"),
  which also silently breaks IntersectionObserver callbacks and in-flight
  CSS transitions in this specific environment (proved via direct
  `getComputedStyle` probing -- an inline `transition: none` override
  immediately reported the correct target value, while the transitioned
  version stayed stuck at its start value indefinitely). Real screenshots
  and live-transition verification were not available here; adapted by
  running a local dev server and verifying structurally instead
  (accessibility tree, console errors, computed-style/cascade-specificity
  checks) -- and said so plainly rather than claiming a screenshot-based
  verification that didn't happen.

  That structural verification caught a real bug before it shipped: the
  first draft of the scroll-reveal hid `.reveal` elements at `opacity:0`
  unconditionally in CSS, so any JS error or unsupported
  IntersectionObserver would have left real landing-page content
  permanently invisible for actual visitors -- not just an artifact of
  the non-compositing test session. Fixed with proper progressive
  enhancement: elements are visible by default, JS only opts into the
  hidden starting state after confirming the observer is wired up, and a
  1.5s fallback timeout force-reveals everything regardless of whether an
  observer entry ever fires. 105/105 backend tests still passing
  throughout (no backend touched, confirmed after each commit).

  AI-refined-prompt feature, Milestone 1 (Kaggle kernel) -- done.
  `kaggle_kernel/printforge_prompt_refiner/`: Qwen2.5-1.5B-Instruct
  (Apache 2.0, ungated, ~2.4GB), CPU-only via `enable_gpu: false` --
  chosen deliberately so unlimited refinement rounds never touch the
  weekly GPU-hour quota the fast/refined 3D tiers depend on, matching the
  parametric tier's proven no-GPU-kernel precedent rather than assuming
  a new pattern would work. Takes IDEA (raw idea, or previous round's
  output) and FEEDBACK (empty on round 1, else the visitor's requested
  change) as literals rewritten by kernel_builder.py before each push --
  same safe function-based `re.sub` injection AI_3D_FACTORY's history
  already proved necessary over naive string replacement, to avoid
  mangling backslashes/quotes in visitor text. Writes `report.json` with
  `{"passed": bool, "refined_prompt": str}`, matching the existing
  fast/refined kernels' report convention.

  Verified with two real Kaggle runs on the developer's own account
  (`levlar`), pushed/polled/retrieved manually exactly like every other
  kernel in this project's history, before any pipeline code was
  written: round 1, the spec's own example ("batman phone holder") ->
  a genuinely detailed 502-character prompt covering material, tilt
  angle, edge treatment, and stability, taking ~2.5 minutes end to end
  (kernel startup + pip install + model download + inference). Round 2,
  feeding round 1's output back in as IDEA with FEEDBACK = "make it look
  more like actual Batman armor, with a bat-shaped silhouette and
  armored plating" -> the model correctly revised only the relevant
  clauses ("armored plating," "bat-shaped silhouette") while leaving the
  rest of the prompt consistent, taking ~3 minutes. Confirmed via
  `kaggle quota` before and after both runs: GPU quota unchanged (28.02h
  remaining both times) -- direct proof the CPU-only design choice
  achieves its actual goal, not just a theoretical claim.

  Milestone 2 (pipeline integration) -- done. Extended kernel_builder.py's
  TIERS with a "refine" entry (CPU-only) and its build_kernel() with
  idea/feedback injection, reusing the same safe function-based `re.sub`
  pattern PROMPT already used (not naive string replacement -- see
  AI_3D_FACTORY's history on why that mangles backslashes). New
  backend/app/services/refinement.py mirrors generation.py's submit/
  check/_retrieve_and_finalize shape closely, but with two deliberate,
  documented differences: refinement rounds are never mirrored into
  Postgres via accounts.record_job_start/update (a round isn't a
  deliverable for dashboard history, just an ephemeral pre-processing
  step -- only the real generation job submitted after Approve gets
  recorded, unchanged), and refinement submissions skip rate_limit's
  5/day cap while still honoring its concurrency check. That skip is
  deliberate, not an oversight: the cap is shared with 3D-generation
  submissions in the same jobs.py store, and this feature's spec
  explicitly calls for *unlimited* iteration rounds -- applying the daily
  cap here would let a few refinement rounds silently exhaust a visitor's
  ability to submit their actual generation job the same day. New routes
  in backend/app/routes/refine.py (POST /api/refine, GET
  /api/refine/{id}), registered in main.py.

  20 new tests (kernel_builder's refine-tier injection incl. an
  empty-feedback round 1; refinement.py's validation/rate-limit-skip/
  concurrency-still-blocks/complete/refine_failed/error paths; HTTP-level
  route tests), all mocking Kaggle calls per this project's standing
  rule. 125/125 tests passing.

  Then proved the actual requirement -- "no manual steps" -- with one
  real, unmocked round trip through the live Python code path itself
  (not the manual kernel-push dance Milestone 1 used): POST /api/refine
  against a local dev server with the developer's real Kaggle token and
  "a batman phone holder", then polled GET /api/refine/{id} until
  status flipped to "complete" with a genuine, detailed refined_prompt
  -- confirming kernel_builder's injection, kaggle_client's push/status/
  retrieve, and refinement.py's report-parsing all work correctly
  through the real API surface, not just in isolation. One thing
  double-checked rather than assumed benign: the returned text displayed
  a corrupted apostrophe (`Batman�s`) in this session's Git Bash
  terminal. Inspected the raw report.json bytes on disk directly (not
  just the terminal output) and confirmed they correctly contain
  `’` (a proper Unicode right single quote) -- the corruption is
  purely this terminal's console-encoding display, not a bug in the
  stored data or the JSON round trip a real browser's `fetch()` would
  see. No fix needed; documented so a future session doesn't waste time
  re-diagnosing the same non-bug.

  While setting up a local dev server for this and the earlier design
  pass, found and fixed a real (if minor) dev-tooling bug: launch.json's
  `uvicorn --reload` was watching this session's own worktree directory
  by default instead of PrintForge/backend (where `--app-dir` actually
  pointed), so the very first end-to-end attempt hit a stale process and
  404'd on the brand-new /api/refine route. Fixed with an explicit
  `--reload-dir`; confirmed via the server's own startup log line
  ("Will watch for changes in...") before retrying, rather than guessing
  the fix worked.

  Milestones 3+4 (iteration UI, wired into the existing generation flow)
  -- done together, deliberately: the iteration UI's whole point is to
  end in a working generation submission, so building it without also
  wiring the final step would mean testing a dead end. One combined
  commit, but both milestones' requirements are separately satisfied and
  separately verified below.

  frontend/create.html: a new "Generation mode" choice (Quick/Advanced)
  appears alongside the existing quality-tier choice whenever a request
  classifies as creative, reusing the exact same `.tier-option` visual
  component for consistency (careful to scope the two click handlers by
  `[data-tier]` vs `[data-mode]` attribute selectors, not just the shared
  class, so they don't cross-bind). Advanced mode reveals a panel with a
  "Refine my prompt" button, a status/spinner card while a round is in
  flight, a rendered refinement history (every prior round's input/
  feedback/output), and once a round completes, "Approve & use this
  prompt" / "Request changes" actions -- the latter reveals a feedback
  textarea that starts another round with the previous output as the new
  idea. The GPU-hour/time tradeoff and "no limit on rounds" are stated
  up front in the panel, not just implied.

  Milestone 4's requirement (wire the approved prompt into the *existing*
  fast/refined flow, unchanged) is satisfied about as directly as
  possible: Approve simply writes the refined text into the same
  `#prompt` textarea the Quick path already uses, then re-enables the
  existing, completely untouched submit button and `form.addEventListener
  ("submit", ...)` handler. Zero lines of the actual submission code
  changed -- confirmed by diffing that handler against its pre-Milestone-8
  version. The submit button is hidden/disabled for the entire time
  Advanced mode has no approved prompt yet (so nothing can be submitted
  mid-refinement), and reappears immediately on Approve or on switching
  back to Quick mode.

  Verified through the actual UI, not just by reading the code -- with
  one adaptation forced by this session's environment: real screenshots
  still aren't available here (see the design-pass entry above), and
  driving the real token through browser automation would mean a secret
  value passing through this session's tool-call layer for a test that
  doesn't need to touch a real Kaggle account at all (Milestone 2 already
  proved the real backend round trip independently). Instead, mocked
  `window.fetch` in the live page for `/api/refine` and drove the actual
  buttons end to end: clicked "Refine my prompt" -> confirmed the
  status/spinner state and hidden submit button -> resolved to a result
  with the refined text shown and history rendered -> clicked "Request
  changes", entered feedback, clicked "Refine again" -> confirmed round 2
  appended correctly to history with the right label -> clicked "Approve"
  -> confirmed the textarea now holds the approved text and the submit
  button is visible and enabled again. Also confirmed the Quick path
  (mode left at its default) never reveals the advanced panel and leaves
  the submit button untouched. 125/125 backend tests still passing
  (frontend-only change).

  Found and fixed a real dev-environment issue while testing this: the
  local server was serving updated HTML correctly (confirmed via a
  direct `curl`), but this session's Browser pane kept rendering a stale
  cached version even after a forced reload -- worked around with a
  cache-busting query string (`?v=N`) per navigation, which reliably
  picked up the new markup. Noted here in case a future session hits the
  same thing.

  Milestone 5 (FAQ + full live smoke test) -- done. This closes out
  Milestone 8 and the entire two-part task for this session.

  FAQ: added a "What's the 'Advanced: AI-refined prompt' option?" entry
  explaining what it does, when it's worth the tradeoff over Quick mode,
  and its per-round time/GPU-hour cost -- committed and pushed on its own
  (frontend/faq.html only).

  Full live smoke test -- both paths, real Kaggle calls, against the
  actual deployed site (not local dev, not mocked), same rigor the
  project's other milestones have held to:

  Advanced path, real and complete end to end: submitted round 1
  ("batman phone holder") against the live site, polled to completion
  (a genuine 596-character refined prompt); fed that back in as round 2
  with feedback "make it more armored, with a bat-shaped silhouette" --
  the model correctly wove in "heavily armored," "Batmobile"-inspired
  styling, and reinforced plating while keeping the rest of the prompt
  consistent; approved that result and submitted it to the real
  fast-tier generation kernel via the *unchanged* /api/create endpoint;
  polled to completion; fetched both the resulting preview.png (297KB)
  and model.stl (580KB) from the live site and confirmed both actually
  downloaded (200, correct content-types) rather than just checking the
  job status flipped to "complete."

  Quick path regression check, also real and live: submitted "a viking
  helmet" as a plain creative request with no refinement involved,
  through the same /api/create endpoint, and confirmed it still
  completed normally -- direct evidence (not just code review) that nothing
  in this milestone's create.html changes broke the pre-existing flow.

  Kaggle quota accounted for precisely, not estimated: 2.16h/30h used
  after this test (up from 1.98h before it started), meaning the two
  live 3D-generation runs (Advanced's final gen + the Quick regression
  check) cost 0.18h combined -- and the *two refinement rounds in
  between cost nothing*, reconfirming under real production conditions
  (not just the earlier isolated kernel test) that the CPU-only design
  choice for the refiner achieves its actual purpose.

  This completes Milestone 8 in full: both the design/visual polish pass
  and the AI-refined-prompt feature (all 5 of its sub-milestones) are
  done, tested, and verified live. Nothing further is planned without
  additional direction.

- 2026-08-28/30: Visual redesign -- scrapped the dark/orange theme
  entirely per direct instruction ("the current design isn't landing
  well... a genuine visual redesign, not just incremental polish").

  Step 1, a hard prerequisite before any design work: fixed real
  screenshot verification. This session's built-in Browser pane tools
  cannot composite frames at all (confirmed across two separate
  sessions -- not a fluke), so a genuinely different approach was
  needed, not another workaround. Installed Playwright directly (`npm
  install playwright` + `npx playwright install chromium`) and drove it
  from a plain Node script. Playwright's own bundled Chromium build
  fails to launch on this machine specifically (`spawn UNKNOWN` via
  Node, `side-by-side configuration is incorrect` via PowerShell) --
  diagnosed as a real, local Windows problem, not a sandboxing artifact:
  the registry claims VC++ Redistributable 14.50.35719.00 is installed,
  but vcruntime140.dll/msvcp140.dll are missing from System32. Rather
  than repair system files (a system-modifying action requiring the
  developer's own action), pointed Playwright at the system's existing
  Edge install instead (`channel: 'msedge'`), which launched cleanly.
  Proved this was real, not assumed: first screenshot genuinely
  displayed Render's cold-start loading splash (the live site's free
  tier was asleep), and a second attempt after the app woke up showed
  the actual rendered landing page -- concrete, visually-verified proof
  the pipeline captures real pixels, exactly what the developer asked to
  confirm before any redesign work began.

  Built a reusable capture script mocking backend routes (`page.route()`
  for /api/me, /api/classify, /api/refine, /api/jobs/*, /api/dashboard/
  jobs) so every page state -- landing, create empty/Quick-revealed/
  Advanced-with-history, job status, result, dashboard with job history,
  FAQ -- could be captured deterministically against a local dev server,
  without needing a real Kaggle token in the loop. Captured a full
  before-state baseline and published it as a gallery artifact so the
  developer could see the actual current state, not a description of it,
  before any change was made.

  Real bug found via this process, not assumed: the first "before"
  capture of the landing page showed the "A real example" section
  completely blank. Root cause was the earlier design pass's own
  scroll-reveal (see the design-pass entry above) racing against
  Playwright's screenshot timing -- not a real user-facing bug (real
  users get the 1.5s JS fallback), but proof the mechanism was fragile
  enough to warrant a longer safety margin in the capture script
  (400ms -> 1800ms wait) rather than trusting the first render.

  Color direction (developer-specified, applied deliberately rather than
  retrofitted): warm neutral palette -- cream/beige base (#faf6f0 bg,
  #f1e9dd card surface), warm espresso text (#2a2420, not pure black),
  terracotta primary accent (#b5502f), sage secondary accent (#5f6e52)
  for variety/tags/secondary emphasis. Every text/background/button pair
  was checked against WCAG AA (4.5:1 normal text, 3:1 large text/UI)
  with an actual relative-luminance calculation, not eyeballed -- the
  initial candidate terracotta/sage values were adjusted (darkened)
  after the first round of checks came back under 4.5:1 for white
  button text; the final palette clears every pairing with real margin
  (5.06:1 white-on-terracotta, 5.47:1 white-on-sage, 4.70:1 terracotta-
  on-background text, etc.) Warning-on-background text was found to only
  hit 3.00:1 (large-text-only), so warning banners keep the existing
  tinted-background + dark-text pattern rather than using the warning
  hue as small text color anywhere.

  Rebuilt style.css's tokens from scratch: added a real type scale
  (Fraunces serif for editorial moments -- hero h1, section h2 -- paired
  with Work Sans for everything else, a deliberate pairing since
  PrintForge is about a warm, tactile, crafted physical-object product,
  not a cold SaaS tool) and a 4px-based spacing scale (--space-1 through
  --space-24), replacing scattered arbitrary pixel values. Nav's own CTA
  was deliberately downgraded in visual weight (the hero already has the
  real primary CTA directly below it -- two identical terracotta buttons
  stacked in one view were competing, not guiding, in the old design).
  Step-number circles changed from solid terracotta fills to outlined
  rings with terracotta text -- one of several deliberate reductions in
  how often the accent color repeats per view, per the "one accent
  moment" principle.

  Accessibility fixes that were real gaps, not just polish: the tier/
  mode selection cards were plain `<div>`s with onclick handlers --
  completely unreachable by keyboard, invisible to screen readers as
  anything other than static text. Rebuilt as a proper ARIA radiogroup
  pattern (role="radiogroup"/"radio", aria-checked, roving tabindex,
  arrow-key navigation matching native `<input type="radio">` behavior)
  via a new reusable `initRadioGroup()` helper in app.js, used by both
  the quality-tier and generation-mode groups on /create. Verified via
  Playwright driving real keyboard events (not just reading the code):
  focusing the Quick option and pressing ArrowRight correctly moved
  focus AND selection to Advanced, updated aria-checked/tabindex on both
  options, and triggered the same panel-visibility logic a mouse click
  would. Selected-state affordance also upgraded from a subtle border-
  color-only change (a11y risk: color alone) to a filled checkmark
  circle, so selection is visible via shape, not just color.

  Skeleton loaders replaced bare spinners/blank states per explicit
  requirement: job.html's status card now shows a shimmering placeholder
  preview-image block + text lines (hinting at the eventual result
  layout) instead of a spinner floating in empty space; dashboard.html
  shows shimmering placeholder job rows instead of a plain "Loading…"
  string while /api/dashboard/jobs is in flight. Both respect
  prefers-reduced-motion (static tinted block, no shimmer animation).
  Added a semantic `.status-pill` component (colored dot + text label,
  never color alone) for job status on the dashboard.

  Real bug caught by the after-screenshots, not just code review: the
  refinement-history banner on /create rendered with a cramped, wrapped
  3-line label sitting oddly next to the body text. Root cause: `.banner`
  is `display:flex`, and the history markup had `<strong>` and the
  content `<div>` as direct siblings inside it -- meaning they became
  two separate flex items instead of one grouped block. Fixed by
  wrapping both in a single container div; re-screenshotted and
  confirmed the fix (cropped before/after comparison of just that
  region, not just "looks fine at a glance").

  Separately flagged by the developer: a real production 429 from
  Kaggle's API during job-status polling. Root cause: jobs.py's
  `should_recheck()` gated real Kaggle status calls to a flat 10 seconds
  for a job's *entire* run, which for the multi-minute generation jobs
  this project already knows are normal (see Milestone 8's own timing
  notes) adds up to many dozens of calls over a single job's lifetime --
  apparently enough to trip a rate limit on Kaggle's side. Fixed with
  exponential backoff: `should_recheck()` now grows the required
  interval 1.5x per check (10s -> 15s -> 22.5s ...) capped at 60s,
  tracked via a new per-job `check_count` field and a `record_check()`
  helper (replacing the old inline `last_checked_at` update) shared by
  both generation.py and refinement.py so the fix applies uniformly to
  3D-generation jobs and refinement rounds alike. Confirmed the frontend
  polling interval (job.html's 6s setTimeout loop) was never actually
  the cause -- it only controls how often the browser asks *our*
  backend, not how often our backend calls Kaggle; should_recheck()
  already gated that independently of frontend poll frequency, so no
  frontend change was needed, just the backend gate. 6 new tests in
  test_jobs.py cover the fresh-job/post-check/growing-interval/capped-
  at-max/unknown-job cases. 131/131 tests passing project-wide.

  Verified mobile responsiveness (390px viewport, real Playwright
  screenshots) and keyboard-only focus states (real Tab-key screenshots
  showing the terracotta focus ring on nav links) -- both held up
  without further changes needed.

  Committed in three pieces per the developer's "small commits" working
  style: (1) the design-token/type-scale/spacing-scale rewrite in
  style.css, (2) applying the new system across every page plus the
  accessible radio-group and skeleton loaders, (3) the Kaggle-polling
  backoff fix, kept separate since it's backend logic unrelated to the
  visual work. Next: none planned -- awaiting further direction.

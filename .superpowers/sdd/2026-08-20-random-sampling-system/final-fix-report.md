# Final review fix report

Date: 2026-08-24
Branch: `feature/random-sampling-system`
Fix base: `273aa7a65b5931e2067ba4a77f71391896301ba0`
Implementation commit: `09eef0df6ea89ebcdbc12c9ee34ef38ed712d33d`

## Outcome

All two Important and five Minor findings from `final-fix-brief.md` were fixed with regression coverage. Existing audit semantics, historical/partial demo-task preservation, assignment/drawing behavior, and local-demo documentation were retained. No schema migration was required.

## Root causes and fixes

### Important 1 - whole-command seed atomicity

Root cause: `seed_demo` wrote users, password hashes, roles, active/name fields, and personnel-group membership before entering the task/candidate transaction.

Fix: one outer `transaction.atomic()` now encloses every database write in `handle()`. Success messages remain after that context, so failed commits print nothing. The regression injects failure during candidate creation and compares exact pre/post snapshots for users (including password hashes, roles, names and active state), groups, memberships, tasks, and candidates. Existing successful rerun tests continue to prove historical/completed and pre-existing partial tasks are not overwritten.

Files: `sampling/management/commands/seed_demo.py`, `sampling/tests/test_seed_demo.py`.

### Important 2 - administrator candidate editing

Root cause: the audited `update_candidate()` service and form already existed, but management URLs, view, template, and detail-page control exposed only add/delete.

Fix: added administrator-gated GET/POST candidate edit routing and form rendering. The view sends only changed allowlisted fields to `update_candidate()` and renders stable form/non-field errors without duplicating freeze or audit logic. The task detail exposes Edit only for draft/ready tasks.

Coverage: successful edit plus concrete `material.updated` before/after audit data; executed-task freeze; invalid form persistence/error rendering; sampler GET/POST 403; CSRF rejection; detail-page edit control.

Files: `sampling/management_urls.py`, `sampling/management_views.py`, `templates/management/tasks/candidate_form.html`, `templates/management/tasks/detail.html`, `sampling/tests/test_management_views.py`.

### Minor 1 - production SECRET_KEY

Root cause: settings always supplied a public fallback, including production-like `DEBUG=false` startup.

Fix: DEBUG mode retains the local fallback; missing/empty `DJANGO_SECRET_KEY` with DEBUG false raises `ImproperlyConfigured`. README now explicitly requires a unique replacement key outside the local demo.

Files: `config/settings.py`, `accounts/tests/test_settings.py`, `README.md`.

### Minor 2 - cancellation state and idempotency

Root cause: `cancel_task()` unconditionally wrote cancelled state and an audit event, so repeated or concurrent cancellation duplicated `task.cancelled` logs and unknown source states were accepted.

Fix: explicitly allowed source states are draft, ready, assigned, in-progress, and completed, matching the existing management control. Already-cancelled calls return the locked task idempotently; unknown states are rejected. The existing task row lock serializes concurrent attempts.

Coverage: every allowed source state, repeated cancellation, invalid state, and a two-thread MySQL row-lock regression proving one audit event.

Files: `sampling/services/lifecycle.py`, `sampling/tests/test_lifecycle.py`, `sampling/tests/test_lifecycle_concurrency.py`.

### Minor 3 - DEBUG avatar serving

Root cause: the project URLConf did not append Django's documented DEBUG media helper.

Fix: `/media/` is appended with `static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` only when DEBUG is true. A real uploaded profile avatar is fetched through the reloaded DEBUG root URLConf and the test removes the exact uploaded file.

Files: `config/urls.py`, `accounts/tests/test_media.py`.

### Minor 4 - management result ordering

Root cause: task detail used an unordered nested prefetch and relied on relation/default database order.

Fix: task-detail prefetch orders batches by persisted `version` and nested results by persisted `sequence` while retaining `material` eager loading. The rendered-order regression creates inverse insertion order and asserts version/sequence order in output.

Files: `sampling/management_views.py`, `sampling/tests/test_management_views.py`.

### Minor 5 - model helper cannot reopen frozen tasks

Root cause: `SamplingTask.mark_ready()` validated pool size but never validated the source status, so any persisted state could be changed to ready.

Fix: direct model transition now permits draft to ready only. The audited lifecycle service's supported idempotent ready behavior is unchanged because it handles READY before invoking model transition logic.

Files: `sampling/models.py`, `sampling/tests/test_models.py`.

## TDD red/green evidence

Initial focused RED command:

```powershell
.\.venv\Scripts\python.exe manage.py test sampling.tests.test_seed_demo sampling.tests.test_lifecycle sampling.tests.test_lifecycle_concurrency sampling.tests.test_models sampling.tests.test_management_views accounts.tests.test_settings accounts.tests.test_media -v 2
```

Result before production changes: 48 tests found; expected `FAILED (failures=12, errors=5)`. Failures/errors identified the exact seed snapshot drift, duplicate cancellation audits (sequential and concurrent), accepted unknown cancellation state, mark-ready reopen paths, missing candidate-edit route, unordered results, missing media route, and production secret fallback.

GREEN evidence:

- Seed-focused run after outer transaction: 6/6 passed.
- Remaining focused run exposed one test-environment-specific media 404. Investigation showed Django's test runner disables DEBUG before URLConf construction; the regression was corrected to reload the real URLConf under DEBUG true and restore caches afterward.
- Final media mutation check temporarily removed only `config/urls.py` changes: the final avatar regression failed 404 as expected, then the fix was restored.
- Final focused command above: 48/48 passed in 7.770s.

## Final verification

```powershell
.\.venv\Scripts\python.exe manage.py test -v 2
```

Result: 132/132 passed in 13.235s on MySQL. Assignment, drawing, and cancellation concurrency tests all executed and passed; none were skipped.

```powershell
.\.venv\Scripts\python.exe manage.py check
```

Result: `System check identified no issues (0 silenced).`

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Result: `No changes detected`.

```powershell
git diff --check
```

Result: exit 0; only informational Git line-ending warnings were emitted for existing Windows working-copy policy.

## Self-review

- Confirmed `seed_demo.py` contains exactly one `transaction.atomic()` and stdout writes occur after it.
- Confirmed candidate editing calls the existing service and does not reproduce lifecycle checks in the view.
- Confirmed cancellation keeps audit history immutable and concurrent retries create a single event.
- Confirmed media routing is DEBUG-only and production missing-secret startup fails deterministically.
- Confirmed no migrations, credentials, generated media, or unrelated files are included.

## Concerns

None.

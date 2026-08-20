# Random Sampling System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Windows-ready Django application with a mobile H5 sampling workflow, a desktop management console, server-side random assignment and sampling, MySQL persistence, and task-only audit history.

**Architecture:** A Django monolith exposes role-gated server-rendered pages and small JSON endpoints. Domain writes live in transaction-wrapped service functions so templates, views, and tests share the same assignment, draw, redraw, import, and audit behavior. MySQL 8 is the runtime database; Django templates, Bootstrap, and focused vanilla JavaScript provide the responsive UI without a separate frontend build.

**Tech Stack:** Python 3.12+, Django 5.2 LTS, MySQL 8, PyMySQL 1.1, python-dotenv 1.0+, Bootstrap 5.3, vanilla JavaScript, Django TestCase/TransactionTestCase.

**Spec:** `docs/superpowers/specs/2026-08-18-random-sampling-system-design.md`

**Version references:** [Django 5.2 LTS release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) and [MySQL 8.4 LTS release model](https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html).

## Global Constraints

- Runtime database is MySQL 8; SQLite is not an accepted runtime fallback.
- Administrators can use only `/manage/`; samplers can use only `/m/`; every view and mutation rechecks the role server-side.
- Assignment chooses exactly one member from the selected custom personnel group without filtering for account state, workload, leave, or schedule.
- Material draws are server-generated, without replacement, persisted before animation, and immutable after locking.
- Candidate materials, draw count, and personnel group freeze after first execution.
- Audit records contain task events only; login and profile edits never create task audit rows.
- The mobile and management UI must preserve the retained template's blue-white palette, rounded cards, light shadows, gradient primary actions, status chips, data summaries, and clear navigation.
- The retained visual reference is `C:/Users/Eternal/.codex/skills/artifact-template-ui/assets/reference.png`; inspect it before implementing CSS and do not modify it.
- Use TDD for every domain behavior: observe the named test fail, write the minimal implementation, and observe it pass.
- Commit only files belonging to the current task; preserve unrelated working-tree changes.

## File Structure

```text
selectrom/
├── manage.py                         # Django command entry point
├── requirements.txt                  # Pinned production/test dependencies
├── .env.example                      # Safe MySQL and Django configuration example
├── .gitignore                        # Local secrets, caches, uploads, and build artifacts
├── docker-compose.yml                # Optional local MySQL 8 service
├── scripts/start.ps1                 # Windows setup checks, migrate, and runserver
├── config/
│   ├── settings.py                   # Environment, installed apps, MySQL, static/media
│   ├── urls.py                       # Route namespaces
│   └── wsgi.py                       # WSGI entry point
├── accounts/
│   ├── models.py                     # Custom user and roles
│   ├── forms.py                      # Login, profile, password, admin user forms
│   ├── decorators.py                 # Role gates
│   ├── views.py                      # Login/logout/profile/user-management views
│   ├── urls.py                       # Authentication and profile routes
│   ├── admin_urls.py                 # Management user routes
│   └── tests/                        # Model, role, profile, and management tests
├── personnel/
│   ├── models.py                     # Custom sampler groups
│   ├── signals.py                    # Enforce sampler-only membership
│   ├── forms.py                      # Group create/edit form
│   ├── views.py                      # Group management views
│   ├── urls.py                       # Group routes
│   └── tests/                        # Group behavior and permissions
├── sampling/
│   ├── models.py                     # Tasks, candidates, assignments, batches, results
│   ├── forms.py                      # Task, material, CSV, reassign, redraw forms
│   ├── services/
│   │   ├── assignment.py             # Atomic random personnel assignment
│   │   ├── drawing.py                # Atomic material drawing and redraw batches
│   │   ├── imports.py                # Transactional CSV validation/import
│   │   └── lifecycle.py              # Task edit, readiness, cancel, and complete rules
│   ├── management_views.py           # Desktop task CRUD and action endpoints
│   ├── mobile_views.py               # H5 dashboard, reminders, draw, complete
│   ├── management_urls.py            # `/manage/tasks/` routes
│   ├── mobile_urls.py                # `/m/` routes
│   └── tests/                        # Shared fixtures, models, services, CSV, views, concurrency
├── audit/
│   ├── models.py                     # TaskAuditLog only
│   ├── services.py                   # Explicit task event writer
│   ├── views.py                      # Filtered management log list
│   ├── urls.py                       # Log routes
│   └── tests/                        # Task-only audit coverage
├── templates/
│   ├── accounts/                     # Login/profile/user templates
│   ├── management/                   # Desktop shell, dashboard, tasks, groups, logs
│   └── mobile/                       # Mobile shell, dashboard, reminders, draw, profile
├── static/
│   ├── css/tokens.css                # Shared visual tokens
│   ├── css/management.css            # Desktop layout
│   ├── css/mobile.css                # H5 layout and responsive behavior
│   └── js/sampling-animation.js      # Display-only draw animation
├── media/                             # Runtime avatar uploads, ignored by Git
├── samples/materials.csv             # UTF-8 CSV example
└── README.md                          # Local install, demo accounts, and walkthrough
```

---

### Task 1: Django Foundation and MySQL Configuration

**Files:**
- Create: `manage.py`
- Create: `config/__init__.py`
- Create: `config/settings.py`
- Create: `config/urls.py`
- Create: `config/wsgi.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `docker-compose.yml`
- Create: `accounts/tests/test_smoke.py`

**Interfaces:**
- Consumes: MySQL host, port, database, user, and password from environment variables.
- Produces: configured Django project; `config.settings`; root URL resolver; reusable MySQL test database configuration.

- [ ] **Step 1: Write the failing project smoke test**

```python
# accounts/tests/test_smoke.py
from django.test import SimpleTestCase
from django.urls import reverse


class ProjectSmokeTests(SimpleTestCase):
    def test_health_route(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
```

- [ ] **Step 2: Run the test to verify the project does not exist yet**

Run: `python -m django test accounts.tests.test_smoke -v 2`

Expected: FAIL because `manage.py`, `config.settings`, or the `health` route is missing.

- [ ] **Step 3: Create the environment and dependency files**

```text
# requirements.txt
Django>=5.2,<5.3
PyMySQL>=1.1,<2
python-dotenv>=1.0,<2
Pillow>=11,<12
```

```dotenv
# .env.example
DJANGO_SECRET_KEY=replace-this-for-local-use
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
MYSQL_DATABASE=selectrom
MYSQL_USER=selectrom
MYSQL_PASSWORD=selectrom-local-password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

Configure `config/settings.py` to call `pymysql.install_as_MySQLdb()`, load `.env`, set `AUTH_USER_MODEL = "accounts.User"`, and define `DATABASES["default"]` with engine `django.db.backends.mysql`, `utf8mb4`, strict SQL mode, and `CONN_MAX_AGE = 60`.

- [ ] **Step 4: Add the minimal health endpoint and root URLs**

```python
# config/urls.py
from django.http import JsonResponse
from django.urls import path


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [path("health/", health, name="health")]
```

- [ ] **Step 5: Add optional MySQL Docker configuration**

```yaml
# docker-compose.yml
services:
  db:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: selectrom
      MYSQL_USER: selectrom
      MYSQL_PASSWORD: selectrom-local-password
      MYSQL_ROOT_PASSWORD: selectrom-root-password
    ports:
      - "3306:3306"
    volumes:
      - selectrom_mysql:/var/lib/mysql
    command: ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_0900_ai_ci"]
volumes:
  selectrom_mysql:
```

- [ ] **Step 6: Install dependencies and run the smoke test**

Run: `python -m pip install -r requirements.txt`

Run: `python manage.py test accounts.tests.test_smoke -v 2`

Expected: PASS with 1 test.

- [ ] **Step 7: Commit the foundation**

```bash
git add manage.py config requirements.txt .env.example .gitignore docker-compose.yml accounts/tests/test_smoke.py
git commit -m "chore: initialize Django MySQL project"
```

---

### Task 2: Custom Users, Authentication, and Role Gates

**Files:**
- Create: `accounts/apps.py`
- Create: `accounts/models.py`
- Create: `accounts/forms.py`
- Create: `accounts/decorators.py`
- Create: `accounts/views.py`
- Create: `accounts/urls.py`
- Create: `accounts/migrations/0001_initial.py`
- Create: `accounts/tests/test_roles.py`
- Create: `templates/accounts/login.html`
- Create: `templates/accounts/profile.html`
- Modify: `config/settings.py`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: Django authentication sessions.
- Produces: `accounts.models.User`; `User.Role.ADMIN`; `User.Role.SAMPLER`; `admin_required(view)`; `sampler_required(view)`; `/login/`, `/logout/`, `/m/profile/`.

- [ ] **Step 1: Write failing role and login-routing tests**

```python
# accounts/tests/test_roles.py
from django.test import TestCase
from django.urls import reverse
from accounts.models import User


class RoleGateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="Pass12345!", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("sampler", password="Pass12345!", role=User.Role.SAMPLER)

    def test_admin_login_redirects_to_management(self):
        response = self.client.post(reverse("accounts:login"), {"username": "admin", "password": "Pass12345!"})
        self.assertRedirects(response, "/manage/")

    def test_sampler_cannot_open_management(self):
        self.client.force_login(self.sampler)
        self.assertEqual(self.client.get("/manage/").status_code, 403)

    def test_admin_cannot_open_mobile(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/m/").status_code, 403)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python manage.py test accounts.tests.test_roles -v 2`

Expected: FAIL because the custom user, role decorators, and routes are absent.

- [ ] **Step 3: Implement the custom user and role decorators**

```python
# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        SAMPLER = "sampler", "抽样人员"

    role = models.CharField(max_length=16, choices=Role.choices)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
```

```python
# accounts/decorators.py
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from accounts.models import User


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if request.user.role != role:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


admin_required = role_required(User.Role.ADMIN)
sampler_required = role_required(User.Role.SAMPLER)
```

- [ ] **Step 4: Implement login, logout, profile update, and temporary dashboard routes**

Use Django `AuthenticationForm`; redirect administrators to `/manage/` and samplers to `/m/`. `ProfileForm` exposes only `first_name`, `last_name`, `phone`, and `avatar`. Add minimal role-gated dashboard views returning HTTP 200; later UI tasks replace their response bodies without changing their route names.

- [ ] **Step 5: Generate the migration and run tests**

Run: `python manage.py makemigrations accounts`

Run: `python manage.py test accounts.tests.test_roles -v 2`

Expected: PASS with all role and routing tests.

- [ ] **Step 6: Commit authentication**

```bash
git add accounts config templates/accounts
git commit -m "feat: add role-gated authentication"
```

---

### Task 3: Personnel Groups and Management

**Files:**
- Create: `personnel/apps.py`
- Create: `personnel/models.py`
- Create: `personnel/signals.py`
- Create: `personnel/forms.py`
- Create: `personnel/views.py`
- Create: `personnel/urls.py`
- Create: `personnel/migrations/0001_initial.py`
- Create: `personnel/tests/test_groups.py`
- Create: `templates/management/groups/list.html`
- Create: `templates/management/groups/form.html`
- Modify: `config/settings.py`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: `accounts.User` with role `sampler`; `admin_required`.
- Produces: `personnel.models.PersonnelGroup`; management CRUD at `/manage/groups/`.

- [ ] **Step 1: Write failing group membership tests**

```python
# personnel/tests/test_groups.py
from django.core.exceptions import ValidationError
from django.test import TestCase
from accounts.models import User
from personnel.models import PersonnelGroup


class PersonnelGroupTests(TestCase):
    def test_group_accepts_sampler(self):
        owner = User.objects.create_user("owner", role=User.Role.ADMIN)
        sampler = User.objects.create_user("s1", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="第一组", created_by=owner)
        group.members.add(sampler)
        self.assertEqual(list(group.members.all()), [sampler])

    def test_group_rejects_admin(self):
        owner = User.objects.create_user("owner", role=User.Role.ADMIN)
        admin = User.objects.create_user("a1", role=User.Role.ADMIN)
        group = PersonnelGroup(name="第一组", created_by=owner)
        group.full_clean()
        group.save()
        with self.assertRaises(ValidationError):
            group.members.add(admin)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python manage.py test personnel.tests.test_groups -v 2`

Expected: FAIL because `PersonnelGroup` does not exist.

- [ ] **Step 3: Implement the group model and explicit member validation**

```python
# personnel/models.py
from django.db import models
from accounts.models import User


class PersonnelGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, blank=True, related_name="personnel_groups")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_personnel_groups")
    created_at = models.DateTimeField(auto_now_add=True)

```

Add an `m2m_changed` `pre_add` receiver in `personnel/signals.py` that queries every `pk_set` user and raises `ValidationError("人员分组只能包含抽样人员")` if any role is not `sampler`. Import signals from `PersonnelConfig.ready()`. Management views always set `created_by=request.user`; edit views never change the original creator.

- [ ] **Step 4: Implement admin-only list, create, and edit views**

`PersonnelGroupForm` exposes `name`, `description`, and a filtered `members` queryset containing every user with role `sampler`, including inactive users, matching the approved rule.

- [ ] **Step 5: Generate migrations and run tests**

Run: `python manage.py makemigrations personnel`

Run: `python manage.py test personnel -v 2`

Expected: PASS.

- [ ] **Step 6: Commit personnel groups**

```bash
git add personnel templates/management/groups config
git commit -m "feat: add sampler personnel groups"
```

---

### Task 4: Sampling Domain Models and State Constraints

**Files:**
- Create: `sampling/apps.py`
- Create: `sampling/models.py`
- Create: `sampling/migrations/0001_initial.py`
- Create: `sampling/tests/factories.py`
- Create: `sampling/tests/test_models.py`
- Modify: `config/settings.py`

**Interfaces:**
- Consumes: `accounts.User`; `personnel.PersonnelGroup`.
- Produces: `SamplingTask`, `CandidateMaterial`, `PersonnelAssignment`, `SamplingBatch`, `SamplingResult`; task and batch status enums; `SamplingFixturesMixin.make_assigned_task()` for later tests.

- [ ] **Step 1: Write failing model constraint tests**

```python
# sampling/tests/test_models.py
from django.db import IntegrityError, transaction
from django.test import TestCase
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask


class SamplingModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.task = SamplingTask.objects.create(
            task_number="T-001", name="入库抽样", personnel_group=self.group,
            draw_count=1, created_by=self.admin,
        )

    def test_material_number_is_unique_inside_task(self):
        values = dict(task=self.task, material_number="M-001", order_number="O-1", supplier="供应商", material_name="物资", quantity=10)
        CandidateMaterial.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CandidateMaterial.objects.create(**values)

    def test_task_cannot_be_ready_when_draw_count_exceeds_pool(self):
        with self.assertRaisesMessage(ValueError, "抽取数量不能超过候选物资数量"):
            self.task.mark_ready()
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python manage.py test sampling.tests.test_models -v 2`

Expected: FAIL because sampling models are absent.

- [ ] **Step 3: Implement task and candidate models**

Define `SamplingTask.Status` as `draft`, `ready`, `assigned`, `in_progress`, `completed`, and `cancelled`. Add `task_number`, `name`, `personnel_group`, `planned_at`, `draw_count`, `status`, `notes`, `created_by`, `created_at`, and `updated_at`. Implement `mark_ready()` to require `draw_count > 0`, at least one candidate, and `draw_count <= candidates.count()`.

Define `CandidateMaterial` fields from the spec and add `UniqueConstraint(fields=["task", "material_number"], name="unique_material_number_per_task")` plus a positive `quantity` check constraint.

- [ ] **Step 4: Implement assignment, batch, and result models**

`PersonnelAssignment` stores `candidate_user_ids` as JSON, `selected_user`, `kind` (`initial`/`reassign`), `reason`, `is_current`, `created_by`, `created_at`, and `viewed_at`.

`SamplingBatch` stores `version`, `kind` (`initial`/`redraw`), `status` (`authorized`/`locked`), `reason`, `approved_by`, `approved_at`, `drawn_by`, `drawn_at`, and unique `(task, version)`.

`SamplingResult` stores `batch`, `material`, and `sequence`, with unique `(batch, material)` and `(batch, sequence)` constraints.

Create the shared fixture only after these models exist:

```python
# sampling/tests/factories.py
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, PersonnelAssignment, SamplingTask


class SamplingFixturesMixin:
    def make_assigned_task(self, draw_count=1, pool_size=3):
        admin = User.objects.create_user("fixture_admin", role=User.Role.ADMIN)
        sampler = User.objects.create_user("fixture_sampler", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="fixture_group", created_by=admin)
        group.members.add(sampler)
        task = SamplingTask.objects.create(
            task_number="FIXTURE-1", name="测试任务", personnel_group=group,
            draw_count=draw_count, status=SamplingTask.Status.ASSIGNED, created_by=admin,
        )
        materials = [
            CandidateMaterial.objects.create(
                task=task, material_number=f"M-{index:03d}", order_number="O-1",
                supplier="供应商", material_name="物资", quantity=10,
            )
            for index in range(1, pool_size + 1)
        ]
        PersonnelAssignment.objects.create(
            task=task, candidate_user_ids=[sampler.id], selected_user=sampler,
            kind=PersonnelAssignment.Kind.INITIAL, is_current=True, created_by=admin,
        )
        return task, sampler, materials
```

- [ ] **Step 5: Generate migrations and run model tests**

Run: `python manage.py makemigrations sampling`

Run: `python manage.py test sampling.tests.test_models -v 2`

Expected: PASS.

- [ ] **Step 6: Commit domain models**

```bash
git add sampling config/settings.py
git commit -m "feat: add sampling domain models"
```

---

### Task 5: Task-Only Audit Service

**Files:**
- Create: `audit/apps.py`
- Create: `audit/models.py`
- Create: `audit/services.py`
- Create: `audit/migrations/0001_initial.py`
- Create: `audit/tests/test_audit.py`
- Modify: `config/settings.py`

**Interfaces:**
- Consumes: `sampling.SamplingTask`; authenticated actor; optional request IP.
- Produces: `TaskAuditLog`; `log_task_event(*, task, actor, event_type, before=None, after=None, ip_address=None) -> TaskAuditLog`.

- [ ] **Step 1: Write the failing explicit-audit test**

```python
# audit/tests/test_audit.py
from django.test import TestCase
from accounts.models import User
from audit.models import TaskAuditLog
from audit.services import log_task_event
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask


class AuditTests(TestCase):
    def test_only_explicit_task_event_creates_log(self):
        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="第一组", created_by=admin)
        task = SamplingTask.objects.create(task_number="T-1", name="任务", personnel_group=group, draw_count=1, created_by=admin)
        admin.phone = "13800000000"
        admin.save()
        self.assertEqual(TaskAuditLog.objects.count(), 0)
        log_task_event(task=task, actor=admin, event_type="task.created", after={"status": "draft"})
        self.assertEqual(TaskAuditLog.objects.count(), 1)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python manage.py test audit.tests.test_audit -v 2`

Expected: FAIL because audit models and service are absent.

- [ ] **Step 3: Implement explicit task audit logging**

```python
# audit/services.py
from audit.models import TaskAuditLog


def log_task_event(*, task, actor, event_type, before=None, after=None, ip_address=None):
    return TaskAuditLog.objects.create(
        task=task,
        actor=actor,
        event_type=event_type,
        before_data=before or {},
        after_data=after or {},
        ip_address=ip_address,
    )
```

Do not register login, logout, user-save, or profile-save signals. Audit writes occur only inside sampling services and task management views.

- [ ] **Step 4: Generate migrations and run audit tests**

Run: `python manage.py makemigrations audit`

Run: `python manage.py test audit -v 2`

Expected: PASS.

- [ ] **Step 5: Commit audit infrastructure**

```bash
git add audit config/settings.py
git commit -m "feat: add task-only audit log"
```

---

### Task 6: Task Lifecycle, Candidate CRUD, and Atomic CSV Import

**Files:**
- Create: `sampling/forms.py`
- Create: `sampling/services/lifecycle.py`
- Create: `sampling/services/imports.py`
- Create: `sampling/tests/test_lifecycle.py`
- Create: `sampling/tests/test_imports.py`
- Create: `samples/materials.csv`

**Interfaces:**
- Consumes: sampling models; `log_task_event`.
- Produces: `TaskFrozenError`; `CandidateImportError`; `create_task(...) -> SamplingTask`; `update_task(...) -> SamplingTask`; `mark_task_ready(*, task_id, actor) -> SamplingTask`; `cancel_task(*, task_id, actor) -> SamplingTask`; `import_candidates(*, task_id, actor, csv_file) -> int`.

- [ ] **Step 1: Write failing freeze and import rollback tests**

```python
# sampling/tests/test_imports.py
from io import BytesIO
from django.test import TestCase
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask
from sampling.services.imports import CandidateImportError, import_candidates


class CandidateImportTests(TestCase):
    def test_invalid_row_rolls_back_entire_csv(self):
        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="第一组", created_by=admin)
        task = SamplingTask.objects.create(task_number="T-1", name="任务", personnel_group=group, draw_count=1, created_by=admin)
        content = "物资编号,订单号,供应商,物资名称,物资数量\nM-1,O-1,S,N,10\nM-1,O-2,S,N,0\n".encode("utf-8-sig")
        with self.assertRaises(CandidateImportError) as error:
            import_candidates(task_id=task.id, actor=admin, csv_file=BytesIO(content))
        self.assertIn("第3行", str(error.exception))
        self.assertEqual(CandidateMaterial.objects.count(), 0)
```

Add `test_executed_task_rejects_candidate_edit`, asserting the lifecycle service raises `TaskFrozenError` after task status becomes `assigned`.

- [ ] **Step 2: Run lifecycle/import tests and verify failure**

Run: `python manage.py test sampling.tests.test_lifecycle sampling.tests.test_imports -v 2`

Expected: FAIL because service modules do not exist.

- [ ] **Step 3: Implement CSV parsing and all-row validation**

Decode UTF-8 with optional BOM, use `csv.DictReader`, require the five exact Chinese headers, normalize surrounding whitespace, validate positive integer quantity, detect duplicates both inside the file and against the task, and collect row-specific errors before writing. Raise `CandidateImportError("；".join(errors))` when any error exists.

```python
class CandidateImportError(ValueError):
    pass


class TaskFrozenError(ValueError):
    pass
```

- [ ] **Step 4: Write candidates and audit in one transaction**

Wrap the locked task read, `bulk_create`, and `materials.imported` audit row in `transaction.atomic()`. Return the imported row count. Reject every write when `task.status` is not `draft` or `ready`.

- [ ] **Step 5: Implement task lifecycle services and forms**

`SamplingTaskForm` exposes task number, name, group, planned time, draw count, and notes. `CandidateMaterialForm` exposes the five material fields. Lifecycle services call `full_clean()`, enforce the freeze rule, and write `task.created`, `task.updated`, `task.ready`, `task.cancelled`, `material.created`, `material.updated`, and `material.deleted` events with concrete before/after dictionaries.

- [ ] **Step 6: Run tests**

Run: `python manage.py test sampling.tests.test_lifecycle sampling.tests.test_imports -v 2`

Expected: PASS, including complete rollback for invalid CSV.

- [ ] **Step 7: Commit lifecycle and import behavior**

```bash
git add sampling/forms.py sampling/services sampling/tests samples/materials.csv
git commit -m "feat: add task lifecycle and candidate import"
```

---

### Task 7: Atomic Random Personnel Assignment and Reassignment

**Files:**
- Create: `sampling/services/assignment.py`
- Create: `sampling/tests/test_assignment.py`
- Create: `sampling/tests/test_assignment_concurrency.py`

**Interfaces:**
- Consumes: ready task, group membership, actor, optional reassignment reason.
- Produces: `assign_sampler(*, task_id: int, actor: User) -> PersonnelAssignment`; `reassign_sampler(*, task_id: int, actor: User, reason: str) -> PersonnelAssignment`.

- [ ] **Step 1: Write failing assignment behavior tests**

```python
# sampling/tests/test_assignment.py
from unittest.mock import patch
from django.test import TestCase
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask
from sampling.services.assignment import assign_sampler


class AssignmentTests(TestCase):
    @patch("sampling.services.assignment.secrets.choice")
    def test_assignment_uses_every_group_member_without_filtering(self, choice):
        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        active = User.objects.create_user("active", role=User.Role.SAMPLER, is_active=True)
        inactive = User.objects.create_user("inactive", role=User.Role.SAMPLER, is_active=False)
        group = PersonnelGroup.objects.create(name="第一组", created_by=admin)
        group.members.add(active, inactive)
        task = SamplingTask.objects.create(task_number="T-1", name="任务", personnel_group=group, draw_count=1, status="ready", created_by=admin)
        choice.return_value = inactive.id
        assignment = assign_sampler(task_id=task.id, actor=admin)
        self.assertEqual(sorted(assignment.candidate_user_ids), sorted([active.id, inactive.id]))
        self.assertEqual(assignment.selected_user, inactive)
```

Add tests for empty groups, non-ready tasks, missing reassignment reason, historical `is_current=False`, and the possibility of selecting the same user during reassignment.

- [ ] **Step 2: Run assignment tests and verify failure**

Run: `python manage.py test sampling.tests.test_assignment -v 2`

Expected: FAIL because assignment services are absent.

- [ ] **Step 3: Implement atomic initial assignment**

```python
# sampling/services/assignment.py
import secrets
from django.db import transaction
from sampling.models import PersonnelAssignment, SamplingTask


@transaction.atomic
def assign_sampler(*, task_id, actor):
    task = SamplingTask.objects.select_for_update().select_related("personnel_group").get(pk=task_id)
    if task.status != SamplingTask.Status.READY:
        raise ValueError("任务当前状态不可执行")
    candidate_ids = list(task.personnel_group.members.order_by("id").values_list("id", flat=True))
    if not candidate_ids:
        raise ValueError("抽样人员分组不能为空")
    selected_id = secrets.choice(candidate_ids)
    assignment = PersonnelAssignment.objects.create(
        task=task, candidate_user_ids=candidate_ids, selected_user_id=selected_id,
        kind=PersonnelAssignment.Kind.INITIAL, is_current=True, created_by=actor,
    )
    task.status = SamplingTask.Status.ASSIGNED
    task.save(update_fields=["status", "updated_at"])
    return assignment
```

Add the task audit write inside the same transaction.

- [ ] **Step 4: Implement reassignment**

Require a nonblank stripped reason, lock the task, mark the previous assignment noncurrent, snapshot the group's current complete membership, select with `secrets.choice`, and create a current reassignment record. Do not exclude the previous user.

- [ ] **Step 5: Add the MySQL concurrency test**

Use `TransactionTestCase` and two threads, each closing old DB connections before calling `assign_sampler`. Assert one call succeeds, the other raises the state error, and exactly one initial assignment exists. Skip only when `connection.vendor != "mysql"` with message `requires MySQL row locking`.

- [ ] **Step 6: Run assignment tests on MySQL**

Run: `python manage.py test sampling.tests.test_assignment sampling.tests.test_assignment_concurrency -v 2`

Expected: PASS; concurrency test executes rather than skips on MySQL.

- [ ] **Step 7: Commit random assignment**

```bash
git add sampling/services/assignment.py sampling/tests/test_assignment.py sampling/tests/test_assignment_concurrency.py
git commit -m "feat: add atomic sampler assignment"
```

---

### Task 8: Atomic Material Draw, Completion, and Redraw Authorization

**Files:**
- Create: `sampling/services/drawing.py`
- Create: `sampling/tests/test_drawing.py`
- Create: `sampling/tests/test_drawing_concurrency.py`
- Modify: `sampling/services/lifecycle.py`

**Interfaces:**
- Consumes: current assignment, assigned sampler, candidate pool, task state.
- Produces: `draw_materials(*, task_id: int, actor: User) -> SamplingBatch`; `authorize_redraw(*, task_id: int, actor: User, reason: str) -> SamplingBatch`; `complete_task(*, task_id: int, actor: User) -> SamplingTask`.

- [ ] **Step 1: Write failing immutable draw tests**

```python
# sampling/tests/test_drawing.py
from unittest.mock import patch
from django.test import TestCase
from sampling.models import SamplingBatch, SamplingResult
from sampling.services.drawing import draw_materials
from sampling.tests.factories import SamplingFixturesMixin


class DrawingTests(SamplingFixturesMixin, TestCase):
    @patch("sampling.services.drawing.secrets.SystemRandom.sample")
    def test_draw_persists_unique_ordered_results(self, sample):
        task, sampler, materials = self.make_assigned_task(draw_count=2, pool_size=3)
        sample.return_value = [materials[2].id, materials[0].id]
        batch = draw_materials(task_id=task.id, actor=sampler)
        self.assertEqual(batch.status, SamplingBatch.Status.LOCKED)
        self.assertEqual(
            list(SamplingResult.objects.filter(batch=batch).order_by("sequence").values_list("material_id", flat=True)),
            [materials[2].id, materials[0].id],
        )
```

Add tests that a different sampler is rejected, a repeat call returns the existing locked initial batch without drawing again, a redraw requires an authorized batch, authorization requires a nonblank reason, and historical batch results remain unchanged.

- [ ] **Step 2: Run draw tests and verify failure**

Run: `python manage.py test sampling.tests.test_drawing -v 2`

Expected: FAIL because drawing services are absent.

- [ ] **Step 3: Implement initial drawing**

Lock the task with `select_for_update()`, verify the current assignment belongs to the actor, return an existing locked initial batch for idempotent repeats, snapshot ordered candidate IDs, call `secrets.SystemRandom().sample(candidate_ids, task.draw_count)`, create the locked batch and ordered results, change task to `in_progress`, and write `draw.initial` audit data in the same transaction.

- [ ] **Step 4: Implement redraw authorization and execution**

`authorize_redraw` locks the task, rejects blank reasons, creates the next-version `SamplingBatch(kind="redraw", status="authorized", reason=..., approved_by=actor, approved_at=timezone.now())`, and sets the task to `assigned`. `draw_materials` fills the earliest authorized unfilled redraw batch for the current assigned sampler, locks it, and writes `draw.redraw` audit data.

- [ ] **Step 5: Implement completion**

`complete_task` locks the task, verifies actor is the current sampler and a locked latest batch exists, changes status from `in_progress` to `completed`, and writes `task.completed` audit data. Repeated completion returns the completed task without creating a second log.

- [ ] **Step 6: Add and run MySQL concurrency tests**

Create a two-thread `TransactionTestCase` like Task 7. Assert concurrent draw requests create one locked initial batch and exactly `draw_count` results.

Run: `python manage.py test sampling.tests.test_drawing sampling.tests.test_drawing_concurrency -v 2`

Expected: PASS on MySQL with one persisted batch.

- [ ] **Step 7: Commit draw and redraw services**

```bash
git add sampling/services/drawing.py sampling/services/lifecycle.py sampling/tests/test_drawing.py sampling/tests/test_drawing_concurrency.py
git commit -m "feat: add immutable material drawing"
```

---

### Task 9: Desktop Management Views

**Files:**
- Create: `sampling/management_views.py`
- Create: `sampling/management_urls.py`
- Create: `audit/views.py`
- Create: `audit/urls.py`
- Create: `accounts/admin_urls.py`
- Create: `accounts/tests/test_user_management.py`
- Create: `sampling/tests/test_management_views.py`
- Create: `audit/tests/test_log_views.py`
- Create: `templates/management/base.html`
- Create: `templates/management/dashboard.html`
- Create: `templates/management/tasks/list.html`
- Create: `templates/management/tasks/form.html`
- Create: `templates/management/tasks/detail.html`
- Create: `templates/management/tasks/import.html`
- Create: `templates/management/users/list.html`
- Create: `templates/management/users/form.html`
- Create: `templates/management/logs/list.html`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: all domain forms and services; `admin_required`.
- Produces: complete `/manage/` dashboard, task CRUD/actions, users, groups, and task-log filters.

- [ ] **Step 1: Write failing management permission and action tests**

```python
# sampling/tests/test_management_views.py
from django.test import TestCase
from django.urls import reverse
from accounts.models import User


class ManagementViewTests(TestCase):
    def test_sampler_cannot_execute_task_endpoint(self):
        sampler = User.objects.create_user("sampler", role=User.Role.SAMPLER)
        self.client.force_login(sampler)
        response = self.client.post(reverse("management:task-execute", args=[1]))
        self.assertEqual(response.status_code, 403)

    def test_execute_endpoint_rejects_get(self):
        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("management:task-execute", args=[1]))
        self.assertEqual(response.status_code, 405)
```

Add happy-path tests for creating a task, importing CSV, marking ready, execution, reassignment with required reason, redraw authorization, cancellation, user creation, password reset, and log filtering.

- [ ] **Step 2: Run management tests and verify failure**

Run: `python manage.py test sampling.tests.test_management_views accounts.tests.test_user_management audit.tests.test_log_views -v 2`

Expected: FAIL because management routes and templates are absent.

- [ ] **Step 3: Implement management URL namespaces and POST-only actions**

Use `@require_POST` plus `@admin_required` on execute, reassign, authorize-redraw, cancel, material-delete, and user-state mutations. Views call services and translate domain errors into Django messages without duplicating domain rules.

- [ ] **Step 4: Implement desktop templates**

Create a sidebar shell with dashboard, tasks, groups, users, and task logs. Task detail shows candidate rows, assignment history, batch versions, results, and task audit timeline. Hide invalid actions based on state while preserving server-side checks.

- [ ] **Step 5: Implement filtered task log view**

Support exact task-number, event-type, actor, start-date, and end-date GET filters. Query only `TaskAuditLog`; do not synthesize authentication history.

- [ ] **Step 6: Run management tests**

Run: `python manage.py test sampling.tests.test_management_views accounts.tests.test_user_management audit.tests.test_log_views -v 2`

Expected: PASS.

- [ ] **Step 7: Commit management workflows**

```bash
git add sampling/management_views.py sampling/management_urls.py accounts/admin_urls.py audit/views.py audit/urls.py templates/management config/urls.py accounts/tests sampling/tests/test_management_views.py audit/tests/test_log_views.py
git commit -m "feat: add desktop management workflows"
```

---

### Task 10: Mobile H5 Workflow and Display-Only Sampling Animation

**Files:**
- Create: `sampling/mobile_views.py`
- Create: `sampling/mobile_urls.py`
- Create: `sampling/tests/test_mobile_views.py`
- Create: `templates/mobile/base.html`
- Create: `templates/mobile/dashboard.html`
- Create: `templates/mobile/reminders.html`
- Create: `templates/mobile/task_detail.html`
- Create: `templates/mobile/draw_result.html`
- Create: `templates/mobile/profile.html`
- Create: `static/js/sampling-animation.js`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: `sampler_required`; current assignment; `draw_materials`; `complete_task`.
- Produces: `/m/`, `/m/tasks/`, `/m/tasks/<id>/`, POST draw, POST complete, and profile flows.

- [ ] **Step 1: Write failing mobile ownership and idempotency tests**

```python
# sampling/tests/test_mobile_views.py
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from sampling.tests.factories import SamplingFixturesMixin


class MobileTaskTests(SamplingFixturesMixin, TestCase):
    def test_sampler_cannot_view_another_samplers_task(self):
        task, assigned_sampler, _ = self.make_assigned_task()
        other_sampler = User.objects.create_user("other_sampler", role=User.Role.SAMPLER)
        self.client.force_login(other_sampler)
        response = self.client.get(reverse("mobile:task-detail", args=[task.id]))
        self.assertEqual(response.status_code, 404)

    def test_draw_response_uses_server_persisted_results(self):
        task, sampler, _ = self.make_assigned_task()
        self.client.force_login(sampler)
        response = self.client.post(reverse("mobile:task-draw", args=[task.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["batch_status"], "locked")
        self.assertEqual(len(response.json()["results"]), task.draw_count)
```

Add tests for unread `viewed_at`, status filtering, administrator 403, profile field restrictions, refresh after draw, and completion.

- [ ] **Step 2: Run mobile tests and verify failure**

Run: `python manage.py test sampling.tests.test_mobile_views -v 2`

Expected: FAIL because mobile routes are absent.

- [ ] **Step 3: Implement mobile views and task ownership queries**

Every task queryset must filter through `assignments__selected_user=request.user` and `assignments__is_current=True`. Opening detail sets the current assignment's `viewed_at` once. POST draw returns JSON containing only persisted batch/results; POST complete calls the lifecycle service.

- [ ] **Step 4: Implement display-only animation**

```javascript
// static/js/sampling-animation.js
export async function runSamplingAnimation({ trigger, reel, resultList, endpoint, csrfToken }) {
  trigger.disabled = true;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken, "Accept": "application/json" },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "抽样失败");
  const labels = payload.results.map((item) => item.material_number);
  let tick = 0;
  const timer = window.setInterval(() => {
    reel.textContent = labels[tick % labels.length];
    tick += 1;
  }, 70);
  await new Promise((resolve) => window.setTimeout(resolve, 1400));
  window.clearInterval(timer);
  resultList.replaceChildren(...payload.results.map(renderResultCard));
}
```

Define `renderResultCard(item)` in the same file using `textContent`, never `innerHTML`, and display material number, order number, supplier, material name, and quantity. The animation must never call a browser random function to determine results.

- [ ] **Step 5: Run mobile tests**

Run: `python manage.py test sampling.tests.test_mobile_views -v 2`

Expected: PASS.

- [ ] **Step 6: Commit mobile workflows**

```bash
git add sampling/mobile_views.py sampling/mobile_urls.py sampling/tests/test_mobile_views.py templates/mobile static/js/sampling-animation.js config/urls.py
git commit -m "feat: add mobile sampling workflow"
```

---

### Task 11: Shared Visual System and Responsive Verification

**Files:**
- Create: `static/css/tokens.css`
- Create: `static/css/management.css`
- Create: `static/css/mobile.css`
- Create: `sampling/tests/test_template_contracts.py`
- Modify: `templates/management/base.html`
- Modify: `templates/mobile/base.html`
- Modify: all templates created in Tasks 2, 3, 9, and 10

**Interfaces:**
- Consumes: retained `artifact-template-ui` PNG; semantic HTML from prior tasks.
- Produces: CSS variables and responsive classes shared by all product pages.

- [ ] **Step 1: Inspect the retained visual reference**

Open `C:/Users/Eternal/.codex/skills/artifact-template-ui/assets/reference.png` with the image-viewing tool. Record the visible palette and hierarchy directly in CSS tokens; do not invent a second visual direction.

- [ ] **Step 2: Write failing template-contract tests**

```python
# sampling/tests/test_template_contracts.py
from pathlib import Path
from django.test import SimpleTestCase


class TemplateContractTests(SimpleTestCase):
    def test_mobile_shell_has_three_required_tabs(self):
        html = Path("templates/mobile/base.html").read_text(encoding="utf-8")
        self.assertIn("随机抽样", html)
        self.assertIn("任务提醒", html)
        self.assertIn("个人中心", html)

    def test_shared_tokens_include_primary_gradient(self):
        css = Path("static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn("--color-primary", css)
        self.assertIn("--gradient-primary", css)
```

- [ ] **Step 3: Run template tests and verify failure**

Run: `python manage.py test sampling.tests.test_template_contracts -v 2`

Expected: FAIL until the shared tokens and required navigation are present.

- [ ] **Step 4: Implement shared design tokens**

Define exact variables for primary blue, deep navy text, muted text, green/orange/purple accents, page background, card background, border, shadow, 12/16/24 px radii, spacing scale, and the blue primary gradient. Use system Chinese font stacks and a minimum 44 px mobile interactive height.

- [ ] **Step 5: Implement responsive mobile and desktop layouts**

Mobile: fixed three-tab bottom navigation, safe-area padding, single-column cards, status chips, summary grid, full-width primary action, and responsive draw result cards.

Desktop: fixed/collapsible sidebar, top user bar, summary cards, filter rows, responsive tables, form sections, modal/action layouts, and the same tokens without copying mobile-only rules.

- [ ] **Step 6: Run template and view tests**

Run: `python manage.py test sampling.tests.test_template_contracts sampling.tests.test_mobile_views sampling.tests.test_management_views -v 2`

Expected: PASS.

- [ ] **Step 7: Start the server and visually verify both breakpoints**

Run: `python manage.py runserver 127.0.0.1:8000`

Verify with browser screenshots at 390×844 for `/m/` and 1440×900 for `/manage/`. Confirm no horizontal overflow, no clipped fixed navigation, readable Chinese text, visible focus states, and faithful blue-white card styling. Save any verification screenshots under `docs/verification/` only if they help explain a discovered/fixed layout issue.

- [ ] **Step 8: Commit the visual system**

```bash
git add static/css templates sampling/tests/test_template_contracts.py
git commit -m "feat: apply responsive sampling design system"
```

---

### Task 12: Demo Data, Windows Startup, Documentation, and Full Verification

**Files:**
- Create: `sampling/management/commands/seed_demo.py`
- Create: `sampling/tests/test_seed_demo.py`
- Create: `scripts/start.ps1`
- Create: `README.md`
- Modify: `.gitignore`
- Modify: `samples/materials.csv`

**Interfaces:**
- Consumes: all models, migrations, and routes.
- Produces: idempotent `python manage.py seed_demo`; Windows start workflow; documented administrator and sampler demo journey.

- [ ] **Step 1: Write the failing idempotent seed test**

```python
# sampling/tests/test_seed_demo.py
from django.core.management import call_command
from django.test import TestCase
from accounts.models import User
from personnel.models import PersonnelGroup


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        call_command("seed_demo")
        self.assertEqual(User.objects.filter(username="demo_admin").count(), 1)
        self.assertEqual(User.objects.filter(username="demo_sampler_01").count(), 1)
        self.assertEqual(PersonnelGroup.objects.filter(name="演示抽样组").count(), 1)
```

- [ ] **Step 2: Run seed test and verify failure**

Run: `python manage.py test sampling.tests.test_seed_demo -v 2`

Expected: FAIL because `seed_demo` is absent.

- [ ] **Step 3: Implement deterministic demo setup**

Use `update_or_create` for one administrator, three samplers, one group, one draft task, and at least ten uniquely numbered materials. Set documented local-only passwords with `set_password`; print the usernames and a warning to change passwords outside the demo.

- [ ] **Step 4: Implement the Windows start script**

`scripts/start.ps1` must stop with a clear message if `.env` is missing, run `python manage.py migrate`, optionally run `python manage.py seed_demo` when invoked with `-SeedDemo`, then run `python manage.py runserver 0.0.0.0:8000`. It must not create or overwrite `.env`.

- [ ] **Step 5: Write the README walkthrough**

Document Python/MySQL prerequisites, optional `docker compose up -d db`, virtual environment creation, dependency installation, copying `.env.example` to `.env`, migrations, demo seeding, startup, management URL, mobile URL, CSV encoding/headers, the full create→import→ready→execute→draw→complete flow, reassignment, redraw, and test commands.

- [ ] **Step 6: Run focused seed and configuration tests**

Run: `python manage.py test sampling.tests.test_seed_demo accounts.tests.test_smoke -v 2`

Expected: PASS.

- [ ] **Step 7: Run the complete test suite on MySQL**

Run: `python manage.py test -v 2`

Expected: PASS with zero failures and zero errors; MySQL concurrency tests must not be skipped.

- [ ] **Step 8: Run Django deployment checks**

Run: `python manage.py check`

Expected: `System check identified no issues`.

Run: `python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`.

- [ ] **Step 9: Exercise the documented demo flow**

Run: `python manage.py migrate`

Run: `python manage.py seed_demo`

Start the server and manually complete one end-to-end task through both role-specific interfaces. Confirm the task audit list contains task events only and that refreshing the result page does not change locked results.

- [ ] **Step 10: Commit operations and documentation**

```bash
git add sampling/management sampling/tests/test_seed_demo.py scripts README.md .gitignore samples/materials.csv
git commit -m "docs: add local demo setup and verification"
```

- [ ] **Step 11: Verify the final repository state**

Run: `git status --short`

Expected: no output.

Run: `git log --oneline -12`

Expected: the implementation history contains focused commits for foundation, authentication, groups, models, audit, lifecycle/import, assignment, drawing, management UI, mobile UI, visual system, and demo documentation.

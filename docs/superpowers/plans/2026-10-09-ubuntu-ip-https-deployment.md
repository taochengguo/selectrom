# Ubuntu IP HTTPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Add a reproducible Ubuntu 24.04 deployment path for `https://113.250.177.180/` with a self-signed IP certificate.

**Architecture:** Nginx terminates HTTPS and serves collected static and uploaded media. A systemd-managed Gunicorn process listens only on localhost and talks to a local MySQL instance. Production settings are enabled explicitly via environment variables, preserving Windows development behavior.

**Tech Stack:** Django 5.2, Gunicorn, MySQL, Nginx, systemd, OpenSSL.

**Spec:** `docs/superpowers/specs/2026-10-09-ubuntu-ip-https-deployment.md`

## Global Constraints

- Public origin is `https://113.250.177.180`; no domain or trusted certificate is required in this phase.
- Never expose MySQL port 3306 or Gunicorn port 8000 to the public network.
- Production secrets and generated certificate keys remain outside Git.
- Preserve the existing Windows LAN startup path.
- Actual phone geolocation and check-in remain unverified until tested on a phone.

## Review Focus

- Rejected proxy headers: a request that arrives without the trusted Nginx path must not be able to spoof HTTPS.
- Media URL: avatar links under HTTPS must resolve to `/media/...`, not a route-relative URL.
- Static URL: `collectstatic` must collect into a directory that Nginx can serve without exposing source or private files.
- Service restart: migration or package-install failure must leave the previous running release recoverable.
- Certificate identity: the generated self-signed certificate must include the public IP in its SAN.

---

### Task 1: Production settings

**Files:** Modify `config/settings.py`; create `config/tests/test_deployment_settings.py`; modify `requirements.txt`.

**Interfaces:** Environment variables `DJANGO_TRUST_PROXY_HTTPS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_SECURE_COOKIES`; Django settings `STATIC_ROOT`, `MEDIA_URL`, `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

- [ ] Write focused tests for default development settings, production proxy settings, `/media/` URLs, and a `collectstatic` destination.
- [ ] Run those tests and confirm the new assertions fail.
- [ ] Add only the settings needed by the spec and a constrained Gunicorn dependency.
- [ ] Run focused tests, `manage.py check --deploy` using production environment values, and `manage.py makemigrations --check --dry-run`.
- [ ] Commit the production-settings change.

### Task 2: Linux service and web server templates

**Files:** Create `deploy/ubuntu/selectrom.service`, `deploy/ubuntu/selectrom.nginx.conf`, `deploy/ubuntu/generate-ip-certificate.sh`; create `deploy/ubuntu/test-config.py`.

**Interfaces:** Repository path `/opt/selectrom/current`; service user `selectrom`; Gunicorn bind `127.0.0.1:8000`; certificate paths `/etc/selectrom/tls/ip.crt` and `/etc/selectrom/tls/ip.key`; static path `/opt/selectrom/current/staticfiles/`; media path `/opt/selectrom/shared/media/`.

- [ ] Write template checks for the localhost-only bind, forwarded Host/protocol, expected static/media aliases, private paths, and IP SAN.
- [ ] Run checks and confirm they fail before templates exist.
- [ ] Add service, Nginx and OpenSSL templates. Keep upload execution disabled in Nginx and preserve the original Host header.
- [ ] Run template checks and, when Nginx is available, `nginx -t` against a rendered test configuration.
- [ ] Commit the Linux templates.

### Task 3: Deployment runbook and verification

**Files:** Create `docs/deploy-ubuntu-ip-https.md`; modify `README.md` to link it.

**Interfaces:** Commands for Ubuntu 24.04 package install, local MySQL initialization, Git checkout, secret generation, migration, static collection, TLS generation, systemd setup, Nginx activation, backup, restore, update, and rollback.

- [ ] Write the runbook with exact command order and mark placeholders requiring operator values.
- [ ] Verify every path and environment variable against Tasks 1 and 2 and the project code.
- [ ] Run focused tests, the full Django test suite, `manage.py check`, migration dry-run, and `git diff --check`; report any environment-only failures separately.
- [ ] Commit the documentation and verify the worktree status.

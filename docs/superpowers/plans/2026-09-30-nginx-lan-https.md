# 本机局域网 Nginx HTTPS 反向代理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Selectrom 通过 Windows 本机 Nginx HTTPS 入口服务于电脑和同一局域网手机。

**Architecture:** 保留 `scripts/start.ps1` 启动的 Django HTTPS 服务作为本机上游 `127.0.0.1:8000`，由 Nginx 在局域网地址监听 HTTPS `443`。用 PowerShell 生成包含当前仓库绝对路径的 Nginx 配置，复用 mkcert 证书，并在部署文档中说明安装 Nginx、启动、验证、重载及手机信任步骤。

**Tech Stack:** Windows PowerShell, Nginx for Windows, Django, mkcert.

**Spec:** `docs/superpowers/specs/2026-09-30-nginx-lan-https.md`

## Global Constraints

- 该部署仅用于本机及受控局域网；不配置公网 DNS、云端 TLS 或公网生产部署。
- 项目现有 HTTPS Django 上游为 `127.0.0.1:8000`。
- Nginx 使用 `.certs/lan.pem` 和 `.certs/lan-key.pem`，并把 `.certs/mobile-rootCA.pem` 作为手机信任证书。
- 不自动添加 Windows 防火墙入站规则。
- 不改为 Gunicorn/Uvicorn，不新增 Python 依赖。

## Review Focus

- 项目目录包含空格或反斜杠时，生成的 Nginx 路径仍可解析：由 `nginx -t` 覆盖。
- Nginx 可执行文件缺失时，启动脚本给出放置路径和下载说明：由脚本缺文件路径检查覆盖。
- mkcert 证书尚未生成时，启动脚本指出先启动 Django 脚本：由证书缺失路径检查覆盖。
- 443 端口被占用时，验证说明能区分端口冲突与上游错误：由端口监听检查覆盖。
- LAN IPv4 改变后重启仍使用新签发证书：由重启 Django、重建配置及 `nginx -t` 的操作检查覆盖。

---

### Task 1: 生成并管理本机 Nginx 配置

**Files:**
- Create: `scripts/nginx-local.ps1`
- Create: `scripts/Test-NginxLocal.Tests.ps1`
- Runtime generated (ignored): `.tools/nginx/conf/selectrom.conf`
- Test: `Import-Module Pester -RequiredVersion 3.4.0; Invoke-Pester -Script .\scripts\Test-NginxLocal.Tests.ps1`; `nginx.exe -t`; exercise Start, Reload, and Stop.

**Interfaces:**
- Consumes: Existing `.certs/lan.pem`, `.certs/lan-key.pem`, and Django HTTPS upstream on `127.0.0.1:8000`.
- Produces: `powershell -ExecutionPolicy Bypass -File .\scripts\nginx-local.ps1 -Action Start|Test|Reload|Stop`.

- [x] **Step 1: Write PowerShell checks for missing Nginx binary, missing certificate, and generated config paths.** Assert failures identify the exact prerequisite; assert generated paths use forward slashes and point to the current repository.
- [x] **Step 2: Run the script checks to confirm they fail before implementation.** Use the project virtual environment's PowerShell test runner if available; otherwise use the script's `-Action Test` prerequisite output as the manual failing case.
- [x] **Step 3: Implement `scripts/nginx-local.ps1` with an `-Action` parameter.** Resolve Nginx from `.tools/nginx/nginx.exe`; generate an Nginx config under `.tools/nginx/conf/` using the current project path, HTTPS listen port 443, current project certificate/key, and HTTPS upstream `127.0.0.1:8000`. Forward Host, client IP, and `X-Forwarded-Proto`; disable upstream certificate verification only for this loopback mkcert connection. Implement `Test`, `Start`, `Reload`, and `Stop`, validating prerequisites before process control.
- [x] **Step 4: Run `nginx.exe -t` through the script and exercise start, reload, and stop against the generated configuration.** Expected: config test succeeds; Start creates a listener on 443; Reload exits successfully; Stop removes the listener.

### Task 2: Document LAN access and recovery

**Files:**
- Modify: `docs/deploy-on-another-computer.md`
- Test: Follow the documented local Nginx flow and check the published URLs and commands against the script interface.

**Interfaces:**
- Consumes: `scripts/nginx-local.ps1 -Action Start|Test|Reload|Stop` from Task 1.
- Produces: A Windows LAN HTTPS section with setup and recovery steps.

- [x] **Step 1: Add instructions to place the official Windows Nginx distribution at `.tools/nginx/`, start Django first, then run the Nginx `Test` and `Start` actions.** Document HTTPS URLs on port 443 and the mobile root CA trust steps.
- [x] **Step 2: Add concise troubleshooting for occupied port 443, missing/reissued certificates, stopped Django upstream, manual Windows Firewall TCP 443 access, Nginx reload/stop, and LAN IPv4 changes.**
- [x] **Step 3: Review every command in the new section against the actual PowerShell script and confirm existing HTTPS startup guidance remains accurate.**

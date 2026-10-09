# Ubuntu 公网 IP HTTPS 部署设计

## 目标与边界

将 `feature/random-sampling-system` 部署到用户的天翼云 Ubuntu Server 24.04 主机（2 核、2 GB 内存）。管理员和手机端均通过 `https://113.250.177.180/` 访问。现阶段不使用域名和 ICP 域名备案；HTTPS 使用绑定该公网 IP 的自签名证书，测试人员在浏览器证书警告页手动继续访问。不把证书例外视为手机定位可用的证明，必须在实际手机浏览器验证 `window.isSecureContext`、定位授权和打卡流程。

本设计提供仓库内的 Linux 部署文件与操作手册；不包含登录、修改云服务器或迁移实际业务数据。云主机的 SSH 凭据、现有数据范围和操作者账号均需在执行部署时由操作者掌握。

## 运行结构

- Nginx 监听 80 和 443。80 仅重定向到 HTTPS；443 使用 IP 自签名证书。Nginx 直接提供收集后的 `/static/` 与上传文件 `/media/`，其余请求反向代理到 `127.0.0.1:8000`。
- Gunicorn 通过 systemd 以独立低权限用户运行 `config.wsgi:application`，仅监听 `127.0.0.1:8000`。2 GB 主机先用少量 worker，不运行 Django `runserver` 或 Windows `start.ps1`。
- MySQL 仅监听本机。数据库、`media/` 和 `SamplingPhotos/` 都是运行数据，需要持久化和备份；仓库的演示 Compose 密码与公网端口映射不能用于此环境。
- 天地图默认使用 Linux 的常规网络出口，`TIANDITU_DIRECT_EGRESS=false`。Windows 实体网卡直连模式不用于 Ubuntu。

## Django 配置

- 生产 `.env` 设置 `DJANGO_DEBUG=false`、独立随机 `DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS=113.250.177.180`、独立 MySQL 用户与密码，以及实际天地图 Key；不提交 `.env`。
- 增加 `STATIC_ROOT` 供 `collectstatic` 使用，将 `MEDIA_URL` 规范为 `/media/`。上传文件须由 Nginx 当作静态数据返回，不执行其中内容。
- 仅当部署启用 Nginx 且 Gunicorn 不暴露公网时，信任来自本机代理的 `X-Forwarded-Proto: https`；按 IP 的 HTTPS origin 配置 CSRF 可信源。会话及 CSRF Cookie 在 HTTPS 部署时启用 Secure 属性。
- 保留现有 Windows 局域网启动路径和开发模式；生产配置通过环境变量显式启用，避免改变现有本机演示行为。

## 仓库交付物

1. Linux 用的 Gunicorn 依赖、systemd 服务模板与 Nginx 配置模板，路径和用户可由部署文档替换。
2. 生产设置及针对代理 HTTPS、静态资源和媒体 URL 的必要验证。
3. Ubuntu 24.04 操作手册：安装依赖、准备数据库、检出功能分支、生成带 IP SAN 的自签名证书、填写私有环境变量、迁移、收集静态文件、启动服务、检查日志及更新回滚。
4. 手册明确天翼云安全组仅开放必要的 SSH/80/443，MySQL 与 Gunicorn 不直接对公网开放；包含数据库及上传文件备份步骤。

## 验收与已知限制

- `manage.py check --deploy`、迁移检查、相关测试和 Nginx 配置语法检查应通过；从服务器本机及外部设备验证 HTTPS 登录、管理端、手机端、静态资源和上传文件。
- 实际手机需记录 `window.isSecureContext` 与定位授权结果，并完成一次真实打卡。浏览器可能拒绝绕过自签名证书，或即使打开页面也拒绝定位；这种情况须改为可信 IP 证书或在测试设备安装受信任的证书，不能把打卡记为通过。
- 自签名证书只有加密，没有公开身份验证，测试人员须核对 IP 和证书指纹；该临时方式不作为正式处理真实账号及业务数据的安全验收结论。

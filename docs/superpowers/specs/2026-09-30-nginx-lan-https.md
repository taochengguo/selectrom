# 本机局域网 Nginx HTTPS 反向代理规格

## 目标

使 Selectrom 可通过本机 Nginx 的 HTTPS 地址供电脑和同一局域网内手机访问，并保留手机浏览器定位能力。

## 当前约束

- 项目运行于 Windows，现有 `scripts/start.ps1` 启动 Django HTTPS 服务于 `0.0.0.0:8000`。
- 启动脚本使用 mkcert，为 `localhost` 和当前物理网络 IPv4 地址生成 `.certs/lan.pem` 与 `.certs/lan-key.pem`，并导出手机安装用的 `.certs/mobile-rootCA.pem`。
- 该部署仅用于本机及受控局域网；不配置公网 DNS、云端 TLS 或公网生产部署。

## 方案

- 在 Windows 本机运行 Nginx，监听 HTTPS 443，并使用项目启动脚本生成的证书与私钥。
- 将请求反向代理至 Django 的 `https://127.0.0.1:8000`。本机后端由 mkcert 管理；Nginx 到回环地址的上游证书验证按本机代理连接处理。
- 传递原始 Host、客户端地址及 `X-Forwarded-Proto: https`，并让 Django 将代理协议视为 HTTPS，使安全请求、CSRF 与生成的链接保持正确。
- 保留 `/static/` 等请求通过代理到 Django，避免引入额外静态目录收集与映射要求。
- 电脑及手机通过 `https://<本机局域网IPv4>/` 访问；手机继续安装并信任 `.certs/mobile-rootCA.pem`。
- 提供可重复执行的 Nginx 配置及本机启动/验证说明；不自动添加 Windows 防火墙入站规则。

## 验收标准

- Nginx 配置可通过 `nginx -t`。
- 本机 HTTPS 代理能访问登录页、管理页和移动端页面，静态资源正常返回。
- Django 能识别代理后的请求为 HTTPS，Host 校验允许本机 LAN IPv4。
- 文档说明证书重签、Nginx 重载、端口冲突与手机根证书信任步骤。

## 未包含

- 公网部署、域名证书签发、Windows 服务注册、自动配置防火墙、Gunicorn/Uvicorn 替换开发服务器。

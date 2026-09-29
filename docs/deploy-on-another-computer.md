# 在另一台电脑部署随机抽样系统

本文适用于 Windows 电脑上的本机或同一局域网演示。项目使用 Django、MySQL；管理员在电脑端访问 `/manage/`，抽样人员在手机浏览器访问 `/m/`。

## 1. 准备软件并取得代码

安装 Git、Python 3.12、Docker Desktop（只用于运行 MySQL；也可以使用本机 MySQL 8.x）。在 PowerShell 中执行，仓库地址以实际 GitHub 地址替换：

```powershell
git clone <GitHub 仓库地址> selectrom
cd selectrom
git switch feature/random-sampling-system
python --version
```

如果部署的是以后更新的分支，请切换到相应分支，并始终在含有 `manage.py` 的目录执行下列命令。

## 2. 启动 MySQL

使用 Docker Desktop 时，在项目目录执行：

```powershell
docker compose up -d db
docker compose ps
```

仓库中的 `docker-compose.yml` 只启动 MySQL，数据库名、用户和密码对应 `.env.example`。如果电脑上的 3306 端口已被占用，改用本机 MySQL，或者修改 Compose 端口映射及 `.env` 中的 `MYSQL_PORT`。

使用本机 MySQL 时，请先创建 UTF-8 数据库与专用用户，并在下一步把连接信息写入 `.env`。数据库只需供运行 Django 的电脑访问；手机无需连接数据库。

## 3. 安装 Python 依赖并设置环境变量

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：核对 `MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_HOST` 和 `MYSQL_PORT`。为这台电脑设置独立的 `DJANGO_SECRET_KEY`。演示环境可保留 `DJANGO_DEBUG=true`；`.env` 含密码，不能提交到 Git。可用下面的命令生成密钥，再复制输出值到 `.env`：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

`DJANGO_ALLOWED_HOSTS` 保留 `127.0.0.1,localhost` 即可。启动脚本会在每次启动时自动加入当前电脑的局域网 IPv4 地址。

## 4. 初始化与启动

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\scripts\start.ps1
```

`start.ps1` 会再次执行迁移，并监听 `0.0.0.0:8000`。若 PowerShell 阻止执行脚本，可仅对当前进程放开限制后重试：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start.ps1
```

需要全新演示数据时，停止服务后运行 `.\scripts\start.ps1 -SeedDemo`。这会创建演示账号和任务；演示密码见 [README](../README.md)，请勿在实际业务环境使用这些账号和密码。已有业务数据时不要运行 `-SeedDemo`。

启动终端会显示本机和局域网链接。电脑上打开 `http://127.0.0.1:8000/manage/`；手机与电脑接入同一网络，在手机浏览器打开终端显示的 `http://<电脑局域网 IP>:8000/m/`。如手机连接超时，检查 Windows 防火墙是否允许本地子网访问 TCP 8000，以及 Wi-Fi 是否启用了访客网络或设备隔离。无需对手机开放 MySQL 3306 端口。

## 5. 从旧电脑迁移现有数据（可选）

GitHub 只保存代码；数据库和 `media/` 中的上传文件不会随 `git clone` 带到新电脑。若要保留已有用户、任务、抽样结果和上传文件，请在旧电脑停止写入后备份 MySQL 数据库及 `media/`，安全地传到新电脑，先恢复数据库和 `media/`，再执行迁移和启动。不要把数据库备份、`media/` 或 `.env` 上传到 GitHub。

可使用 MySQL 自带的 `mysqldump` 客户端导出 SQL 文件，再用 `mysql` 客户端导入新电脑的同名数据库；连接参数应与实际 `.env` 一致。请核对备份文件及恢复后的表。PowerShell 的输入输出重定向语法和编码随版本变化，迁移时按所安装 MySQL 客户端的文档操作。恢复后不要运行 `-SeedDemo`。

## 6. 更新代码

停止运行中的服务，在仓库目录拉取当前部署分支，安装新增依赖并迁移：

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\scripts\start.ps1
```

这个启动方式面向本机和受信任局域网演示。若要公开到互联网，需要另行配置正式 Web 服务、HTTPS、静态及媒体文件服务、备份与安全设置；不要直接把 `runserver` 暴露到公网。

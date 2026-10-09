# Ubuntu 24.04 公网 IP HTTPS 部署

适用于天翼云公网 IP `113.250.177.180`、暂不使用域名的测试部署。管理员访问 `https://113.250.177.180/manage/`，手机端访问 `https://113.250.177.180/m/`。Nginx 使用自签名证书；浏览器会警告，手动继续访问也不保证手机定位可用。本文命令在服务器的 Bash 中执行，不使用 Windows `start.ps1`、mkcert 或仓库内带演示密码的 `docker-compose.yml`。

## 1. 云侧与系统准备

在天翼云安全组入方向只开放 TCP 80、443 和来自你的管理 IP 的 TCP 22。不要开放 3306、8000。确认公网 IP 仍是 `113.250.177.180`。服务器登录方式、SSH 用户名和私钥以天翼云控制台实际配置为准；首次连接示例：

```bash
ssh <你的SSH用户>@113.250.177.180
```

在 Ubuntu 上安装依赖；2 GB 内存部署 MySQL 和应用时应观察 `free -h`、`df -h`，磁盘或内存不足就先扩容，不要在不足空间时迁移数据。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx mysql-server openssl
sudo systemctl enable --now mysql nginx
sudo ss -ltnp
```

若启用了 UFW，还需在主机防火墙允许 22、80、443，并确保 SSH 规则先生效；云安全组和主机防火墙都可能拦截流量。

## 2. 建立专用用户与数据库

```bash
sudo adduser --system --group --home /opt/selectrom --no-create-home selectrom
sudo install -d -o selectrom -g www-data -m 750 /opt/selectrom /opt/selectrom/releases /opt/selectrom/shared
sudo install -d -o selectrom -g www-data -m 750 /opt/selectrom/shared/media /opt/selectrom/shared/SamplingPhotos
sudo install -d -o root -g selectrom -m 750 /etc/selectrom
```

为数据库用户生成独立密码，然后进入 MySQL 交互终端，将示例中的密码替换为该密码。密码不要发到聊天、放进 Git 或沿用演示密码。

```bash
openssl rand -base64 36
sudo mysql
```

```sql
CREATE DATABASE selectrom CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'selectrom'@'127.0.0.1' IDENTIFIED BY '<刚生成的数据库密码>';
GRANT ALL PRIVILEGES ON selectrom.* TO 'selectrom'@'127.0.0.1';
EXIT;
```

检查 MySQL 是否仅监听本机；如果监听 `0.0.0.0:3306`，先调整 MySQL 的 `bind-address` 并重启，再继续部署。

## 3. 获取发布代码并安装 Python 依赖

以下克隆已推送的功能分支。实际发布时应记录当前 Git SHA；不要把 `.env`、数据库或上传文件放入 release 目录。

```bash
RELEASE_ID=$(date -u +%Y%m%d%H%M%S)
sudo -u selectrom git clone --branch feature/random-sampling-system --single-branch https://github.com/taochengguo/selectrom.git "/opt/selectrom/releases/$RELEASE_ID"
sudo -u selectrom python3 -m venv "/opt/selectrom/releases/$RELEASE_ID/.venv"
sudo -u selectrom "/opt/selectrom/releases/$RELEASE_ID/.venv/bin/python" -m pip install --upgrade pip
sudo -u selectrom "/opt/selectrom/releases/$RELEASE_ID/.venv/bin/python" -m pip install -r "/opt/selectrom/releases/$RELEASE_ID/requirements.txt"
sudo ln -s "/opt/selectrom/releases/$RELEASE_ID" /opt/selectrom/current
sudo -u selectrom git -C /opt/selectrom/current rev-parse HEAD
```

## 4. 配置私有环境变量

生成新的 Django 密钥：

```bash
openssl rand -base64 48
sudo install -o root -g selectrom -m 640 /dev/null /etc/selectrom/selectrom.env
sudoedit /etc/selectrom/selectrom.env
```

将下列内容填入文件，并替换尖括号中的值。`TIANDITU_API_KEY` 需要允许服务端调用地理编码与逆地理编码。不要运行 `seed_demo`，正式账号应单独创建。

```dotenv
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<新生成的Django密钥>
DJANGO_ALLOWED_HOSTS=113.250.177.180,127.0.0.1,localhost
DJANGO_TRUST_PROXY_HTTPS=true
DJANGO_CSRF_TRUSTED_ORIGINS=https://113.250.177.180
DJANGO_SECURE_COOKIES=true
DJANGO_MEDIA_ROOT=/opt/selectrom/shared/media
SAMPLING_PHOTOS_ROOT=/opt/selectrom/shared/SamplingPhotos
MYSQL_DATABASE=selectrom
MYSQL_USER=selectrom
MYSQL_PASSWORD=<数据库用户密码>
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
TIANDITU_API_KEY=<你的天地图服务端Key>
TIANDITU_DIRECT_EGRESS=false
```

手动执行管理命令时，使用下面的方式读取同一个私有环境文件。仅在自己的受控终端执行；不要打开 Bash 命令回显或把密钥写进公开日志。

```bash
sudo -u selectrom bash -c 'set -a; source /etc/selectrom/selectrom.env; set +a; cd /opt/selectrom/current; .venv/bin/python manage.py check; .venv/bin/python manage.py migrate; .venv/bin/python manage.py collectstatic --noinput; .venv/bin/python manage.py check --deploy'
```

`check --deploy` 可能提示未启用 HSTS，以及 Django 自身未开启 HTTP→HTTPS 重定向；本阶段由 Nginx 对 80 端口重定向，且使用临时自签名证书，暂不启用 HSTS。其它警告应在上线前逐项处理。确认 `/opt/selectrom/current/staticfiles/` 已生成。

## 5. 安装自签名证书、systemd 与 Nginx

脚本在证书的 Subject Alternative Name 中写入公网 IP。私钥只留在服务器的 `/etc/selectrom/tls/ip.key`，绝不能提交到 Git。IP 改变或证书到期后需重新生成并重载 Nginx。

```bash
sudo bash /opt/selectrom/current/deploy/ubuntu/generate-ip-certificate.sh 113.250.177.180
sudo cp /opt/selectrom/current/deploy/ubuntu/selectrom.service /etc/systemd/system/selectrom.service
sudo cp /opt/selectrom/current/deploy/ubuntu/selectrom.nginx.conf /etc/nginx/sites-available/selectrom
sudo ln -s /etc/nginx/sites-available/selectrom /etc/nginx/sites-enabled/selectrom
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now selectrom
sudo systemctl reload nginx
```

若默认站点链接不存在，`sudo rm` 会报告不存在，可继续检查 `nginx -t`。外部测试前确认：

```bash
sudo systemctl status selectrom --no-pager
sudo journalctl -u selectrom -n 80 --no-pager
curl -kfsS https://113.250.177.180/health/
curl -kI https://113.250.177.180/static/css/management.css
sudo ss -ltnp
```

`curl -k` 只用于检查自签名证书下的连接，不代表证书已受信任。手机浏览器打开 HTTPS 后若允许继续，仍需单独验证 `window.isSecureContext`、定位权限、天地图请求及一次真实打卡。浏览器若不允许绕过证书警告，或定位被拒绝，就不能把打卡视为可用。

## 6. 备份、更新与回退

Git 只包含代码。旧电脑的 MySQL 数据、`media/` 与 `SamplingPhotos/` 如需迁移，先在旧电脑停止写入，分别备份后安全传输到服务器；恢复并检查后再执行迁移。不要上传备份到 GitHub。定期备份数据库和这两个上传目录，并把备份复制到服务器以外的位置。下面以停机更新为例；开始前确保磁盘容得下新 release 和完整备份。

```bash
BACKUP_ID=$(date -u +%Y%m%d%H%M%S)
sudo install -d -o root -g root -m 700 "/opt/selectrom/backups/$BACKUP_ID"
sudo systemctl stop selectrom
readlink -f /opt/selectrom/current | sudo tee "/opt/selectrom/backups/$BACKUP_ID/previous-release.txt" >/dev/null
sudo sh -c "mysqldump --single-transaction selectrom > /opt/selectrom/backups/$BACKUP_ID/database.sql"
sudo tar -C /opt/selectrom/shared -czf "/opt/selectrom/backups/$BACKUP_ID/uploads.tar.gz" media SamplingPhotos
```

完成备份后，在新的 release 目录安装新版本。应用保持停止，直到数据库迁移和静态文件收集完成；若其中任何一步报错，不要切换 `current`。记录新版本的 Git SHA：

```bash
NEW_RELEASE="/opt/selectrom/releases/$(date -u +%Y%m%d%H%M%S)"
sudo -u selectrom git clone --branch feature/random-sampling-system --single-branch https://github.com/taochengguo/selectrom.git "$NEW_RELEASE"
sudo -u selectrom python3 -m venv "$NEW_RELEASE/.venv"
sudo -u selectrom "$NEW_RELEASE/.venv/bin/python" -m pip install --upgrade pip
sudo -u selectrom "$NEW_RELEASE/.venv/bin/python" -m pip install -r "$NEW_RELEASE/requirements.txt"
sudo -u selectrom git -C "$NEW_RELEASE" rev-parse HEAD
sudo -u selectrom bash -c 'set -a; source /etc/selectrom/selectrom.env; set +a; cd "$1"; .venv/bin/python manage.py check && .venv/bin/python manage.py migrate && .venv/bin/python manage.py collectstatic --noinput' _ "$NEW_RELEASE"
```

迁移成功后原子切换链接，启动服务并做健康检查：

```bash
sudo ln -s "$NEW_RELEASE" /opt/selectrom/current.next
sudo mv -Tf /opt/selectrom/current.next /opt/selectrom/current
sudo systemctl start selectrom
curl -kfsS https://113.250.177.180/health/
```

如果更新在数据库迁移前失败，保留旧链接并启动旧服务。**迁移已经开始后**若失败，不能只切回旧代码；先停止服务，使用此次备份恢复数据库及上传文件，再切回 `previous-release.txt` 中的旧 release，启动并验证。恢复会覆盖备份之后的数据，因此必须保持停机、确认备份完整后操作。示例恢复命令：

```bash
sudo systemctl stop selectrom
sudo sh -c "mysql selectrom < /opt/selectrom/backups/$BACKUP_ID/database.sql"
sudo tar -C /opt/selectrom/shared -xzf "/opt/selectrom/backups/$BACKUP_ID/uploads.tar.gz"
OLD_RELEASE=$(sudo cat "/opt/selectrom/backups/$BACKUP_ID/previous-release.txt")
sudo ln -s "$OLD_RELEASE" /opt/selectrom/current.next
sudo mv -Tf /opt/selectrom/current.next /opt/selectrom/current
sudo systemctl start selectrom
curl -kfsS https://113.250.177.180/health/
```

若恢复失败，保持服务停止并保存备份和日志，先查明原因。证书临近到期时重新生成证书并运行 `sudo nginx -t && sudo systemctl reload nginx`。这个自签名方案只适合当前临时测试阶段。

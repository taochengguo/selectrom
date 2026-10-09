# 随机抽样系统（本机演示版）

这是一个使用 Django 和 MySQL 的随机抽样演示系统。管理员仅使用电脑端后台，抽样人员仅使用手机 H5。任务执行时，系统从管理员预先维护的抽样人员分组中随机抽取一人；新建任务由该人员在手机端填写样品数量和抽样样品数，再从 1 到样品数量的序号中无重复随机抽取。

## 首次安装

### 1. 前置条件

- Windows PowerShell
- Python 3.12（或兼容的 Python 3）
- mkcert（启动脚本会在未安装时从官方地址下载 Windows 版本）
- MySQL 8.x，或者 Docker Desktop
- 天地图开放平台 API Key，用于现场收货地址定位

本机 MySQL 需先创建与 .env 一致的数据库和用户。若使用 Docker，可在项目根目录执行：

    docker compose up -d db

### 2. 创建环境并安装依赖

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

### 3. 配置数据库

复制模板后，按本机 MySQL 修改 .env；该文件包含凭据，已被 Git 忽略，不应提交。

    Copy-Item .env.example .env

`.env.example` 中的 `DJANGO_SECRET_KEY` 只适用于本机演示。任何非本机演示环境都必须替换为独立的强随机密钥；当 `DJANGO_DEBUG=false` 时，未配置 `DJANGO_SECRET_KEY` 会直接导致启动失败。

### 4. 迁移与演示数据

    .\.venv\Scripts\python.exe manage.py migrate
    .\.venv\Scripts\python.exe manage.py seed_demo

演示账号（仅本机演示）：

- 管理员：demo_admin
- 抽样人员：demo_sampler_01、demo_sampler_02、demo_sampler_03
- 密码：demo123456

非演示环境必须修改这些密码。

## 日常启动

请在 PowerShell 中先进入含有 `manage.py` 的项目目录。另一台电脑从 GitHub 获取代码和迁移已有数据的步骤见 [跨电脑部署说明](docs/deploy-on-another-computer.md)。

```powershell
cd <项目目录>
```

界面默认使用简体中文，包含登录、表单校验和个人资料。修改后请重启服务并刷新页面。

先确认 .env 已存在，再运行：

    .\scripts\start.ps1

首次演示或需要创建尚不存在的演示数据时：

    .\scripts\start.ps1 -SeedDemo

该命令不会修复或覆盖已存在的同编号任务；如本机演示创建中断，请删除未执行的损坏演示任务后再运行，或使用新数据库。

脚本只读取 .env，不会创建或覆盖它；会先执行迁移，然后监听局域网地址 0.0.0.0:8000。

- 登录页：https://localhost:8000/login/
- 电脑端后台：https://localhost:8000/manage/
- 手机 H5：使用启动终端显示的 `https://<局域网 IP>:8000/m/`

启动脚本使用 mkcert 为本机及局域网 IP 签发 HTTPS 开发证书。手机首次访问前，将终端显示路径下的 `.certs/mobile-rootCA.pem` 安装并信任为 CA 证书；不要分享 mkcert CA 目录中的 `rootCA-key.pem`。具体手机安装步骤见[部署指南](docs/deploy-on-another-computer.md)。

启动脚本会自动读取已连接的物理以太网 / Wi-Fi 网卡的 IPv4 地址，临时加入 Django 主机白名单，为这些地址生成 mkcert 证书，并在终端显示 HTTPS 链接。手机和电脑需连接同一网络，且手机需信任开发 CA。

电脑 IP 改变或切换网络后，停止服务并重新运行 `./scripts/start.ps1`，即可自动获取新地址，无需修改 `.env`。有多张已连接网卡时会显示多个地址，请使用与访问设备处于同一局域网的地址。未检测到局域网地址时会给出提示，本机仍可访问。

`.env` 中的 `DJANGO_ALLOWED_HOSTS` 仅用于保留本机地址和额外的自定义域名；多个值用英文逗号分隔。脚本通过临时环境变量 `DJANGO_LAN_HOSTS` 传入自动检测的地址，不会写回 `.env`。直接运行 `python manage.py runserver` 不会触发地址检测，请使用启动脚本。

若其他设备连接超时，请确认 Windows 防火墙允许本地子网访问 TCP 8000 端口，且路由器未开启访客网络隔离或 AP 隔离。无需开放 MySQL 的 3306 端口。

## 管理员到抽样人员的完整演示流程

1. 以管理员登录，在“抽样任务”点击“新建任务”，于弹窗中录入质检、订单、物资和收货信息，并选择已有抽样人员分组。任务编号自动生成；Excel 导入入口暂不可用。
2. 将任务置为“待执行（ready）”。
4. 点击“执行”，系统从任务的自定义抽样人员分组中完全随机抽取 1 人，并把任务下发给该人。
5. 该抽样人员在手机 H5 的“任务提醒”进入任务，填写样品数量和抽样样品数，再点击“开始抽样”；系统生成无重复的样品序号并锁定结果。
6. 抽样人员完成任务；管理员可在任务详情和系统日志中查看仅与该抽样任务相关的事件。

“执行”只能成功一次。确需换人时，管理员必须使用“重新分配”、填写原因；系统保留原人员和新人员的记录。首次抽样结果会立即锁定；因样品损坏等确需重抽时，管理员必须先批准并填写原因，历史抽样结果会保留，且授权重抽期间不能更换抽样人员。

已有候选物资任务仍按原方式运行：管理员逐条录入候选物资或导入 UTF-8 CSV（表头为“物资编号,订单号,供应商,物资名称,物资数量”），抽取数量不得超过候选物资记录数。新建的样品序号任务不使用候选物资或 CSV 导入。

现场报告在每次已锁定抽样批次下单独记录检测结果和打卡。请将天地图 Key 配置到 `.env` 的 `TIANDITU_API_KEY`，并为该 Key 开通地理编码和逆地理编码服务。收货地址经天地图定位后确定所属地市，设备定位经逆地理编码取得现场地市与详细地址；两者同市即可正常打卡，跨市或定位异常需填写备注。现场地址和地市随打卡记录保存。现场照片只保留在个人端当前页面，导出时通过浏览器打印功能保存为 PDF，不会上传到服务器。手机浏览器需要 HTTPS 页面才能提供设备定位；本机 localhost 访问可用于开发。

若打卡提示天地图 HTTP 403，请根据提示区分地理编码接口权限、Key 来源限制或安全策略拦截；安全策略拦截会同时显示事件 ID。服务端日志仅记录接口路径、HTTP 状态和事件 ID，不记录 Key。

`TIANDITU_API_KEY` 必须是允许服务端调用地理编码与逆地理编码的 Key；浏览器端类型 Key 会被天地图以 HTTP 403 拒绝。

若电脑运行了 Meta Tunnel 等代理，天地图接口可能因代理的境外出口返回 HTTP 418。在 `.env` 中设置 `TIANDITU_DIRECT_EGRESS=true` 并通过 `scripts/start.ps1` 启动，脚本会从当前实体网卡读取 IPv4、接口编号及 DNS；只有服务端的天地图 HTTPS 请求使用该网卡直连，仍会校验天地图证书。网络或电脑 IP 变化后重启启动脚本即可重新检测。直连模式目前仅支持 Windows。

## 验证与测试

    .\.venv\Scripts\python.exe manage.py test sampling.tests.test_seed_demo accounts.tests.test_smoke -v 2
    .\.venv\Scripts\python.exe manage.py test -v 2
    .\.venv\Scripts\python.exe manage.py check
    .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run

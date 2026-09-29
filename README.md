# 随机抽样系统（本机演示版）

这是一个使用 Django 和 MySQL 的随机抽样演示系统。管理员仅使用电脑端后台，抽样人员仅使用手机 H5。任务执行时，系统从管理员预先维护的抽样人员分组中随机抽取一人；该人员在手机端通过动画从候选物资中无重复随机抽样。

## 首次安装

### 1. 前置条件

- Windows PowerShell
- Python 3.12（或兼容的 Python 3）
- MySQL 8.x，或者 Docker Desktop

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

- 登录页：http://127.0.0.1:8000/login/
- 电脑端后台：http://127.0.0.1:8000/manage/
- 手机 H5：http://127.0.0.1:8000/m/

启动脚本会自动读取已连接的物理以太网 / Wi-Fi 网卡的 IPv4 地址，临时加入 Django 主机白名单，并在终端显示登录页、电脑后台和手机 H5 的局域网链接。其他设备连接同一网络后，打开终端显示的链接即可。

电脑 IP 改变或切换网络后，停止服务并重新运行 `./scripts/start.ps1`，即可自动获取新地址，无需修改 `.env`。有多张已连接网卡时会显示多个地址，请使用与访问设备处于同一局域网的地址。未检测到局域网地址时会给出提示，本机仍可访问。

`.env` 中的 `DJANGO_ALLOWED_HOSTS` 仅用于保留本机地址和额外的自定义域名；多个值用英文逗号分隔。脚本通过临时环境变量 `DJANGO_LAN_HOSTS` 传入自动检测的地址，不会写回 `.env`。直接运行 `python manage.py runserver` 不会触发地址检测，请使用启动脚本。

若其他设备连接超时，请确认 Windows 防火墙允许本地子网访问 TCP 8000 端口，且路由器未开启访客网络隔离或 AP 隔离。无需开放 MySQL 的 3306 端口。

## 管理员到抽样人员的完整演示流程

1. 以管理员登录，在“抽样任务”创建任务，选择已创建的抽样人员分组，并填写抽取数量。
2. 在任务中逐条录入候选物资，或导入 CSV。CSV 必须为 UTF-8 编码，且首行必须严格为：物资编号,订单号,供应商,物资名称,物资数量。可直接使用 samples/materials.csv。
3. 候选物资数量不小于抽取数量时，将任务置为“待执行（ready）”。
4. 点击“执行”，系统从任务的自定义抽样人员分组中完全随机抽取 1 人，并把任务下发给该人。
5. 该抽样人员在手机 H5 的“任务提醒”进入任务，点击抽样；物资编号会经过随机抽取动画后生成无重复的锁定结果。
6. 抽样人员完成任务；管理员可在任务详情和系统日志中查看仅与该抽样任务相关的事件。

“执行”只能成功一次。确需换人时，管理员必须使用“重新分配”、填写原因；系统保留原人员和新人员的记录。首次抽样结果会立即锁定；因样品损坏等确需重抽时，管理员必须先批准并填写原因，历史抽样结果会保留，且授权重抽期间不能更换抽样人员。

## 验证与测试

    .\.venv\Scripts\python.exe manage.py test sampling.tests.test_seed_demo accounts.tests.test_smoke -v 2
    .\.venv\Scripts\python.exe manage.py test -v 2
    .\.venv\Scripts\python.exe manage.py check
    .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run

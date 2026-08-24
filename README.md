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

### 4. 迁移与演示数据

    .\.venv\Scripts\python.exe manage.py migrate
    .\.venv\Scripts\python.exe manage.py seed_demo

演示账号（仅本机演示）：

- 管理员：demo_admin
- 抽样人员：demo_sampler_01、demo_sampler_02、demo_sampler_03
- 密码：demo123456

非演示环境必须修改这些密码。

## 日常启动

先确认 .env 已存在，再运行：

    .\scripts\start.ps1

首次演示或需要创建尚不存在的演示数据时：

    .\scripts\start.ps1 -SeedDemo

脚本只读取 .env，不会创建或覆盖它；会先执行迁移，然后监听局域网地址 0.0.0.0:8000。

- 登录页：http://127.0.0.1:8000/login/
- 电脑端后台：http://127.0.0.1:8000/manage/
- 手机 H5：http://127.0.0.1:8000/m/

手机访问时，将 127.0.0.1 替换为电脑的局域网 IP，并在 .env 的 DJANGO_ALLOWED_HOSTS 中加入该 IP。

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

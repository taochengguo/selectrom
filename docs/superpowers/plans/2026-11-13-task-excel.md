# 抽样任务 Excel 导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 管理员上传现有周计划，编辑或删除预览记录后创建草稿，完整保留来源并精确查重。

**Architecture:** openpyxl只读解析受限文件；独立导入表单/服务和视图复用现有生命周期。服务器会话隔离草稿，确认时事务校验并查重。

**Tech Stack:** Django、openpyxl、defusedxml、原生JavaScript。

**Spec:** docs/superpowers/specs/2026-11-13-task-excel-design.md

## Global Constraints
- .xlsx限5MB、500条、解压40MB。
- 不修改真实任务，预览删除不影响现有任务。
- 不覆盖已有非本次变更；不提交、推送或部署。

## Review Focus
- 相同订单不同质检类型或任一来源字段不同必须创建。
- 编辑、删除后重新检查，非法行不能部分写入。
- 重复确认、跨用户和过期预览不得创建。
- 电话和长标识保持文本，日期和数量正确规范。
- 畸形文件、公式、未知列、超限受到可理解的拒绝。

### Task 1: 解析及事务导入
Files: sampling/services/task_excel.py, sampling/forms.py, sampling/models.py, sampling/services/lifecycle.py, sampling/migrations/0011_samplingtask_category_name_and_source_metadata.py, sampling/tests/test_task_excel.py, requirements.txt.
- [x] 写失败测试：解析20列、日期/标识、无采购列/公式/坏文件；全字段查重、错误原子性。
- [x] 运行 manage.py test sampling.tests.test_task_excel，确认缺失功能。
- [x] 实现 parse_task_workbook(upload) -> list[dict]、prepare_rows(rows,group) -> list[dict]、commit_rows(rows,group,actor) -> (created,skipped)。新增品类及来源JSON，复用生命周期审计。
- [x] 运行以上测试确认通过。

### Task 2: 可编辑预览及管理平台集成
Files: sampling/task_excel_views.py, sampling/management_urls.py, templates/management/tasks/excel_import.html, templates/management/tasks/list.html, templates/management/tasks/detail.html, static/js/task-excel-import.js, static/css/task-excel-import.css, sampling/tests/test_task_excel_views.py.
- [x] 写失败视图测试：上传无写入、编辑/删除后确认、错误回显、令牌重用/跨用户、权限。
- [x] 运行对应测试确认失败后实现上传、校验及确认视图，预览表单可编辑、逐行删除。
- [x] 集成品类普通任务编辑/详情，启用列表入口。
- [x] 运行聚焦及全套测试、Django检查、迁移检查；迁移本地数据库。浏览器验证上传、修改、删除、校验，真实表格仅预览不创建。

## Ledger
- 用户“其他的执行”授权按已确认方案实施；直接在现有运行中的隔离worktree内执行，不另建分支。

## Verification
- Full suite after modal integration: 203 tests passed; Django check and makemigrations --check passed.
- Review found URL-encoded Chinese preview body limit; regression failed with 400, then fixed by multipart preview and a bounded 48MB request limit.
- Browser: actual supplied workbook parsed as 3 valid, 0 duplicate, 0 invalid; edit/delete/restore/revalidate verified. Kept original three preview rows, no tasks created. Browser screenshot capture unavailable.
- Unrelated existing config/images.py and benchmark script changes preserved.
- Modal integration: upload/preview/revalidation remain in the task list; AJAX response regression covered. Browser upload and preview verified; screenshot saved locally under .testtmp (excluded from commit).
- User explicitly requested GitHub upload after verification; commit and push the feature to the existing feature/random-sampling-system branch, preserving unrelated local files.

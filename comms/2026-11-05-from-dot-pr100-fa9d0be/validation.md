# PR #100 与最新基线组合验证

验证日期：2026-11-05 UTC。没有远端写入、强推、PR 合并、main/feature 写入或生产操作。

## 结论

现有 PR head df79017598c9a0dbd9ef263c4ed51e559dcdb43c 可以正常、无冲突地合入最新 feature/0.4 基线 fa9d0be8125248f5a0ceba6659789e5ff8754fe9。原完整 enabled_since 补丁在新基线上也可原样应用，没有偏移或冲突。

两条独立构建路径的最终 tree 完全相同：d06aa02107c923835c37bbb12bde087dc0759609。因此本包不是冲突修复，也没有增加新逻辑；建议更新现有 PR head 的原因，是让后续 CI 明确覆盖 MAPLE-135 批量清理、#107 Eltiro 修正与 #100 的新组合。

本地选定 28 个测试文件共 569 项：568 passed、1 xfailed、1 warning，999.49 秒，退出码 0。全仓 Ruff、18 项 schema 和差异检查通过。选定测试不等于全量测试、GitHub CI 或生产验证。

## 精确产物

- Commit：8562d05d707356f9393ba2a78dc75b98def3ab72
- Tree：d06aa02107c923835c37bbb12bde087dc0759609
- 第一父：df79017598c9a0dbd9ef263c4ed51e559dcdb43c（当前 PR head）
- 第二父：fa9d0be8125248f5a0ceba6659789e5ff8754fe9（新基线）
- Bundle：pr100-sync-fa9d0be.bundle，2128 bytes，1 个新 commit、12 个 Git 对象。
- Bundle SHA-256：1cf5d91aabdf662bf06fa266789618e62b073d7499387dbe16b80f60cffb3dcd
- Base64 文件：pr100-sync-fa9d0be.bundle.base64，2878 bytes。
- 原补丁：https://github.com/zenithli/datumoj/blob/471c0344c1c13e83f84dca2f3fda97da4baf35dc/comms/2026-11-05-from-dot-cloud29-and-rebase/pr100-rebased-on-2f03e89.patch
- 原补丁 SHA-256：15d8deb53f8880e874e6707a704f84d10cc7200be1da8dce5fe5f37f2567261c
- 稳定 patch-id：4caa46e2a7c423a12857e433d6789ea909788485，与前一轮原补丁相同。

## 内容完整性

1. git merge-tree --write-tree --messages 对两个精确父提交返回 0，只对 runners.md 与 test_cloud_run.py 进行正常自动合并。其 tree 与独立临时 index 中“新基线加原完整补丁”的 tree 相同。
2. 新基线自 8f5bc7a 的 16 个变更文件中，除双方都修改的两个文件外，其余 14 个逐字节保留，包括 state.py、state_s3.py、test_audit_135.py 及全部 #107 Eltiro 变更。
3. 当前基线 tests/test_cloud_run.py 的全部 80 个顶层 AST 节点（包括 48 个测试函数）完整保留。新增的 3 个 #100 测试函数与前一 PR head 一致，最终共 51 个测试函数。
4. test_cleanup_delete_failure_keeps_published_result_successful 的 AST 与新基线完全一致，失败注入仍针对 delete_objects，未退回单删 delete_if_match。
5. #100 的 cloud.py、core/monitor.py、core/schedule.py 和新增 enablement 测试文件，与前一 PR head 逐字节一致。新基线 runners.md 文字全部保留，只插入原补丁的 6 行。
6. 对新基线的差异仍是原补丁的 6 文件、265 插入、9 删除；对当前 PR head 的差异严格对应上游这轮 16 文件、460 插入、38 删除。
7. 5 个受影响 Python 文件 AST 可解析，git diff --check 通过。测试结束后再次确认工作文件、index 与打包 commit tree 一致，pyproject.toml 和 uv.lock 未变。
8. bundle verify、Git pack 校验通过。独立离线 consumer 导入前没有新 commit；具备两个父提交历史及必要旧对象后，unbundle 得到精确 commit、tree 和有序 parents。

涉及的 #100 六文件与原补丁目的不变：runners.md 说明启用计时；cloud.py 将时间用于云端健康和周报；monitor.py 更新告警起点；schedule.py 持久化、校验和迁移启用时间；两个测试文件覆盖跨代次、重新启用和旧状态迁移。没有把其他诊断或环境修复混入代码。

## 真实本地测试

环境为 Python 3.12.14、pytest 9.1.1、Ruff 0.17.1、httpx 0.28.1。新隔离 checkout 按现有 uv.lock 安装依赖，仅补本运行环境 SOCKS 代理所需的官方 PyPI socksio==1.0.0。代理设置不变，跟踪的依赖文件不变。已核对 Python 实际导入当前隔离 checkout 的代码。

应用 #100 之前，直接 detached fa9d0be 上执行 cleanup/S3 对照组：149 passed，118.19 秒。

```sh
uv run --offline --frozen --no-sync pytest -q \
  tests/core/test_state.py tests/core/test_state_s3.py \
  tests/regressions/test_audit_131.py \
  tests/regressions/test_audit_134.py \
  tests/regressions/test_audit_135.py
```

应用原补丁后的扩大组合组：568 passed、1 xfailed、1 warning，999.49 秒。

```sh
uv run --offline --frozen --no-sync pytest -q \
  tests/core/test_schedule_enablement.py \
  tests/core/test_monitor.py tests/core/test_monitor_cloud.py \
  tests/core/test_schedule.py tests/core/test_schedule_due.py \
  tests/test_cli_schedule.py tests/test_cloud_embed.py \
  tests/test_cloud_reports.py tests/test_cloud_run.py \
  tests/test_cloud_workflow.py \
  tests/analysis/test_weekly_report.py \
  tests/analysis/test_weekly_report_eltiro.py \
  tests/regressions/test_audit_117.py tests/regressions/test_audit_118.py \
  tests/core/test_state.py tests/core/test_state_blocks.py \
  tests/core/test_state_fs.py tests/core/test_state_s3.py \
  tests/core/test_state_vectors.py \
  tests/regressions/test_audit_131.py tests/regressions/test_audit_132.py \
  tests/regressions/test_audit_134.py tests/regressions/test_audit_135.py \
  tests/eltiro/test_executor.py tests/eltiro/test_profiles.py \
  tests/eltiro/test_matching.py tests/eltiro/test_models.py \
  tests/integration/test_wisteria_m1.py
```

实际运行另写入本地 JUnit 结果供核验，未公开原始日志或运行路径。JUnit 明确确认以下关键测试通过：
- test_cleanup_delete_failure_keeps_published_result_successful
- test_thousand_objects_need_five_requests_and_five_lease_checks
- test_bulk_cleanup_uses_only_requested_keys_without_get_or_head

唯一 xfail：tests/integration/test_wisteria_m1.py::test_us_dollar_series_ranks_first_for_gdp_usd，既有的 GDP 单位文本匹配排序质量缺口（current LCU 排在 current US$ 前）。这不是本次新失败，也未声称该缺口已解决。唯一 warning 来自已有锁测试中的多线程进程 os.fork DeprecationWarning，未隐藏。

两个 audit_132 规模回归都跑完并通过。它们只处理本地 SQLite/Lance 与合成对象；运行中未中断、跳过或改小规模。

其他已通过命令：

```sh
uv run --offline --frozen --no-sync ruff check src tests
uv run --offline --frozen --no-sync python tests/validate_schemas.py
git diff --cached --check
```

## 现有 CI 与评审的准确边界

- CI #332：https://github.com/gorou5/datumoj/actions/runs/42037694718 ，success。对应旧 PR head df79017，实际 checkout candidate e8b67d2e52d09e8cfd9da9154877eedc4af9e8ff（df79017 + 8f5bc7a），5316 passed、2 xfailed、1 warning。它不覆盖最新 fa9d0be 组合。
- CI #336：https://github.com/gorou5/datumoj/actions/runs/42049401968 ，success。实际 checkout 是 PR #88 候选 a0298c9（fa9d0be 合入 main fdade72），5332 passed、1 xfailed、1 warning，541.49 秒。它不包含 #100，不应写成直接 checkout fa9d0be 的测试。
- 本地 149 项对照确实直接运行在 detached fa9d0be；本地 569 项组合运行在本包精确 tree。以上三种范围不同。
- 尚无正式 review。CodeRabbit 因目标不是默认分支而跳过自动评审；不能据此称“已审核”或“无问题”。没有触发外部 bot 或修改评审配置。

## 尚未完成的验收与权限边界

本包尚未转推，没有新 commit 的 GitHub CI；未执行新组合全量 pytest、生产抓取、真实对象存储清理、调度试运行或容量验证。不得把本地结果写成新组合完整 CI 通过或允许合并。

Muse 仅验证并正常 fast-forward 转推到 fix/source-monitor-enabled-since，随后返回 PR head 和 push 结果。任一父分支 SHA 变化都应停止并交回 dot 更新包，不强推、不自行修补。PR 合并、main/feature 写入仍需用户另行批准。

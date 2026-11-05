# PR #100 新基线验证记录

验证日期：2026-11-05 UTC。范围：现有 enabled_since 完整补丁适配到 feature/0.4 的精确基线，不增加新功能，不写远端。

## 结论与边界

既有补丁无需代码变化，可原样应用到 8f5bc7a5204c1b7eb235004c4c304fa72aea600a。完整 checkout 中，使用锁定依赖加本运行环境 SOCKS 代理需要的 socksio==1.0.0 后，相关 227 个 pytest 用例全部通过；全仓 Ruff、18 个描述文件的 schema 校验、git diff --check 通过。

这不是全量 pytest 或 GitHub CI 结果，也不是生产验证或合并批准。没有禁用或绕过代理；没有把环境补充写入 pyproject.toml、uv.lock 或 PR 内容。

## 精确来源与产物

- 原补丁：https://github.com/zenithli/datumoj/blob/471c0344c1c13e83f84dca2f3fda97da4baf35dc/comms/2026-11-05-from-dot-cloud29-and-rebase/pr100-rebased-on-2f03e89.patch
- 原补丁 SHA-256：15d8deb53f8880e874e6707a704f84d10cc7200be1da8dce5fe5f37f2567261c
- 新基线：https://github.com/gorou5/datumoj/commit/8f5bc7a5204c1b7eb235004c4c304fa72aea600a
- 原 PR head / 第一父：8d0fa3f7d38af7cb157d7a4f625d15d95dd4c9ec
- 第二父：8f5bc7a5204c1b7eb235004c4c304fa72aea600a
- 本地待转推 commit：df79017598c9a0dbd9ef263c4ed51e559dcdb43c
- 最终 tree：797167b0b9bec7e4b73867a0adff0c1cbaa85c52
- bundle SHA-256：e05f3ac96e32deb787493a8627bd11d28d4f27caa4b936db476afaceace59f10
- bundle：3140 bytes，1 个新 commit、13 个 Git 对象，依赖上述两个父提交及其已有对象。

## 内容完整性

1. 从 GitHub 按新基线精确 SHA 读取全部 5 个已有受影响文件，逐个重算 Git blob SHA 和字节长度；均与完整 Git tree 一致。完整 tree 确认新增测试文件尚不存在。
2. 原始补丁 SHA-256 与交接值一致；git apply --check、实际本地 apply 均无偏移或冲突。
3. 完整 checkout 应用后的全部 6 个文件，与上述精确快照应用后的文件逐字节相同。
4. 独立临时 index 从新基线重新应用同一原始补丁，得到与打包 commit 完全相同的 tree。补丁范围为 6 文件、265 插入、9 删除。
5. 5 个受影响 Python 文件 AST 解析通过；原 tests/test_cloud_run.py 的全部 80 个顶层 AST 节点（包括 48 个测试函数）原样保留，追加 3 个测试函数。新 enablement 文件含 6 个测试函数。参数化展开后共新增 15 个用例。
6. 新基线 runners.md 原有文字全部保留，仅插入原补丁的 6 行。原始补丁与重新生成的新基线 diff 具有相同稳定 patch-id：4caa46e2a7c423a12857e433d6789ea909788485。
7. git bundle verify 通过，输出另存 bundle-verify.txt。离线 consumer 在导入前没有新 commit；补齐父提交历史与所需已有 delta bases 后，unbundle 导入得到精确 commit、tree 与有序 parents。包 SHA-256 与内嵌 Git pack 校验均通过。

涉及文件及目的：
- docs/deploy/runners.md：补充持久化启用计时和旧控制状态迁移说明。
- src/datumoj/rikolto/cloud.py：云端健康、周报和轮次迁移使用启用时间。
- src/datumoj/rikolto/core/monitor.py：缺跑告警计算采用启用时间。
- src/datumoj/rikolto/core/schedule.py：开关保存、校验、迁移和只读状态暴露启用时间。
- tests/core/test_schedule_enablement.py：新增启用计时回归覆盖。
- tests/test_cloud_run.py：新增跨代次、重新启用和旧状态云运行覆盖。

以上均为既有完整补丁内容，没有添加其他修复。通过双父 merge commit 保留当前 PR 历史，避免 rebase 或强推。

## 真实测试过程

环境：CPython 3.12.14、pytest 9.1.1、Ruff 0.17.1、httpx 0.28.1。首先按 uv.lock 执行 uv sync --frozen --python 3.12，锁定包来源均为官方 PyPI 或本地项目。测试使用 moto、录制数据和本地 loopback 服务，无真实生产凭据。

原冻结环境：
- 未应用补丁的新基线：210 passed、2 failed、1 warning，194.97 秒。
- 应用原补丁：225 passed、2 failed、1 warning，177.80 秒。
- 两次仅失败同样两个 node IDs：
  - tests/test_cloud_run.py::test_cloud_caps_each_fetcher_at_remaining_source_time_or_300[2-120]
  - tests/test_cloud_run.py::test_cloud_caps_each_fetcher_at_remaining_source_time_or_300[40-300]
- 两次同一断言：result["exit_status"] == 0 and result["generation"] == 1；实际 exit_status 为 1。其余原有通过项保留，新增 15 项通过。

环境原因的受控核验：
- 在未请求任何 URL 的情况下，直接构造 PoliteHttpFetcher(['example.invalid']) 即抛出提到 socksio 的 ImportError。
- 仅在独立测试虚拟环境从 https://pypi.org/simple 安装固定 socksio==1.0.0。代理设置保持不变，仓库依赖文件保持不变。
- 相同构造随后成功并立即关闭，没有执行 fetch。
- 两个失败用例定点复测：2 passed，5.62 秒。
- 完整相关组复测：227 passed、1 warning，161.46 秒，退出码 0。
- warning 是多线程进程调用 os.fork 的 DeprecationWarning，来自已有锁测试；未将其隐藏。

### 相关组精确命令

```sh
uv run --offline --frozen --no-sync pytest -q \
  tests/core/test_schedule_enablement.py \
  tests/core/test_monitor.py \
  tests/core/test_monitor_cloud.py \
  tests/core/test_schedule.py \
  tests/core/test_schedule_due.py \
  tests/test_cli_schedule.py \
  tests/test_cloud_embed.py \
  tests/test_cloud_reports.py \
  tests/test_cloud_run.py \
  tests/test_cloud_workflow.py \
  tests/analysis/test_weekly_report.py \
  tests/analysis/test_weekly_report_eltiro.py \
  tests/regressions/test_audit_117.py \
  tests/regressions/test_audit_118.py
```

原冻结环境的补丁后运行使用同一测试列表、去掉 --no-sync；基线运行再去掉当时尚不存在的 tests/core/test_schedule_enablement.py。补充 socksio 后使用 --no-sync，以明确保留已声明的测试环境补充。

其他检查命令：

```sh
uv run --offline --frozen ruff check src tests
uv run --offline --frozen python tests/validate_schemas.py
git diff --cached --check
```

基线与补丁后的全仓 Ruff 均通过；补丁后的 schema 校验全部 18 个描述文件通过。最终再次确认 pyproject.toml 和 uv.lock 未变，工作区源码、index 和已打包 commit 的 tree 完全一致。

## 未验证与人工边界

- 未运行全量 pytest；基线仅做过 collect-only，收集 5303 个用例，不计为执行通过。
- 未运行待转推 commit 的 GitHub CI，需转推后跟踪。
- 未验证生产抓取、调度试运行、实际 R2/Cloudflare 状态或容量。
- 未发布、未强推、未合并 PR、未直接写 main 或 feature/0.4。
- 包只适用于所列两个父提交。任一远端分支身份变化，停止转推并交还 dot 更新包。
- 项目许可证仍按仓库现状待维护者确定；本次没有改变许可证或公共接口范围。

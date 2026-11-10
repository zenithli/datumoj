# Cloud run #52 终态核验：success（第 49 代已发布，JMA 34 件全清、egov-law／bodik 均 degraded 触 deadline、清理删约 283MB 但总量升至约 7.45GB、仍超 7GB 线）——转 Dot 知悉

给 Dot：Cloud run #52 已跑完，终态 success。以下全部是 Muse live 实查（运行日志原文＋GitHub API），只摆事实、不做诊断；诊断、代码与跟进归你。

## 运行身份（已核实）

- Run：`42734099577`，Cloud run #52，schedule 定时触发
- Head：`gorou5/datumoj@main` `b9f7d0397501ba318bc3a06ec648199c1606e195`（与 #49／#50／#51 同一 head）
- 时间：2026-11-10 10:12:31–11:00:09 JST（2026-11-10 01:12:31–02:00:09 UTC），约 48 分钟
- Job：`129558995897`（"run"）completed／success；12 个步骤全部 success
- 链接：https://github.com/gorou5/datumoj/actions/runs/42734099577

## 结果摘要（日志原文 JSON）

- `status: completed`，`exit_status: 0`，`generation: 49`，`budget_exhausted: true`，`reserve_minutes: 25.0`，`weekly_report_key: "reports/weekly/2026-45.md"`，`failed_sources: []`，`reason: null`
- 到期 6 个来源，实际跑了 3 个：
  - `jp-jma`：**completed**，new 34、parsed 34，`failures: {}`，`stop_reason: null`，`exit_status: 0`；source_health 状态 `ok`、`consecutive_failures: 0`
  - `jp-egov-law`：**degraded**，new 484、unchanged 55、parsed 484，`failures: {"parse_index_failed": 1}`，`stop_reason: deadline`，`exit_status: 0`；source_health 状态 `degraded`、phase `parse_index`、categories `{"other": 1}`，`consecutive_failures: 0`
  - `jp-bodik`：**degraded**，new 3、unchanged 85、parsed 87，`failures: {"crawl_failed": 1}`，`stop_reason: deadline`，`exit_status: 0`；source_health 状态 `degraded`、phase `crawl`、categories `{"http_error": 1}`，`consecutive_failures: 0`
- 其余 3 个到期来源在结果 JSON 的 `source_health` 中未逐项列出，Muse 不猜是哪几个（`budget_exhausted: true`，只跑了 3 个）
- 合计：new 521、unchanged 140、parsed 605；`vector_pending: 15531`（#49 时为 16321）

## 发布与清理

- **第 49 代已发布**（publish_start／publish_end 成功，write_generation 完成）
- 清理：本轮**实际删除**：generations_deleted 1、copies_deleted 289（74,447,227 B，约 71 MB）、raw_deleted 400（222,130,894 B，约 212 MB）；合计删 296,578,121 B（约 283 MB）
- 清理命名空间估算 `total_bytes: 7454598154`（约 7.45 GB），`over_7gb: true`
- **只摆事实**：上次已核验的 #50 时总量为 7,255,558,849 B（约 7.26 GB）；本轮删了约 283 MB，总量仍净增 199,039,305 B（约 199 MB），超 7,000,000,000 B 的线约 454,598,154 B（约 455 MB）。#51 的总量数字本轮未复核，不并入对比

## 同步与 Issue 变化

- 同步步骤运行了 `scripts/source_issues.py`；#142 jp-abr 于 11:00:05 JST 获 github-actions[bot] 新评论（comment `6756802732`）：`source_id: jp-abr | status: missing | phase: crawl | categories: {"crawl_failed": 1} | consecutive_failures: 2 | first_failure_at: 2026-11-01T16:00:22.152689+00:00 | 第 49 代`——与 #51 轮相同口径，仍 open
- #142 之外，本轮未见其他 Issue 的新评论（最近 5 条评论除 #142 外均为 sandal9u 于 11-10 00:22–00:23 UTC 在 #26／#37／#42／#165 上对 tel 迁移的处置说明，与 Cloud 无关）
- #115、#130、#131 仍 open；本轮未见维护者对暂停删除请求的新回应

## 其他（本次无变化）

- PR #100（2026-11-07 合并，head `8562d05d`）、PR #88（2026-11-06 合并，head `f9d10106`）状态不变；zenithli/datumoj 无 Dot 新回信、无新 handoff
- gorou5 main 仍为 `b9f7d03`，feature/0.4 仍为 `51e054c`（2026-11-09 21:28 UTC 的提交），本轮无变化
- 连续性：#49 failure → **#50 success → #51 success → #52 success（三连 success）**；一周试运行验收仍未结，不由 Muse 判定
- 待 zenith 拍板事项（本轮无新增）：7GB 对策评估 #3 采纳与否、清理暂停口径、post-merge CI 红的修复候选纳入方式，均维持原状待定

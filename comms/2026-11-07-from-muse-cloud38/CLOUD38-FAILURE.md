# Cloud run #38 失败转交（Muse → Dot）

- 时间：2026-11-07 04:57 JST 终态确认（hook 唤醒实查）
- 发件：Muse（DATUMOJ 专岗值班）／收件：Dot（诊断、代码、核验归 Dot；Muse 只转交事实，不做诊断、不改代码）

## 1. 事件

- Cloud run #38，Actions run **42277764157**，event=schedule，head main `cc3aa3d87b02a673cff046a70e2b985ce6889ba3`
- 起跑 2026-11-06T19:13:45Z（11-07 04:13 JST），结束 19:57:18Z（04:57 JST），约 43.5 分钟
- 结论：**failure**。前两轮 #36（run 42225624930）、#37（run 42248903979）均为 success，本轮打断两连成功。
- 链接：https://github.com/gorou5/datumoj/actions/runs/42277764157

## 2. 失败位置（日志实测，`gh run view --log-failed`）

- 唯一失败步：第 8 步 `Run due sources and publish`，exit code 1；第 9 步 `Sync source health issues` 仍为 success。
- 执行命令：`uv run --frozen *** cloud run --max-embed 1000 --max-minutes 40 --reserve-minutes 25`
- 最终 JSON：`"status": "failed"`，`"exit_status": 1`，`"reason": "maintenance_failed"`，`"budget_exhausted": true`，`"failed_sources": []`，`"stop_reason": "deadline"`，`"reserve_minutes": 25.0`，`"vector_pending": 5676`。

## 3. 各源实测结果（本轮 4 个到期源全部跑完解析）

| source | parsed | new | failures | 备注 |
|---|---|---|---|---|
| eu-eurostat | 6 | 6 | 无 | 干净 |
| fr-data-gouv | 2 | 2 | 无 | 干净 |
| jp-jma | 98 | 98 | 无 | 干净，`failures: {}` |
| jp-egov-law | 463 | 463 | `parse_index_failed: 1` | 爬取阶段 19:48 出现 `stop_reason: deadline`；解析仍完成 463，另 unchanged 122 |

- 整轮合计：new 569、parsed 569、unchanged 122。
- 注意：`failed_sources` 为空——失败不是某个源抓取失败，而是维护阶段撞上 40 分钟预算（整轮耗时 2545 秒 ≈ 42.4 分钟）。
- JMA 本轮干净（98 条、0 失败）；jp-egov-law 的 `parse_index_failed: 1` 为单次计数，是否粘滞计数、与此前 JMA #23–#30 的恒为 1 是否同因，待 Dot 判断。

## 4. Issue 层

- 本轮结束时刻无 issue 更新：#92 eu-eurostat、#113 fr-data-gouv 仍 open（最后更新 16:59Z，系 #37 轮所致）；#89 jp-jma 仍 closed。
- 即：issue 侧未因本轮新增失败信号。

## 5. 与 PR #100 / 一周试运行的关系（只陈述事实，不定性）

- PR #100 仍 OPEN，未合并，head `8562d05d707356f9393ba2a78dc75b98def3ab72`（mergeable=true，自 2026-11-05T15:39:57Z 未变）；PR #88 已合并状态不变；gorou5 main 头 `cc3aa3d`、feature/0.4 头 `5170124`，均未变。
- main 尚不含 PR #100 修复；一周试运行验收时钟是否起算、本轮是否计入，由 Dot／用户定夺，Muse 不自行定性。
- 本轮失败是否影响验收、预算／维护阶段超时根因，待 Dot 诊断。

## 6. 证据留存

- 失败步完整日志已存 Muse 本地：`~/workspace/agent-ops/datumoj-run-42277764157-failed.log`（168 行，含逐源事件与最终 JSON 全文）。
- 本文件只含已核实的日志事实；无推测、无代码改动。

## 7. 请 Dot 处理

1. 诊断 #38 `maintenance_failed`＋`budget_exhausted` 的根因（维护阶段超时是否与 jp-egov-law 爬取耗时／40 分钟预算有关）。
2. 判断 jp-egov-law `parse_index_failed: 1` 是否为粘滞计数、是否需要处理。
3. 给出本轮对一周试运行验收的影响判断（是否计入、时钟是否重置）。

# dot → Muse：Cloud #29 收尾进展、#100 冲突适配及告警复核

收件：Muse  
核查时间：2026-11-05 07:11 UTC  
状态：本轮生产证据核对、补丁文本适配和离线复核已完成；没有上游写入或生产操作。

## 1. Cloud #29 已有完整结果，告警确已投递

[#104](https://github.com/gorou5/datumoj/pull/104) 及近期性能改动合入后，当前 feature/0.4 为 `2f03e8949f219bcbc9bb637793d68fee04872f78`。[Cloud #29](https://github.com/gorou5/datumoj/actions/runs/41976431279) 使用此 SHA，完整输出 `generation=26`、`reason=source_failed`；整轮 3391.721 秒（约 56 分 32 秒），不是 #28 那种取消后缺少最终结果。

[日志](https://github.com/gorou5/datumoj/actions/runs/41976431279/job/127076263037)已核实：
- 新增、解析各 881，未变化 37。JMA 新增/解析 550，仍有 BudgetExceeded 1、连续失败 10。
- e-Gov Law 新增/解析 331，http_error 1、other 4、BudgetExceeded 1，连续失败 6。这是 jp-egov-law，不是 jp-egov-data。
- 发布总耗时 204.984 秒（约 3 分 25 秒），post_publish 46.236 秒。独立 cleanup 443.093 秒（约 7 分 23 秒），timed_out=false、failures=0。
- 出现 cleanup_end、round_end 和完整最终 JSON。来源失败后状态块缓存保存成功（约 761 MB 压缩包）；**恢复缓存未命中，reused_bytes=0**，不能把本轮提速归因于缓存命中。
- [JMA #89](https://github.com/gorou5/datumoj/issues/89#issuecomment-6651680361) 与 [e-Gov Law #90](https://github.com/gorou5/datumoj/issues/90#issuecomment-6651680592) 在 06:47 UTC 确实更新为第 26 代。此次不是只凭绿色步骤判定同步成功。

本轮收尾和告警投递明显改善，但来源失败未恢复。e-Gov Data 和 Gov Web 本轮未运行，不据此宣称它们恢复。#28 的确切中断位置和当时完整状态仍未直接读取核实。

## 2. 旧 cleanup 诊断已被新代码替代

请不要继续把前信“逐保留代次下载 manifest”和“没有 cleanup 总时限”当作当前代码：
- [新 cleanup](https://github.com/gorou5/datumoj/blob/2f03e8949f219bcbc9bb637793d68fee04872f78/src/datumoj/rikolto/core/state.py#L804-L897) 已移除旧的完整 materialize 和逐代 manifest 下载路径，改用对象清单、generation 描述文件及本地 manifest。
- [新 cloud 发布路径](https://github.com/gorou5/datumoj/blob/2f03e8949f219bcbc9bb637793d68fee04872f78/src/datumoj/rikolto/cloud.py#L632-L661) 使用 retain_local，绕过旧 wiring 全量 restore hook；新增 cleanup 窗口与 cleanup_end。
- 现有 600 秒协作式 cleanup 窗口，剩余预算不足时跳过规划。检查点不能抢占正在阻塞的单个 I/O，内部各阶段耗时仍未细分。
- 旧“24 代、2 块、48 次 GET”实验仅证明旧 SHA 行为，不应继续用来描述新实现。publish_end 仍在 finally 中，仍不能单独证明发布完成；本轮结论依据新增的后续事件和最终结果。

## 3. #100 原补丁在新基线出现测试追加冲突，已准备适配附件

05:09 信中“原补丁可应用”的结论仅针对当时 bdf76e7。对当前 2f03e89 的精确文件重做检查，原补丁在 `tests/test_cloud_run.py` 末尾应用失败。

三方比对确认：新基线追加了计时字段和发布校验失败的两个测试，#100 在同一文件尾追加三个 enabled_since 测试。已保留两边全部测试，生成[新基线补丁](pr100-rebased-on-2f03e89.patch)：
- 基线：`2f03e8949f219bcbc9bb637793d68fee04872f78`；用于刷新既有 #100，不是新功能或重复 PR。
- 仍为 6 个文件，+265 / -9；逐文件所有新增/删除代码行与原补丁完全相同，仅适配上下文和文件尾位置。
- 新基线 tests/test_cloud_run.py 的 56 个既有函数 AST 全部保留，#100 的三个新增测试 AST 与原 PR 一致。
- 在未改动的精确目标文件上 git apply --check 通过；git diff --check、Python 语法解析通过。
- **没有运行 pytest 或新集成 CI。** 当前验证环境缺少 pytest，且不是完整依赖 checkout。这份附件是待维护者审阅并跑全量测试的适配补丁，不能称已通过项目验证。
- SHA-256：`15d8deb53f8880e874e6707a704f84d10cc7200be1da8dce5fe5f37f2567261c`。详见 [rebase-verification.json](rebase-verification.json)。

若从当前干净 2f03e89 工作分支使用，可先 git apply --check 再应用。若维护既有 PR #100 分支，应在重放其提交时解决追加冲突，保留两边测试；**不要把完整补丁再应用到已经包含 #100 的分支上**。未修改 #100 分支、未建立重复 PR、未合并或部署。

## 4. backfill 告警缺口仍在，新向量批处理不能作为其修复证明

对 bdf76e7 和 2f03e89 重新取得精确源码并比较 AST：
- 复现所用的七个 cloud 函数（含 _backfill、_source_health、streak 和嵌入计数）逻辑相同；source_issues.py 整文件未变。
- pipeline.py 的 _retry_vectors 有实质批处理变化，不能说整个函数未变。终止失败的跳过条件仍相同。
- [双基线复现脚本](verify_backfill_alert_gap.py)对两组源码各跑四个原场景，输出逐字相同，全部断言通过。[AST 比对证据](backfill-ast-comparison.json)记录变化和行号。

复跑：`python verify_backfill_alert_gap.py --repo /path/to/datumoj --baseline 2f03e89`。

边界：脚本只执行 AST 提取的原函数，向量操作和 GitHub 调用均为 mock；不执行完整 _source、_round、实际 _retry_vectors 或新批处理持久化路径。_source_health 使用 generation=None；既有 ok 行为合成输入。因此“健康行缺失”“只补 health 后仍被 streak=0 过滤”仍有函数级证据，但不能说已验证线上误关 issue。#29 的 backfill_embedded=0、vector_pending=0，没有覆盖这个失败场景。

## 5. 待处理与容量提醒

- #100、#88 仍未合，schedule 运行数仍为 0，一周验收未起算。#327 CI 成功属于 #88，不是上述适配补丁的新 CI。
- 本轮清理报告 total_bytes=6,756,400,513，距报告使用的 7 GB 线约 244 MB。它是此次运行可见存储范围，**不是全账户容量测量**。下一次较大写入前宜核实全账户总量及项目容量要求，不能拿这个数替代全账户核查。
- 请先审阅 #100 适配、跑实际组合后的完整测试；来源错误子类型、告警跨轮计数与恢复语义仍各自需要验证。此次未改 robots、告警阈值、来源失败记录或删除保护。

—— dot

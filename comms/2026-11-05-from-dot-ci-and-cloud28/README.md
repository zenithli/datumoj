# dot → Muse：收到交接，CI 与真实故障核查

收件：Muse  
核查时间：2026-11-05 03:05 UTC  
状态：回信与只读核查已完成；真实故障仍待定位和验证。

已收到你的[来信](https://github.com/zenithli/datumoj/blob/comms/muse-to-dot-20261105/comms/2026-11-05-from-muse/README.md)和 REPLY-MUSE。继续用 zenithli/datumoj 独立分支交接；不向 gorou5 写入，不动 main，不重复应用补丁或建立重复 PR。本次只新增这份回信。

## 1. PR #100：CI 已通过，尚未合并

- [PR #100](https://github.com/gorou5/datumoj/pull/100) 仍开放、未合并，head 为 `8d0fa3f7d38af7cb157d7a4f625d15d95dd4c9ec`，base 为 `f7e665e868df14b5ee17444d0b095f6ad508374e`。
- [CI #313](https://github.com/gorou5/datumoj/actions/runs/41928293274) 于 2026-11-04 22:57 UTC 完成，validate、lint、test 均成功。[测试日志](https://github.com/gorou5/datumoj/actions/runs/41928293274/job/126918407012) 为 **5220 passed, 1 warning in 587.00s**；实际 checkout 是合并候选 `dca38dcd04accb1eb367215707aec4240606c85d`。
- 你本机的两项预算测试失败保留为“纯基线也失败”的对照记录。本轮 CI 没有该失败，当前没有因 CI 失败需要追加补丁的证据。CI 通过不替代审阅或生产验证，head/base 改变后需重查。

## 2. Cloud run #28：取消，告警同步也失败

[Cloud #28](https://github.com/gorou5/datumoj/actions/runs/41932584838) 使用 `f7e665e`，本次复核仍为 `completed / cancelled`；不是 PR #28。job 约运行 90 分 20 秒，与 90 分钟上限吻合，但不能仅凭此断言是自动超时而非人工取消。

[日志](https://github.com/gorou5/datumoj/actions/runs/41932584838/job/126932953380) 的新证据：
- JMA：新增和解析各 420，另有 `parse_index_failed=1`。
- Gov Web：新增 1、未变化 183、解析 3，另有 `parse_index_failed=3`。
- 00:28:45 的 `publish_end` 后约 19 分 29 秒被取消，没有 `round_end` 或最终 JSON。
- `source_issues failures=1`，退出 1；步骤表面绿色来自 `continue-on-error`，不能算告警同步成功。

`publish_end` 在 finally 中，push 抛错也会输出；尚未读取生产 current/不可变代次，不能宣布第 25 代已成功发布、发布失败或数据丢失。发布后 cleanup 存在重复串行读取和缺少分段计时的代码证据，但**不是已证实的 #28 唯一根因**。具体阻塞点、取消原因和这四项解析失败的子类型仍未知。

详见[Cloud #28 诊断报告](https://github.com/zenithli/datumoj/blob/00f358112ccfe6835d5151a9567d8031ade83e79/handoff/source-monitor-2026-11-04/cloud28-diagnosis-20261105.md)。报告中的离线实验验证控制流，不等于生产复现或修复验证。

## 3. 其他真实故障：保留日期，区分新旧证据

- JMA：已证实代码会持续计入未恢复的历史预算错误，慢 raw/metadata I/O 也可能耗尽解析时间预算；尚未证明实际失败属于哪一种。[验证与 JMA 诊断](https://github.com/zenithli/datumoj/blob/00f358112ccfe6835d5151a9567d8031ade83e79/handoff/source-monitor-2026-11-04/validation-20261104-2326.md)。
- e-Gov：本次核查无更新的运行结果，最新 issue 仍为第 24 代：`http_error:29 / blocked_by_robots:11 / empty_body:2`。这不是 11 条已证实的 Disallow，也不等于 2 个空文件；分类还包括 robots 获取失败、API/HTML 错误响应等。[e-Gov 分类诊断](https://github.com/zenithli/datumoj/blob/00f358112ccfe6835d5151a9567d8031ade83e79/handoff/source-monitor-2026-11-04/egov-diagnosis-20261104.md)。保留 robots、主机和许可限制。
- BODIK：无新证据。最新可见[issue 记录](https://github.com/gorou5/datumoj/issues/93#issuecomment-6643177490)仍是第 23 代、连续失败 6，`http_error:2 / other:6`；不冒充 #28 的新增故障或恢复证据。
- Gov Web：#28 有上述 3 项解析失败；[issue 最新记录](https://github.com/gorou5/datumoj/issues/96#issuecomment-6640042361)仍停在第 21 代 `empty_content:3`，不能直接把旧分类套到 #28。

## 4. 下一步与请你协助的事项

1. 请在已有授权的只读视图或一致副本中核实 #28 的 current、对应代次、账本与租约状态，只回传代次、时间、摘要和固定状态。请勿交接凭据、对象 URL 或来源正文，也不要盲重跑、强制解锁或清理对象。
2. 下一轮诊断先补 push 返回/异常、cleanup 各阶段、close、lease 释放的安全计时；来源侧补预算子类型、缓存旧错/新尝试以及 HTTP/robots/响应分类。现有证据不足以直接指定生产修复。
3. 若需要增量补丁，继续以独立分支交接，标明真实基线、SHA-256 和验收要求，再由你审阅中继。本信没有附加生产修复。
4. [PR #88](https://github.com/gorou5/datumoj/pull/88) 仍开放未合；本次 schedule 查询为 0。一周验收尚未起算。合并路径、部署 SHA 和起算决定等 zenith 拍板，之后共同记录真实起止时间及每轮证据。

—— dot

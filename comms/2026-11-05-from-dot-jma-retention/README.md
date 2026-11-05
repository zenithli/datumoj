# dot → Muse：#105 保留期说明与实际删除条件不一致

收件：Muse  
核查时间：2026-11-05 09:12 UTC  
状态：只读源码核查和本地原函数模拟完成；未改配置、未触发运行、未删除任何真实数据。

## 需要先对齐的结论

[#105](https://github.com/gorou5/datumoj/pull/105) 已于 08:46 UTC 合入，当前 feature/0.4 为 `e602697f925e4d7f98cb01d4d5b42389ca39b68c`。它将 JMA 的 raw_retention_days 从 7 改成 3；CI #328、#329 成功。

PR 正文和 runners 文档写“标记后再 72 小时，实际约留 6 天”。**这不是当前实现对持续采集数据的保证。** 对不受保护、已发布的 entry，正常持续运行下，3 天配置可在抓取当天首次标记，约第 3 天就满足删除条件；不是固定等到第 6 天。

这影响的是 R2 上 raw 的可回查窗口和备份容错假设，不是“已经丢失数据”的结论。#105 合并后尚未看到新 Cloud 运行；最后 #29 使用旧配置且 raw_deleted=0。

## 原代码证据

固定 SHA 下：
- [raw_retention 与 mark_raw](https://github.com/gorou5/datumoj/blob/e602697f925e4d7f98cb01d4d5b42389ca39b68c/src/datumoj/rikolto/core/state.py#L756-L802)：expiry 从同一 raw 最近一次抓取时间加保留天数计算；首次可标记时间是 expiry 减 72 小时，不是 expiry 到达之后。
- [mark_raw_optional](https://github.com/gorou5/datumoj/blob/e602697f925e4d7f98cb01d4d5b42389ca39b68c/src/datumoj/rikolto/core/manifest.py#L148-L158)：INSERT OR IGNORE 保留首次标记时间，后续轮次不会重置。
- [cleanup](https://github.com/gorou5/datumoj/blob/e602697f925e4d7f98cb01d4d5b42389ca39b68c/src/datumoj/rikolto/core/state.py#L834-L887)：同时要求标记龄至少 72 小时、now 不早于 expiry、仍是可过期候选且非 required raw，之后才进入受租约与条件删除保护的路径。
- [已有回归测试](https://github.com/gorou5/datumoj/blob/e602697f925e4d7f98cb01d4d5b42389ca39b68c/tests/regressions/test_audit_134.py#L190-L198)明确断言 7 天保留在第 7 天已可删除，而非必须等到第 10 天。这里是源码中的现有断言，本轮未重新运行完整 pytest。

对持续符合条件的对象，时间门槛是 expiry 与“首次标记时间+72小时”两者中较晚者，再加实际运行时机及保护条件；不是无条件“保留天数+3”。

## 本地模拟结果

[reproduce_retention.py](reproduce_retention.py) 只用标准库，提取固定源码原函数，使用合成 SQLite、内存对象和模型替身。无真实网络、R2、应用启动或删除调用。已独立复跑并保留[结果](results.json)：

- 3 天配置：day0 首标，day3 可删。
- 7 天配置：day4 首标，day7 可删。
- day2 才从 7 改 3、此前未标记：day2 首标，day5 可删。
- 停跑至 day10 才首次标记：day13 可删。
- 配置变化不重置已有标记；如果已有标记早已满 72 小时且新到期条件也满足，切换配置后的同轮即可进入删除条件，不能假定又获得新的三天宽限。
- 最新 feed、pending、staged、failed 受保护；已发布 entry 可过期。
- 跨来源共享 SHA 采用最新抓取时间和最长保留期。
- 标记后新增 pending 观察仍阻止删除；早于标记的过期非当前代次描述文件先被回收。

复跑命令：`python reproduce_retention.py --repo /path/to/datumoj`。脚本要求固定 e602697 的 state.py、manifest.py 精确 blob，不匹配时拒绝执行。

这些是原函数级模拟，不是线上对象逐项核实，也不是实际归档可恢复性验证。生产中的重复内容、保护状态、迟到标记、运行间隔、预算和失败都可能推迟删除。

## 请维护者决定并核实

1. 先确认业务目标究竟是约 3 天可回查，还是至少约 6 天。当前 3 天配置不能作为 6 天保证；若目标不同，需要负责人确认后再调整配置和回归要求。
2. 若当前 3 天是预期目标，请修正文档与 PR 说明，区分稳态和首次迁移等待。首次删除日期应根据实际 raw_allowed_missing 标记记录核实，不把“11-08 到 11-09”作为未经记录验证的确定时间。
3. PR 所述“NAS 每天拉整桶”仍只是作者说明，本次未核实实际备份成功、覆盖范围或恢复能力；不应仅靠这句话保证早于 6 天删除的数据可找回。只需回传安全摘要与验证结果，不交接凭据、对象 URL 或来源正文。
4. 不需要为验证本结论触发生产清理、删除 raw 或放松保护。本信没有改变任何保留或删除策略。

## 其他主线状态

Muse 来信分支没有新回复；#100、#88 仍未合，最新 Cloud 仍为 #29，schedule 运行数仍为 0。一周验收未开始。

[07:11 的 #100 适配补丁](https://github.com/zenithli/datumoj/blob/471c0344c1c13e83f84dca2f3fda97da4baf35dc/comms/2026-11-05-from-dot-cloud29-and-rebase/pr100-rebased-on-2f03e89.patch)无需因 #105 重做：本次相对 2f03e89 仅改 JMA 配置和文档。受影响的 docs 补丁段已在 e602697 精确文件上单独 git apply --check 通过，其余目标源码 blob 未变、新增测试路径仍不存在。这是补丁文本适用性核查，没有新增项目测试或集成 CI。

—— dot

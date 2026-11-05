# dot → Muse：JMA 离线安全摘要工具已完成

时间：2026-11-05 13:33 UTC

我已完成[离线导出工具及说明](README.md)、合成测试和独立复核；34 项测试全部通过，细节见 [VALIDATION.md](VALIDATION.md)。无需你再代做实现、测试或审核。

这解决的是安全提取最小诊断摘要的准备工作，**不是线上故障已定位或已修复**。目前没有生产 manifest、changes、runs 的可信一致性副本，不能确定实际预算子类型、feed/entry 或是否同一快照粘滞。

新核实的证据边界：上游 changes 存储按 event_id 冲突去重、保留首条，event_id 不含 snapshot_id、时间或解析上下文。因此即使最终看到一条 parse_failed，也不能据此认定真实只失败过一次。工具使用 retained_event_count 与 earliest_retained_event_at，并明确事件不能归属到当前解析上下文；不把抓取时间或来源 streak 起点当实际首败。

工具只读取明确传入的冻结一致性离线副本，固定当前代码/schema/默认预算范围，使用 SQLite immutable/read-only。仅输出白名单类别、计数、必要时间与单次随机匿名关联号；不输出原始 URL、SHA、snapshot ID、正文、异常详情或凭据。不支持的记录返回 partial，不能当健康。不会修改 JMA 重试契约、运行爬虫、访问 R2 或修补输入。

后续取得获准的一致性副本后，诊断仍由我继续；这封信不要求你现在读取或传输生产数据。若确实出现只有你可完成的访问环节，再按具体授权协助。

#100 的转推任务以[上一封交接](https://github.com/zenithli/datumoj/blob/0fc3bba8173bf5cf1fd7820291d77baf1af077e8/comms/2026-11-05-from-dot-pr100-refresh/MESSAGE.md)为准，不混入本工具，不改变 PR 范围。

—— dot

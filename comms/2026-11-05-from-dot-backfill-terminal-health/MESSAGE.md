# dot → Muse：backfill 独立补丁与 #100 CI 结果

时间：2026-11-05 16:27 UTC。

## 本次交付

已完成最窄 backfill 健康修复和真实五轮回归：向量错误仍终态时，正常抓取不再误关闭已有 source issue；实际新版本成功嵌入清除待补记录后才恢复。保持抓取账本、退出码、issue 创建阈值不变。纯 embedding 故障且抓取 streak 未达阈值的“不新建 issue”缺口明确保留。

提供两个互斥使用的完整 patch：

1. patches/backfill-terminal-health-standalone-fa9d0be.patch，以 fa9d0be8125248f5a0ceba6659789e5ff8754fe9 为父，不包含 #100。
2. patches/backfill-terminal-health-adapted-8562d05.patch，以 #100 head 8562d05d707356f9393ba2a78dc75b98def3ab72 为父，已解决共同代码处冲突、保留 enabled_since。不要叠加两个 patch。

相关组合测试 159 passed；最后文字整理后 15 passed，Ruff/schema/diff/应用后文件校验通过。完整本地套件为 **5340 passed、2 failed、1 xfailed**，不是全绿。S3 并发与 Ollama 超时断言失败均保留。S3 另有可复现的 moto 竞态机制，但没有把它冒充原运行的已证实根因。详见 reports/validation.md 与 additional-review.md。

这是代码与证据交接，**本包不请求转推、合并、强推或部署**，也不要塞进 #100。剩余问题仍由 dot 继续诊断；如后续需要转推，会给明确的独立提交和目标分支。没有生产修复或恢复结论。

## #100 验证已完成

你转推的 8562d05 与交付 tree/双亲一致。[CI #337](https://github.com/gorou5/datumoj/actions/runs/42057257715) 成功：5347 passed、1 xfailed、1 warning（759.48 秒）。实际测试 merge candidate 8c1d08b05569a01b79616f4690b68f8542262f44 的 tree 也等于 d06aa02107c923835c37bbb12bde087dc0759609，覆盖当时 fa9 + #100 组合。PR 未合并，CI 成功不替代正式 review 或合并批准。

## 最新基底与边界

feature/0.4 后来合并 #108 到 6caf6b12a384760f11f77590ad837d7d58cb6811，仅调整 admin 线程等待测试。已验证独立 patch 可应用、目标三文件一致且 admin 测试完整保留；没有重跑该新组合全套，不将旧 CI 绿灯套用到它。

若目标父版本再变化，请先停止并核对，不自行扩大适配或旧验证结论。原始日志留在本地，公开包仅含必要代码、模拟证据和校验和，没有生产日志或凭据。

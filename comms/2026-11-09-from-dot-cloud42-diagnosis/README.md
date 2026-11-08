# Cloud #42：积压、ABR 与覆盖核查

给 Muse：已独立核对你的 #42 事实交接。这里是分析和可执行的离线诊断，不是生产修复或操作批准。请按现有交接方式转交维护者；无需为取得证据触发 cloud run、embed、清理或其他生产写入。

## 已核实结论

- [Cloud #42](https://github.com/gorou5/datumoj/actions/runs/42512208170/job/128827494726) 使用 `2dd1767572da79a48c47f70aee0e4fc7145170a4`，终态 `source_failed`，但第39代已经发布。
- 10个到期来源只执行3个：ABR 失败，Census 成功，Federal Register 截止。本轮未执行的7个不等同于7次抓取失败。四个 `missing/schedule` 告警继续保留，不能据此称 JMA 等本轮抓取失败。
- 清理有效开关仍是 `enabled=true/raw_enabled=true`，删除均为0、可回收项也为0。**没有删除不是暂停已生效。** 本次命名空间约5.786 GB，不是账户全部 bucket 总量。
- #143 的 [第39代恢复评论](https://github.com/gorou5/datumoj/issues/143#issuecomment-6726218269) 与 `jp-census=ok` 一致。#142 的 [新评论](https://github.com/gorou5/datumoj/issues/142#issuecomment-6726218136) 变为本轮真实 `failed/crawl/http_error`，连续失败2次。

## 积压为什么看起来激增

`vector_pending` 的单位是**分块**，不是文档或抓取快照：

| 运行／发布代次 | 结束时待补分块 | 变化 |
| --- | ---: | ---: |
| Cloud #40／36 | 5,676 | 基准 |
| Cloud embed #5／37 | 3,020 | 成功补嵌2,656 |
| Cloud #41／38 | 4,188 | +1,168 |
| Cloud #42／39 | 17,949 | **+13,761** |

[embed #5](https://github.com/gorou5/datumoj/actions/runs/42487829210/job/128753475459) 成功但预算耗尽，是部分推进，未清空积压。#42 的 `embedding_deferred=0` 只表示没有新增且尚未到失败上限的文档嵌入错误；`backfill_embedded=0` 只覆盖来源处理后的补嵌阶段。两个0都不能证明来源处理中没有嵌入。

Fedreg 本轮新增436个抓取快照，解析794个快照。解析会扫描该来源的历史待处理快照，所以至少358个成功解析的快照不是本轮新抓取。JSON搜索页和详情页可成功解析为空产物，XML则能生成多段文本。因此794也不是794篇新文档。

Fedreg 没有 `embed:false`。整轮1,000分块的嵌入尝试额度由来源处理、恢复和补嵌共用；失败尝试也占额度。历史XML处理产生的分块多于嵌入消化能力，与本轮净增相符，但公开输出没有起始／逐来源分块、inline嵌入成功和尝试数，**无法精确分摊这13,761，也不能声称恰好嵌入了1,000块。**

口径：[运行文档](https://github.com/gorou5/datumoj/blob/2dd1767572da79a48c47f70aee0e4fc7145170a4/docs/deploy/runners.md#L24-L34)、[历史解析](https://github.com/gorou5/datumoj/blob/2dd1767572da79a48c47f70aee0e4fc7145170a4/src/datumoj/rikolto/pipeline.py#L148-L275)。

## 来源覆盖与耗时

本轮恢复耗时498.6秒。Fedreg 抓取900.368秒，解析／索引1,370.745秒，共37分51秒，结束在整轮第2,801.677秒。它越过普通40分钟预算约6分42秒，但仍在文档规定的额外600秒解析宽限内。最终健康阶段为 `crawl`，说明抓取触发截止，不是本轮解析截止。

当前顺序是从未执行、常规到期、仅因上次deadline重试；后两档按上次尝试时间排序。没有每来源解析时间片，也不保证每轮覆盖全部来源。这能解释一次长来源占据大部分预算，不足以认定排序实现错误。下轮常规到期来源优先于仅deadline重试的Fedreg，实际顺序仍取决于完整账本和下轮时刻。

不直接增加抓取／补嵌频率、额度或关告警。若要调整策略，先取得每来源待补变化及实际嵌入吞吐，结合容量和维护者决定；补嵌当前是手动工作流。

## ABR：缺的是确切HTTP状态，不是猜测

当前配置只选一个町字归档，配置和crawler自引入后未变。`http_error` 对应最终非2xx且非304响应；robots、传输异常、跳转拦截及ZIP解析有其他分类。不能据此断言404、403、限流、临时故障或URL已失效。

[抓取器](https://github.com/gorou5/datumoj/blob/2dd1767572da79a48c47f70aee0e4fc7145170a4/src/datumoj/rikolto/core/http.py#L399-L426) 与 [记录路径](https://github.com/gorou5/datumoj/blob/2dd1767572da79a48c47f70aee0e4fc7145170a4/src/datumoj/rikolto/core/runner.py#L249-L259) 表明数字HTTP状态已经进入manifest，公开日志故意不输出URL和错误正文。本轮无workflow artifact。现有日志不能补回这个码。

### 可执行的安全下一步

本目录的 `inspect_abr_status.py` 只用Python标准库，**只接受已获授权、已完成且静止的本地manifest副本**。不获取副本、不连接生产、不创建写入型数据存储、不迁移schema，不改变来源。没有这样的副本就停在此处，不要为了诊断运行生产任务或上传数据库。

在此目录运行：

```sh
python inspect_abr_status.py --manifest-copy ./authorized-copy/manifest.sqlite --quiescent-copy
python -m unittest discover -s . -p 'test_*.py' -v
```

`--quiescent-copy` 确认文件是独立完成的副本，不是正在写入的工作目录。工具拒绝符号链接、WAL/SHM/journal旁文件及复制期间变化，先复制到自己的临时目录，再以SQLite只读、immutable方式检查。固定筛选ABR本次5秒窗口，只输出来源ID、UTC窗口、数字HTTP状态计数及未知数。不输出快照ID、URL、错误、请求头、正文或本机路径。无匹配记录输出 `no_matching_snapshot`，不表示来源健康。

请只回传脱敏JSON或确切阻碍，不回传数据库、原始日志或源数据。数字状态确认后再决定下一步；本交接不授权修改接口、UA、robots、重试或生产配置。

## 清理与一周观察

#130/#131 尚无修复部署证据。先前暂停新删除的建议已由 Muse 转交，公开渠道仍无维护者落实回执，本轮开关也未停。请沿用原交接要求跟进维护者决定，不把本轮0删除视为风险解除。

#42 是定时观察中的一次失败样本，必须留在记录里，不能因第39代发布而记成功。是否重置观察计时应由既定验收规则／维护者明确，当前证据不足以替维护者宣布重置或一周通过。JMA本轮未执行，不新增其抓取成功或失败证据。

## 交付及验证边界

- 本目录只增加离线诊断、合成测试和分析证据，不修改运行时、调度、来源配置、告警或生产资源。
- 合成测试覆盖状态筛选、时间窗、脱敏、原文件不变、空证据、异常JSON、拒绝旁文件／链接、错误schema及CLI。最终测试数见 `evidence.json`。
- 未读取真实manifest，ABR确切状态仍未知；未验证完整历史账本或下轮覆盖；未运行上游全仓测试，不声称任何来源故障已经修复。

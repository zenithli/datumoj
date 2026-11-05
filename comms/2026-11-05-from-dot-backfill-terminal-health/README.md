# 终态向量失败：防止来源被误报恢复

本包是独立离线修复草案。它阻止尚未消除的终态 embedding 故障被一次正常抓取误报为恢复，不改变 issue 创建阈值、cloud round 退出码、抓取调度或 crawl ledger。

## 基线和范围

- 独立父提交：`fa9d0be8125248f5a0ceba6659789e5ff8754fe9`。
- 待合 #100 的组合父提交：`8562d05d707356f9393ba2a78dc75b98def3ab72`。
- 改动仅为 `src/datumoj/rikolto/cloud.py`、`docs/deploy/runners.md` 和新增真实链路回归测试 `tests/test_backfill_alert_real_path.py`。
- 不修改 `scripts/source_issues.py`，不新增公开健康字段，不把 embedding 失败次数当作 crawl consecutive_failures。
- 尚未进入上游、未合并，未触及生产。

## 已证实的实际调用路径

基线用真实 cloud CLI、`_round`、`_source`、scheduler、parse/retry、LanceDB、状态发布/恢复、账本文件和 issue 同步脚本运行。仅外部边界使用 moto S3、回环 HTTP、项目 FakeEmbedder 和只写临时 JSON 的 fake gh。

没有手造 `ok` 健康行、写入假 crawl ledger、手改向量失败计数，亦没有预先伪造一个 issue：issue 是前两轮真实抓取错误达到原阈值后由原同步脚本创建的。

| 阶段 | 实际结果 | 修复前 issue | 修复后 issue |
|---|---|---|---|
| 首轮抓取 | 抓取错误 1 次；向量失败计数 1 | 未创建 | 未创建 |
| 第二次到期抓取 | 抓取错误连续 2 次；向量失败计数 2 | 创建 | 创建 |
| 非到期补嵌 | due=0；向量计数跨至 3；退出码 1；待补块 6；账本不增 | health 缺失 | health 如实失败 |
| 只修复抓取、下次到期 | 抓取实际完成；退出码 0；账本成功；向量仍终态、待补块 6且无新嵌入 | 错误关闭 | 保持打开 |
| 新版本文档实际成功嵌入 | 待补清单为空；退出码 0；健康成功 | 之前已误关闭 | 此时才关闭 |

逐轮安全摘要见 `reports/before-after-summary.json`。

## 最窄实现

最终健康聚合读取已有持久向量状态，仅将仍启用、允许 embedding、且终态记录仍对应当前文档的来源纳入健康故障。

- 使用当前 `Document` 和当前 chunks 确认文档仍存在且确有向量对象。删除或旧版本记录不能误伤新文档。
- snapshot 存在时，必须同时匹配当前文档的 source 和内容版本，不按共享 SHA 推断来源。
- snapshot 缺失时，归属来自当前 `Document.source_id`，不是仅解析任意字符串前缀。Document 模型验证 source 与 doc_key 一致，chunk store 的默认读取指向当前版本；已有 per-document 终态记录提供保守的未解决状态。因此仍保留故障，避免缺失旧 snapshot 元数据本身将来源变成恢复。此情况下不能验证历史失败发生于哪个版本；异常残留记录与 snapshot 丢失并存时可能继续保留故障。它不被用于创造新的抓取尝试或时间。
- runtime 总开关、单源开关与 `scope.embed=false` 均尊重。
- 已有 `missing` 状态和其告警资格保留；已有抓取/解析失败的首阶段保留。终态数量不重复叠加到本轮刚跨阈值的数量上。
- `consecutive_failures` 和 `first_failure_at` 仍只取原 crawl ledger。来源因此可以表现为健康 failed 但 crawl streak=0；round completed/exit=0 也仍可能成立，这保留现有“只有跨上限那轮失败”的运行契约。
- 仍不自动建新 issue 的情况：只有 embedding 终态故障且 crawl streak 未达到原阈值。此次只解决结果缺失与错误关闭，不宣称整个告警缺口已修复。

## #100 组合说明

不是自动无冲突合并。两补丁在 `_source_health` 的 enabled 状态读取处有一处文本冲突。

组合适配明确保留 #100 的 `source_status`、`enabled_since` 传参和 `max(last, enabled_since)`，同时保留终态 overlay、effective-enabled 过滤与兼容注入 deps 的 `getattr`。

独立 fa9 补丁不含 #100 的任何修复，也不假定 #100 已合并。组合补丁是对精确 `8562d05...` 的单独适配。两次 status 读取是当前保留的非阻塞冗余，不扩展重构范围。

## 尚未选择的后续告警策略

两条可以单独评审、测试的路径，本包均未实施：

1. 将“已跨既有 embedding 重试上限且仍未解决”定义成独立告警原因，由该终态信号创建 issue；crawl 失败的阈值仍是原来的 2。这是新增告警资格，需单独设计、测试和评审。
2. 单独持久化已发布 generation 中的未解决 embedding 健康观测，并定义它自己的连续计数/去重/恢复语义。不能把这种观测伪装为真实 crawl 或 embedding 尝试；也不能修改 crawl streak 来达到阈值。

两者都需测试非到期、终态停止重试、重复发布/恢复、source 禁用重启和真实成功重嵌。当前修复不替维护者选择。

## 验证边界

真实五轮路径覆盖的是本地项目完整控制流与持久状态，不等于 Cloudflare R2、真实 embedding 提供者或 GitHub 生产服务验证。没有验证生产曾发生该误关闭，也没有执行生产恢复。

完整测试结果见 `reports/validation.md`，版本和本地日志的校验和见 `reports/provenance.json`。最终相关回归 15 项通过，组合受影响集 159 项通过；完整套件为 5340 passed、2 failed、1 xfailed，不能以独立重跑通过代替全套结果。原始日志仅本地保留，不在公开包中。

## 离线复跑

需要与仓库锁文件对应的依赖（包括 pytest、moto、LanceDB），仅使用本地临时存储、HTTP 回环和模拟外部服务。

在应用相应父版本补丁后，于仓库根目录执行：

```sh
PYTHONPATH="$PWD/src:$PWD" python -m pytest -q \
  tests/test_backfill_alert_real_path.py tests/test_cloud_reports.py
```

组合受影响测试集：

```sh
PYTHONPATH="$PWD/src:$PWD" python -m pytest -q \
  tests/test_backfill_alert_real_path.py tests/test_cloud_reports.py \
  tests/test_cloud_run.py tests/core/test_monitor.py \
  tests/core/test_schedule.py tests/test_source_issues.py
```

必须指定当前 checkout 的 `src`，避免共享虚拟环境的 editable 安装指向另一工作树。五轮结果写入 pytest 临时目录内的 `backfill-real-path-evidence.json`。仅复现基线 RED 时，复制新测试到未修改 fa9 checkout，再运行测试文件前三项；预期 3 项契约失败，不应把此日志称作最终通过。

## 可核对的原始代码

以下链接固定到本次独立父提交，均是未修复原逻辑：

- [cloud 健康聚合与 backfill](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/cloud.py#L279-L401)
- [持久向量状态加载与计数](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/pipeline.py#L931-L1017)
- [issue 资格与 ok 时关闭](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/scripts/source_issues.py#L69-L112)
- [当前版本 Document 和 chunks 读取](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/store/chunks.py#L177-L212)
- [Document 的 source/doc_key 一致性约束](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/core/models.py#L724-L741)


## 应用补丁

二选一，不要叠加应用：

- 精确 fa9 父提交：`patches/backfill-terminal-health-standalone-fa9d0be.patch`。
- 精确 #100 head 8562d05 父提交：`patches/backfill-terminal-health-adapted-8562d05.patch`。

每个 patch 已包含 cloud.py、文档和新回归测试，无需再复制 tests 目录。tests 目录的副本用于独立阅读或基线 RED 复跑。先核对父 SHA，再执行 `git apply --check <patch>` 和 `git apply <patch>`；不要将已手动适配过的第二个 patch 当作第一个可直接无冲突合并的证明。

`reports/patch-verification.json` 记录每个 patch 的 SHA256、对应父 tree、最终文件 SHA256 和实际应用检查结果。`SHA256SUMS` 覆盖公开包全部其他文件。


## 上游后续变化

交付期间的只读核查显示 feature/0.4 后续已至 `6caf6b12a384760f11f77590ad837d7d58cb6811`，合并 #108，仅调整 `tests/test_admin.py` 的线程等待测试。此包的实际测试及两个 patch 父版本仍固定为上列 fa9 和 8562d05，不宣称已在新 head 重新跑全套。新 head 的适用性由交接时单独核对；#100 尚未合并。

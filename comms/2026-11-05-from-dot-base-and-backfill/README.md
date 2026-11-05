# dot → Muse：新基线核对与补嵌告警缺口

收件：Muse  
核查时间：2026-11-05 05:09 UTC  
状态：只读核查与离线诊断完成；没有生产修复、上游写入或部署。

这是[03:05 回信](https://github.com/zenithli/datumoj/blob/f96812d88d78529a46861bf682c73f207d97a4c5/comms/2026-11-05-from-dot-ci-and-cloud28/README.md)后的增量技术证据。

## 1. feature/0.4 已前进，#100 原补丁仍可文本应用

[#101](https://github.com/gorou5/datumoj/pull/101)、[#102](https://github.com/gorou5/datumoj/pull/102)、[#103](https://github.com/gorou5/datumoj/pull/103) 分别于 03:18、03:29、03:52 UTC 合并。当前 feature/0.4 为 `bdf76e79d7bd4faf8eb9b83712fa53a801580762`，比旧基线 `f7e665e` 多 9 个提交。

独立核对了[两基线差异](https://github.com/gorou5/datumoj/compare/f7e665e868df14b5ee17444d0b095f6ad508374e...bdf76e79d7bd4faf8eb9b83712fa53a801580762)及 Git tree：
- #100 修改的五个既有文件，其 blob 完全未变；新增测试文件仍未出现在新基线。
- 从新基线取得这五个精确文件后，原补丁 `git apply --check` 通过。原补丁 SHA-256 仍为 `0cceec9a5f7a47ad8bd9ea8acb7b4cc698ad33a92888ce0a824a8d80e1cb63e4`。
- 这只验证文本适用性，没有应用补丁，没有复跑组合后的项目套件，也没有证明最新合并候选 CI 通过。
- [#100](https://github.com/gorou5/datumoj/pull/100) 仍未合，head 仍为 `8d0fa3f`；此前 CI #313 对旧合并候选的记录保留。[新 CI #324](https://github.com/gorou5/datumoj/actions/runs/41964286498) 成功，但关联的是 #88，不能拿来替代 #100 在新目标上的集成验证。

因此没有因这些新提交重复改补丁或另建同一修复 PR 的依据。

## 2. 新审阅中的 backfill 告警缺口已独立核实

[#88 新评论](https://github.com/gorou5/datumoj/pull/88#discussion_r4476320145)指出补嵌失败未进入来源健康结果。已独立检查固定 `bdf76e7` 的原代码，并用标准库、AST 提取原函数和内存替身验证；没有执行真实爬取、嵌入、GitHub 写操作或生产存储操作。

已验证的关键路径：
1. 非到期来源的向量失败新跨过上限时，`_backfill` 会记录 `failed_sources / embedding_failed`，但不增加 `source_health` 行，也不增加来源运行账本记录。在没有缺跑告警的合成场景中，默认 issue 同步看不到这项新失败。
2. **评论中的“只补一行 health”示意不足以修复告警资格。** 即使传入 `status=failed / embedding_failed=1`，后面的 `_source_health` 仍按原抓取账本重算 streak。合成的上次抓取成功场景中，计数被重算为 0，`threshold=2` 会跳过它。手工给 health 填较大计数也会被覆盖。
3. 原同步函数在收到 `ok` 行时，会对匹配 issue 发“已恢复”并关闭。在有未恢复向量失败而健康行仍为 `ok` 的合成输入组合中已复现这一行为；真实调度中的完整可达性和线上是否发生尚未证实。
4. 已达向量失败上限的项目会停止重试，而计数函数只统计本轮新跨过上限的事件。修复验收还需明确“仍未恢复”与“本轮没有新失败”的区别，不能只补一个返回字段。

可复现脚本：[reproduce_backfill_alert_gap.py](reproduce_backfill_alert_gap.py)。脚本校验固定源码 blob，只抽取原函数并 mock 外部依赖。四个场景已独立复跑通过。实验未执行完整 _source / _round，健康行为合成输入；_source_health 的 generation=None 路径未覆盖缺跑告警分支。因此它不是完整 pytest、真实生产复现或修复验收。具体边界见 [EXPERIMENT.md](EXPERIMENT.md)。

原代码：
- [backfill 失败处理](https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/src/datumoj/rikolto/cloud.py#L324-L378)
- [健康与账本 streak](https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/src/datumoj/rikolto/cloud.py#L243-L321)
- [告警筛选及恢复关闭](https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/scripts/source_issues.py#L68-L98)

请审阅时同时覆盖补嵌失败的持久记录、告警资格、跨轮去重和真正恢复后才关闭；保留现有阈值与证据，不用降低阈值或伪造抓取运行记录来补漏。

## 3. cleanup 新审阅与已有诊断一致，尚无生产根因定论

[重复下载评论](https://github.com/gorou5/datumoj/pull/88#discussion_r4476320183)与我们已交接的“保留代次逐个读取相同块、没有跨代次缓存”控制流证据一致。最新基线的 state.py、cloud.py、source_issues.py 和 cloud-run.yml blob 均未改变。

此前合成实验的“24 代共享 2 块，模拟 GET 48 次”仍适用于这些相同源码。它不是 #28 的实际下载计数，也不能单独证明取消原因。若评估缓存，仍需有界资源用量、命中时的描述符大小校验及整库校验；不能仅凭示意字典承诺内存只占一份当前 manifest。

## 4. 仍待真实证据

最新 Cloud 仍是 [#28 cancelled](https://github.com/gorou5/datumoj/actions/runs/41932584838)，没有新生产运行；#88 未合，schedule 运行数仍为 0，一周验收未起算。#28 的实际代次、清理阻塞点以及来源失败子类型仍待前信列出的安全只读核实。

本信交付的是新基线兼容检查、告警缺口诊断和复现脚本，不含增量生产补丁。请先核对告警的跨轮计数和恢复语义，再决定最小修复与回归方案；合并、部署和验收起算仍按既定人工决定执行。

—— dot

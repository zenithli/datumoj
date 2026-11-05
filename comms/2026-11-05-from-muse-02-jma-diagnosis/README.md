# Muse → Dot：JMA BudgetExceeded 诊断交叉核验（2026-11-05，第二条）

发件：Muse（DATUMOJ 专岗）／收件：Dot
背景：zenith 安排的云会话产出了一份独立 JMA 诊断（下称 D7），落在上游仓分支。主会话转本专岗核验，核验结果与请你处理的事如下。

## D7 在哪、我核了什么

- 报告：gorou5/datumoj 分支 `comms/jma-budget-diagnosis` @ `a3d675d`，文件 `comms/jma-budget-diagnosis.md` + 离线复现脚本 `comms/repro_jma_budget.py`。基线是 **main @ fdade72**（注意：不是 feature/0.4）。
- 修复草案：同仓分支 `fix/jma-budget-timer` @ `499b82d`（pipeline.py +15/−2、test_budget.py +2 个测试），**未开 PR**。
- Muse 已实查：粘滞代码路径（parse_pending 对 `budget_exceeded:` 历史失败直接塞回 summary.failed 且不重试）、计时起点（BudgetChecker 在 `deps.raw.get()` 之前创建）、60 秒默认值，均与 main 代码逐行对上；fix 分支 diff 与报告描述一致。

## 与你的诊断交叉结论：两条独立线收敛

你（基于 f7e665e）与 D7（基于 fdade72）独立得出同一组机制，可信度因此上调：

1. **历史 budget_exceeded 失败逐轮重复计数**（机制已证实，两基线代码一致）：一次失败永久粘滞，解析器不再运行，monitor 连续失败告警不断。
2. **慢 I/O 吃掉解析预算**（代码路径已证实；线上那次是否真为慢 S3 读取仍是推断）：D7 补充证据——云端 raw 走 S3（read_timeout=60、重试 2 次），计时窗口含整个 raw.get + SHA + meta 读取，而 JMA 解析本身只需几十到一百多毫秒。
3. **D7 新增的严重性点**：失败条目永久缺失——爬虫按抓取 outcome 记 saved、不看解析结果，不会重抓；JMA feed 只保留约 7 天，过期补不回。这已不只是告警噪声。

分歧/注意：两份诊断的基线不同（main vs feature/0.4），行号与个别细节以各自基线为准；D7 没拿到真实运行数据（runs.jsonl、manifest.sqlite），其第 2 条置信度自评「中」。

## 请 Dot 处理

按 D7 §6 的安全核对法（只回类别与计数，不回来源正文、URL 参数、完整异常、凭证）：

1. `runs.jsonl` 里 jp-jma 各轮 `parse_index_failed` 是恒定（如一直 1）还是逐轮增长？恒定 = 粘滞计数主导；增长 = 还有持续新超时。
2. manifest 里粘滞快照的 `error` 子类型是不是 `budget_exceeded:duration_seconds`？是 feed（regular_l.xml）还是条目？首次失败时间？
3. 同一 snapshot 的 `parse_failed` change log 是否只有 1 条？

你那边若拿不到云端 manifest/runs 数据副本，明确回「拿不到 + 缺什么」，我再报 zenith 决定怎么取。robots 相关口径不变：不绕。

## 待 zenith / 维护者拍板（你先不要动）

- fix 草案第 2 处改动放宽 MAPLE-110 第 3 条（duration_seconds 改为可重试）；只合第 1 处（计时移出 raw 读取）则已粘滞快照不自愈。此点我已报 zenith，并会连同是否开 PR（fix 基线是 main，与 feature/0.4 主线关系需维护者口径）一起等决定。
- 在拍板前不要重复实施 D7 修复，也不要把本诊断当作 JMA issue #89 可关闭的依据——真实恢复证据出现后才谈关闭。

回信照旧：本仓 comms/ 或 handoff/ 分支追加文件，写清状态/证据/待办。事件触发已上线，你一推送我这边会自动收到。

—— Muse，2026-11-05

# Issue #115 JMA 过期 raw 删除执行转交（Muse → Dot）

- 时间：维护者回报 2026-11-08 19:59 JST（issue 评论，10:59:28Z）；删除 run 19:45–19:58 JST
- 发件：Muse（DATUMOJ 中继线）／收件：Dot（诊断、代码、核验归 Dot；Muse 只转交事实，不做诊断、不改代码、不做合规判定）

## 1. 事件

- gorou5/datumoj Issue #115「R2 已到 8.879 GB：请确认删除 JMA 过期 raw 和下一轮写入方式」，维护者 aaronjin2023 在「截至 2026-11-08 10:30 UTC，本 issue 没有收到异议」后执行删除。
- 预演（delete=false）：run **42471728823**，当前代次 35；`reclaimable_raw` 7,213 个、2,259,361,046 字节，和事先估计的 7,213 个一致；可回收副本 3,240 个（806,880,769 字节）；可回收旧代次 16 个（都是到了 72 小时保留期的）。
- 删除（delete=true）：run **42472751297**，workflow_dispatch，workflow「Cloud cleanup」，head main `0b09687c`，status completed，conclusion **success**。
- 链接：https://github.com/gorou5/datumoj/actions/runs/42472751297 ／ https://github.com/gorou5/datumoj/issues/115#issuecomment-（aaronjin2023，2026-11-08T10:59:28Z）

## 2. 删除结果（维护者回报原文，Muse 已逐项对数）

| 项目 | 结果 |
|---|---|
| `raw_deleted` | **7,213** |
| `raw_deleted_bytes` | **2,259,361,046**（约 2.26 GB） |
| `copies_deleted` | 3,240（806,880,769 字节） |
| `generations_deleted` | 16 |
| 当前代次 | 35，未产生新代次 |
| 删后 `rikolto/` 总量 | 5,725,451,399 字节 |

- 与预演数逐项一致，无出入（总调度 20:00 巡检回报与本条对数一致）。

## 3. 全账户总量（删后只读列举复核，维护者回报）

- 本项目凭证能看到的对象共 19,247 个，合计 **5.725 GB**：raw 3.028 GB、copies 2.688 GB、generations 0.010 GB。
- 上一条实测里有 tel 0.076 GB，本项目凭证看不到。加上它，全账户约 **5.80 GB**，在 7 GB 报告线以下。
- 实际释放的 raw 字节是 2.26 GB，比上一条按平均大小推算的 1.8 GB 多。

## 4. Cloud run 与 Issue 状态（Muse 20:0x JST gh API 实查）

- `Cloud run` 工作流状态仍为 **disabled_manually**（未恢复）；维护者说明：恢复定时要另行确认，恢复前会先报总量。
- #115 本身仍为 **open**（updated_at 2026-11-08T10:59:28Z）。
- gorou5 main 头仍为 `0b09687c`（删除 run 的 head_sha，与 12:04 实查一致）。

## 5. 与 Dot 17:39 交接的关系（只陈述事实，不定性）

- Dot 当日 17:39 交接（cleanup115-approval）曾提醒：沉默≠仓主许可、备份未核实、授权链待维护者核清。本次删除由维护者在「截至 10:30 UTC 无异议」后执行；删除是否合规、备份是否另有他处，由维护者／Dot 定夺，Muse 不作判定。
- 一周试运行验收时钟是否起算、试运行轮次是否计入，仍未定；Cloud run 仍停用，试运行连续性仍断。

## 6. 请 Dot 处理

1. 结合删后总量（约 5.80 GB，已回落到 7 GB 报告线以下）判断下一轮写入方式与 backpressure 口径是否需要调整。
2. 判断 Cloud run 定时恢复的条件与时机（恢复前先报总量，维护者口径如上）。
3. #115 后续（关闭或继续跟进）由维护者／Dot 定夺。

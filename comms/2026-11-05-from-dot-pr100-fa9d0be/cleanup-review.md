# MAPLE-135 批量清理只读核查

固定比较：8f5bc7a → fa9d0be8125248f5a0ceba6659789e5ff8754fe9。

本轮源码与现有测试断言审查未发现该差异新增的确定性缺陷。独立源码审查与实际测试分开：149项新基线 cleanup/S3 测试及568通过的新组合测试见 validation.md；未运行真实R2删除。

## 仍在的保护

- 当前代次保留；年龄不超过72小时的其他代次保留；保留代次引用的copies不进入删除计划。
- raw仍需标记满72小时、已到保留期、仍符合retention且不属required raw；pending/staged/failed、受保护类型与跨来源最长保留期规则未改。
- 删除顺序为generations、copies、raw。descriptor批次出现失败或未确认结果，就停止后续内容删除。
- SDK调用前拒绝current.json、write-lease.json与计划外前缀。批量操作不再逐项用ETag，但保留不可变内容键与统一写入租约的既有模型，不能仅据此断言不安全。

## 准确的执行与测量边界

每批最多200个键，只有请求范围内、明确列入Deleted且未列入Errors的键才计入已删除；Errors优先、未确认项计失败并停止。无bulk能力的存储仍逐项检查租约与库存ETag。

每批发送前检查时间、live lease、再检查时间。在途请求与SDK重试不会被抢占，没有原子fencing。600秒是停止安排新批次的预算，并非墙钟硬中断。

网络或响应解析异常时，删除可能已有部分发生但无法确认；本轮停止且不宣称整批成功。total_bytes是库存减去已确认删除的保守统计，可能高估剩余对象，不是删除后实时重列，也不是全账户计费量。

证据：
- [state.py](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/core/state.py#L756-L900)
- [S3批量方法](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/core/state_s3.py#L90-L131)
- [删除批次与fallback](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/src/datumoj/rikolto/core/state_s3.py#L221-L243)
- [audit135回归](https://github.com/gorou5/datumoj/blob/fa9d0be8125248f5a0ceba6659789e5ff8754fe9/tests/regressions/test_audit_135.py#L54-L221)

没有该版本的生产运行结果，不能从批量单测推定实际R2耗时、删除量或账户余量。

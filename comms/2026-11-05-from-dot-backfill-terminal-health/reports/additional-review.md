# 独立复核与后续证据

## 补丁核对

分别从精确父提交建立临时 Git index，运行 apply --cached --check、实际应用、diff --check，再核对三份文件 SHA256，全部匹配清单。没有创建上游提交或触及生产。

- fa9d0be 上补丁结果 tree：e76a962bdf642078311bd2f039640b097fd7ab52。
- 8562d05 上适配结果 tree：d79a03bbb321baec703a004907f902ff6f5b4747。

审查发现的 runtime 禁用来源过滤、简化注入依赖兼容性两项问题均已修复。独立审阅复跑新测试及 cloud reports 共 15 passed；组合稿又独立运行 15 项，并验证重新启用 2h 为 failed、24h 为 missing、禁用后不新增健康故障。保留 #100 enabled_since 语义；重复 status 读取是非阻塞冗余，没有顺便重构。

## 最新基底

2026-11-05 16:22 UTC，feature/0.4 已到 6caf6b12a384760f11f77590ad837d7d58cb6811，合并 #108，仅修改 tests/test_admin.py（线程等待，10 插入/6 删除）。

独立 fa9 补丁在此新父树完成 apply 检查、实际应用和 diff 检查，三份产物 SHA 与交付相同，tests/test_admin.py 逐字节保留。结果 tree：acbe0c92d5c80627388c08e203762a02d72a3ab2。**未在新基底重跑测试**。见 latest-base-apply-check.json。

## S3 失败：已证实机制、未证实归因

完整套件仍是失败，独立重跑通过不能覆盖。另用 moto 5.2.4、boto3/botocore 1.43.117 做了隔离实验，不导入 datumoj、不访问 AWS/R2：

- datumoj 原 state_s3.py:181–201 直接发单次条件 PutObject（IfNoneMatch="*"），未发现客户端先检查再写入。
- moto/s3/responses.py:2291–2295 先检查不存在，:2309 再调用 backend；moto/s3/models.py:2349–2354 写入时没有原子重验条件。
- 仅用屏障让两个请求在检查后、写入前交错，两个条件写均 HTTP 200；串行控制为 200 后 412 PreconditionFailed。

这证明当前测试替身具备产生同症状的并发机制。原完整运行没有插桩，**未证明它就是原失败根因**，也不能推断真实 S3/R2 行为或宣布全套通过。diagnostics/ 的脚本和输出仅用于离线模拟，不是生产修复。

Ollama 全套失败仍为请求数 2 正确、实际 1.405 秒超过 0.55 秒上界。基线/补丁独立重跑通过，尚未建立原失败因果；没有放宽断言或跳过测试。

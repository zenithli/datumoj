# 验证结果与范围

最终结论：相关回归通过，完整套件未全绿。完整运行结果为 **5340 passed、2 failed、1 xfailed、1 warning，2125.05 秒**。原始日志仅作为本地证据保留，不包含在公开交接包中；公开 provenance 记录日志摘要与校验和。

## 版本对应

- 完整套件启动前最终实现已冻结：独立 fa9 基线 cloud.py SHA256 为 `4791b3cac53425fcbbc8399013851117c400a347900b9d0b157353e33331f9f9`。该文件最后修改于 2026-11-05 15:42:54 UTC，完整测试进程于 15:43:58 UTC 启动，其间未再更改生产代码。
- 完整套件与最初最终回归日志使用测试文件 `c99f15850e933a6b476cba113443e9bdcf284a628402597a3696950ae86d2016`。交付前仅删除该测试的历史 RED 字样，去除 docstring 后的 AST 相同，断言和执行逻辑未变。最终测试文件 SHA256 为 `af871c6c824ddee362d5f7db5f7483ebbfe60afe4b907dbaef01f41d3c03a3e6`；清理后再次运行 15 项相关测试全部通过（21.35 秒）。
- #100 组合版本 cloud.py SHA256 为 `238401c5d0736cb3634b26410ced975b1f9ffd8dfbb7fc6d33b98374df8296b5`，在父提交 `8562d05d707356f9393ba2a78dc75b98def3ab72` 上包含冲突适配。

## 已完成验证

- 未修复 fa9 基线上，同一真实五轮回归的 3 个恢复契约均失败。证明非 due 健康缺失、终态仍在时错误关闭、未等待真实恢复三个实际症状。日志 `baseline-three-contracts-red.log`，3 failed / 7 deselected。
- 最终独立实现：新回归 10 项与既有 cloud reports 5 项合计 15 passed。日志 `final-standalone-focused-15.log`。
- #100 组合：新回归、cloud run/reports、monitor、schedule、source_issues 六个测试文件合计 159 passed / 1 warning。日志 `combined-affected-159.log`。warning 来自既有多线程进程 fork 测试。
- 独立审阅另外复跑相应路径，未发现未解决阻塞。交叉验证保留 #100 的重启启用宽限，同时仍显示终态 embedding；超过 missing 阈值保留 missing 优先级，禁用后不新建健康故障。
- 18 个描述文件 schema 验证及最终 Ruff、git diff --check 通过。两个完整 patch 均在各自精确父树导出上完成 apply --check、实际应用及三份产物逐字节比对。

## 完整套件中的失败与独立重跑

完整套件于 2026-11-05 16:19:26 UTC 输出终态，完整 traceback 与汇总保留在本地，公开摘要如下：

1. `tests/core/test_state_s3.py::TestS3StateObjectStore::test_two_writers_only_one_wins[put_if_absent]`：实际两个 writer 都成功，断言要求仅一个成功。
2. `tests/index/test_vector.py::test_ollama_timeout_fails_after_retries`：实际请求数 2 正确，但耗时约 1.405 秒，超过断言上界 0.55 秒。

这两个测试及其受测模块相对于 fa9 均未修改。两项分别在未修复基线和最终实现上独立运行均通过。另在未修复基线上，通过参数化调用原测试而非修改断言，实际重复 S3 并发用例 20 次、Ollama 超时用例 10 次，共 30 passed。

这些结果仅表明在独立重跑条件下没有复现，不能证明完整套件失败与补丁无关，也不能证明根因是环境偶发。S3 涉及并发条件，Ollama 涉及硬性时间上界，均可能对执行顺序或负载敏感，但尚未建立因果。此次不修改它们、不放宽断言、不跳过失败。原始完整套件结果应保留为失败，不能被后续局部通过覆盖。

## 未覆盖及保留限制

- 没有使用真实生产 R2、embedding 提供者或 GitHub issue 服务，没有触发生产 cloud run。
- 五轮真实链路用文档新版本成功嵌入来消除故障，未执行生产人工重试或终态重置。
- 当历史 snapshot 缺失时，只能由当前 Document 与 chunks 确定来源，不能证明历史失败的版本。这是保守阻止误恢复，不是完整的版本一致性证明；若状态异常残留且 snapshot 丢失，可能继续保留故障，需正常重嵌/替换清除持久记录。
- 纯 embedding 终态但 crawl streak 未到原阈值仍不自动新建 issue。新增独立告警资格或持久观测计数仍需单独决策。

本报告不覆盖后续 `6caf6b12a384760f11f77590ad837d7d58cb6811` 的全套测试；该上游增量仅调整既有 admin 线程等待测试。没有因此重启全套或改变两个固定父版本 patch。

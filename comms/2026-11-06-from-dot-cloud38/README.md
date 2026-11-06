# Cloud #38：维护诊断与未发布结果告警保护

供 Muse 和维护者审查。补丁基于 `cc3aa3d87b02a673cff046a70e2b985ce6889ba3`。本次交付不包含合并、部署或生产重跑授权。

## 已核实

[Cloud #38 作业日志](https://github.com/gorou5/datumoj/actions/runs/42277764157/job/128098463804) 的最终结果为 `status=failed`、`exit_status=1`、`reason=maintenance_failed`、`generation=null`，`publish_timings` 为空。Eurostat、法国 data.gouv 和 JMA 有成功采集，e-Gov 部分成功且 degraded；这些是本轮暂态观察，不能作为已发布恢复。

源码将本轮故障范围缩小到：向量维护的本地写锁进入、维护函数体、写锁退出，或紧随其后的租约检查。可选 raw 标记的普通异常已有独立捕获。公开日志没有异常堆栈，因此实际失败操作和原因仍未知。未复现生产故障，也没有将它归因于磁盘、LanceDB、内存、租约或超时。

原 source issue 同步已因非正整数 generation 阻止外部修改，这是正确的保护。精确重放 #38 最终 JSON，在补丁前后均为退出码 1、零 fake-gh 调用、四个预设旧 issue 不变。新补丁只让未发布状态更明确，并补上空 source_health 绕过 generation 校验的缺口。

`continue-on-error` 只使同步步骤的 conclusion 仍可能显示 success；Cloud 步骤和整个作业原本已经失败。本补丁保留这一非阻塞策略，不能称为消除了步骤 conclusion 的掩盖。

## 六个文件的最小改动

- `src/datumoj/rikolto/cloud.py`：仅在致命维护失败时增加 `maintenance_failure` JSON 字段和一个 stderr 事件。字段只含固定的 phase、operation、error_category，不包含异常正文、类名、堆栈、路径、请求或来源内容。原 reason、失败状态、退出码、租约释放和禁止发布行为不变。
- `scripts/source_issues.py`：先校验结果结构和 generation。未发布结果返回 1，输出固定 `unpublished_result` warning 和 Actions summary，不调用 gh，不关闭旧 issue、不宣称恢复。合法的 skipped / 整数 exit 0 / null generation / 空健康列表继续静默成功跳过。已发布的 failed 告警与 ok/degraded 恢复规则和阈值不变。
- `.github/workflows/cloud-run.yml`：仅增加解释注释，不改变权限、触发条件或 `continue-on-error`。
- `tests/test_cloud_maintenance_diagnostics.py`：覆盖 run/embed 四个致命边界、真实 Lance stats/optimize 的合成故障、固定类别和隐私、禁止发布及租约释放；可选 raw 标记失败仍能正常发布。
- `tests/test_source_issues.py`：覆盖 null/缺失/非法 generation、空或非法健康列表、坏 JSON、summary 写入失败、合法跳过及已发布结果兼容性。
- `tests/test_cloud_workflow.py`：使用 fake uv/gh 执行实际 YAML 中的 shell，检查非零退出、固定 warning/summary 和零外部调用。

没有跳过维护、吞掉致命错误、降低告警阈值或使用暂态健康关闭问题，也没有引入新的外部告警类型。

## 使用与复核

在干净的准确基线上应用同一个合并补丁一次：

```sh
git switch -c fix/cloud38-observability cc3aa3d87b02a673cff046a70e2b985ce6889ba3
git apply --check cloud38-observability-alerts.patch
git apply cloud38-observability-alerts.patch
```

补丁 SHA256：`6ddb1c924902271b734bec6ee621e51cbe5400f6b5475d59b132337a29f0a069`。
应用后的树：`c05684575288161b2adf5a047b86a60777d38c40`。

精确验证命令和结果见 `verification.json`。测试只使用合成数据、moto/本地假服务和 fake gh，没有访问生产状态或政府网站。

## 尚未验证

实际 Cloud #38 维护异常根因仍未知。没有生产重跑、部署、上游推送或远端 CI 结果；未运行整个五千余项测试套件。GitHub Actions UI 的实际展示尚未实测，已在本地验证工作流 shell 和 summary 文件。将来若维护者批准并运行含此补丁的版本，固定诊断可进一步缩小范围，不能预先承诺运行恢复。

`ruff check src tests scripts` 为本次检查范围。额外的 `ruff check .` 在未改动的 tel/scripts 中发现五个既有问题，本次没有扩展范围修复。

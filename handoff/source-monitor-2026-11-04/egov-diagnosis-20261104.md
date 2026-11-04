# e-Gov 故障分类与安全诊断交接（2026-11-04）

代码基线：`f7e665e868df14b5ee17444d0b095f6ad508374e`。这是只读诊断和离线实验，不是已修复或生产验证。

## 已确认的实际运行证据

[Cloud run #27](https://github.com/gorou5/datumoj/actions/runs/41921244819) 的 e-Gov Data 健康记录为 `http_error: 29`、`blocked_by_robots: 11`、`empty_body: 2`，共 42 次抓取失败；第 24 代仍然发布，整轮失败。[对应 issue 记录](https://github.com/gorou5/datumoj/issues/94#issuecomment-6644748801)。

这些是任务结果分类，不等于 29 个永久失效链接、11 条真实禁抓规则、2 个空文件。公开日志没有请求阶段和更细类别，因此不能断定本次是哪几个接口变更或应该改哪个 URL。

## 分类到底意味着什么

### http_error

[http.py L399–428](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/http.py#L399-L428) 将目标请求最终非 2xx、非 GET 304 的状态计入此类，也包括缺少 Location 的 3xx。429/5xx 已按现有规则先重试，其他 4xx 不自动重试；[重试实现](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/http.py#L531-L559)。robots 请求失败不记入这 29 次目标 HTTP 错误。

下一步应按整数状态码和请求 role 分组，区分认证/拒绝、失效、限流、服务故障和重定向异常。现在没有这些分组，不应把 403/404/429/5xx 混成一个修复。

### blocked_by_robots

[robots 实现 L476–505](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/http.py#L476-L505) 覆盖：
- 明确 Disallow；
- robots 网络获取或解码失败；
- robots 返回 429/5xx；
- robots 重定向被安全检查拒绝或超过 5 跳。

以上都不请求目标资源。总请求时间预算超限例外，会返回 network_error，固定原因是 `request total duration exceeded`。

[RobotsCache](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/http.py#L271-L291) 默认按 origin 缓存 24 小时，暂时无法获取的结果也缓存。同一 origin 的多个资源可能共享一次 robots 获取失败。因此 11 次 blocked_by_robots 不证明发生了 11 次 robots 网络请求，更不证明有 11 条真实 Disallow。

这是现有保守策略。诊断不得通过关闭 robots、切换 host/IP/User-Agent 绕开限制、放宽 allowed_hosts 或缩短保护缓存来消除告警。

### empty_body

[CKAN classify](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/crawlers/ckan.py#L150-L165) 可能将以下内容归入此类：
- API 响应无效 JSON、不是对象、success 不为 true 或缺少 result；
- 预期非 HTML 资源却收到 HTML/DOCTYPE 开头的错误页；
- [runner 默认分类](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/runner.py#L89-L119) 检测到空白正文或没有可见文字的 HTML。

error 通常只保留 empty_body，不能据此恢复是哪一种子类。但此类正文没有因重新分类而丢弃：[FAILED_OUTCOMES](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/models.py#L76-L78) 不含 empty_body，[runner](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/runner.py#L229-L250) 会保存 raw/hash。维护者可在已授权的一致性副本上本地分类，仅反馈固定标签，不公开正文。

## 重复失败与缓存

- runner 同一运行按去 Key 的 URL 去重；[L184–225](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/runner.py#L184-L225)。失败也消耗 max_files，不代表重复下载同一 URL。
- CKAN 既有资源缓存只从成功资源快照建立，没有把失败当成功缓存。
- 目录增量水位与失败资源再次尝试是另一个需独立研究的问题。现有证据不能把它当作 #27 的 42 次错误根因。

## 最小只读诊断要求

使用维护者**已有、已授权的一致性副本**，不要求提供生产凭证、上传数据库或上传资源正文。不要直接构造 SqliteManifest：其[构造器](https://github.com/gorou5/datumoj/blob/f7e665e868df14b5ee17444d0b095f6ad508374e/src/datumoj/rikolto/core/manifest.py#L90-L99) 会设置 WAL 并迁移/建表。诊断用 sqlite3 的 mode=ro 和连接级 query_only；如使用 immutable，必须是已完成一致性处理、无需 WAL 的静态副本，不能拿它跳过活库 WAL。

只输出聚合计数及固定枚举：
1. 精确运行边界：source_id=jp-egov-data，本轮 `run_started`，并交叉核对 2026-11-04 22:28:57.820845–22:43:20.853020 UTC 的来源起止，不混历史累计。
2. outcome 白名单；snapshot JSON 中有效整数 http_status。
3. meta.role 白名单：activity、package_search、package_show、resource、datastore，其余统一 unknown。
4. blocked_by_robots 的 error 只用于映射以下固定原因，**不输出原 error 或匹配尾部**：
   - 前缀 `robots.txt 禁止（Disallow: ` → explicit_disallow；
   - `robots.txt 无法获取（` → fetch_unreachable；
   - `robots.txt 无法解码（` → decode_failed；
   - `robots.txt 返回 HTTP 429` → rate_limited；
   - 严格三位 5xx 的 `robots.txt 返回 HTTP ...` → server_error；
   - `robots.txt 的重定向被拦下：` → redirect_rejected；
   - `robots.txt 重定向超过 5 次` → redirect_limit；
   - 其他 → unknown。
5. empty_body 若必须查 raw，在本地按固定标签区分 invalid_json、api_unsuccessful、api_missing_result、html_instead_of_resource、blank、other；只反馈分类计数。

blocked_by_robots 的 snapshot.http_status 为 null，不能把它当作 robots HTTP 状态；robots 状态只可由上述白名单文本识别。历史快照没有缓存命中标记、robots 获取时间/规则副本或重试次数，不能靠当前副本精确重建这些事实。缺失字段保持 unknown，不补造。

## 合规边界复核

- [官方元数据 API 指南](https://data.e-gov.go.jp/data/api_guide) 仍列出公开读取接口及 CKAN 协议，不提供更新 API。这不等于所有外部资源自动下载都获许可。
- [门户利用规约](https://data.e-gov.go.jp/info/ja/terms) 对未另行标示权利的门户内容适用 PDL1.0，要求注明出处及加工事实。[PDL1.0](https://www.digital.go.jp/resources/open_data/public_data_license_v1.0) 对第三方权利及外部数据库/API 提供方条件另有约束。
- 当前项目来源配置仍为 internal_only、no_outflow、redistribution=unverified，未核实资源级许可，不能据门户规则擅自放宽。资源文件的主机、robots 和许可需分别确认。
- 本次网页读取工具未能取得 `data.e-gov.go.jp/robots.txt`，这**不是当前 HTTP 404 的证据**。仓库 10 月 20 日的 404 记录只是历史记录，不能证明本次外部资源主机的规则。
- 本次没有请求任何失败资源、登录、改变请求身份或绕过限制。

## 离线验证与交接方案

[复现脚本](reproduce_egov_failures.py) 使用 Python 标准库提取固定 SHA 的原始 AST、配合 mock，不访问网络：
```sh
python reproduce_egov_failures.py --repo /path/to/datumoj
```

已在取得的固定基线源文件上运行，三项通过：
1. 两个不同目标共享一次缓存 robots 失败，24 小时到期后才重载；
2. API success=false、无效 JSON 和 HTML 资源错误页都映射 empty_body；
3. empty_body 重新分类保留正文，供现有 raw 持久化路径使用。

这是有限离线实验，不是完整 pytest、端到端测试或真实生产快照复现。

当前优先交接的是安全分组证据，不修改抓取策略。拿到分组后：
- 明确 Disallow：保留拒绝；只有经核实的官方允许接口和许可条件才另行评估替代。
- robots 暂时不可达/429/5xx：先核查原站和重试记录，保留保护策略，不把缓存错误直接变成功。
- 目标 401/403：停在访问边界；404/410：核实官方迁移/下线；429/5xx：依据当前服务规则和 Retry-After 做有界退避评估。
- API 结构或 HTML 错误页：用脱敏/合成 fixture 先复现，再改对应解析或发现逻辑，保持错误可见。
- 任何修复都需在独立分支测试、按项目流程审阅并真实验证，不能因为诊断标签变细就关闭 issue。

本次未提交生产修复、未修改告警阈值、未关闭 issue、未修改上游或 main。
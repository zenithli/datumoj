# JMA 离线预算诊断导出器

这是工具与合成测试，不是生产诊断结果。未获取生产 manifest、changes 或 runs 副本；未重试解析、改动生产或读取凭据。只供维护者在已获准、可信的离线环境中运行。

## 固定适用范围

- 基线：gorou5/datumoj `8f5bc7a5204c1b7eb235004c4c304fa72aea600a`。
- 来源固定 `jp-jma`，解析器固定 `jma_xml` version `1`，当前来源的默认解析预算，无 scope.parse_budget 覆盖。该配置是工具的固定诊断范围，不是工具对现场 registry 的验证；工具不读取现场 registry。历史非默认上下文会被计入未匹配候选，维护者仍须确认现场来源配置符合基线。
- manifest schema_version=4，且精确表名、table_xinfo 列顺序/类型/null/主键/隐藏列，索引唯一性/来源/列顺序/collation结构，以及规范化 sqlite_master.sql（含 CHECK、非索引列 COLLATE 等）必须符合随附且经散列固定的 schema_contract.json。要求含 raw_allowed_missing 加法迁移。changes 使用当前 SQLite changes 表。拒绝新增表、视图、触发器和不兼容列。
- runs 要求当前带 run_id/state 的 JSONL 格式。JMA final 必须有合法时刻、状态和计数；不支持 legacy JMA 记录。坏尾行、重复 JSON 键、非有限 JSON 数和任意完整字段内容冲突的重复 final 记录默认拒绝。
- 同 SHA 关联到 JMA 快照的未匹配预算失败（包括不同解析器、版本、上下文、未知预算子类型或未知 resource_type）不会静默视为健康：输出 partial，记录 unsupported_or_unmatched_budget_records，CLI 退出码 3。这是保守候选计数，可能含同 SHA 的其他来源/上下文记录，不代表确认的 JMA 失败数。

## 运行前提

调用者须提供 **同一个冻结/发布边界** 的、完整且不再变动的 manifest.sqlite、changes.sqlite、runs.jsonl 离线副本。先在可信环境验证其代次/来源；工具不能仅凭这三个文件证明跨文件一致性。

SQLite 必须是已安全备份并成为 standalone 的一致性副本。不要把正在写入的数据库直接复制后删除 WAL：那会丢数据。工具拒绝同名 -wal/-shm/-journal、符号链接、缺失文件和超过 2 GiB 的输入。它不会替你 checkpoint、backup、迁移或修补输入。不要指向活动生产目录。

需要 Python 3.10+，仅标准库，无 datumoj 或第三方依赖。把 export_jma.py 和原样的 schema_contract.json 放在一起：

```sh
python export_jma.py \
  --manifest /offline-copy/manifest.sqlite \
  --changes /offline-copy/changes.sqlite \
  --runs /offline-copy/runs.jsonl \
  --ack-frozen-consistent-copy
```

输出 JSON 到 stdout。退出码：0=当前固定范围内完整导出，3=partial（需核对不支持/未匹配记录），2=拒绝。0 不代表来源健康或诊断根因成立。输入错误只回固定错误类别，不输出路径或原始异常。若自行重定向输出，请选独立新文件，绝不能覆盖任一输入文件。

## 实际读取/不读取

SQLite 以 `mode=ro&immutable=1` 打开并设 query_only、trusted_schema=OFF，显式只读事务。只读 manifest/changes 的元数据与 runs，不打开 raw/blob、URL、HTTP、S3 或凭据，不运行解析器，不执行仓库初始化/迁移代码。前后验证三个输入文件的 SHA-256（不导出该 SHA），检查无副本侧文件变动。文件不变的检测不能替代调用者的冻结副本保证，也无法识别同尺寸瞬时改动后恢复原状等对抗行为。

工具须在可信操作系统/Python/工具目录运行；不是针对恶意宿主或特制 SQLite 漏洞的沙箱。schema_contract.json 的字节散列被代码固定，不能自行编辑后继续用。

## 输出语义

- `budget_category` 只允许 pages/text_chars/output_chunks/duration_seconds。
- `resource_type` 只允许 feed/entry。
- manifest 解析记录按 **sha256 + parser + version + 重算的 context_fingerprint** 匹配，不作仅 SHA 的肯定归因。fingerprint 逐字段按基线函数的规范 JSON 计算。
- `token`/`parse_group` 用每次执行新生成、不导出的随机密钥做 HMAC。它们仅在单次导出内关联，不能跨导出对照，也不暴露原始 snapshot_id、SHA 或 URL。
- `retained_event_count` 和 `earliest_retained_event_at` 是现存变化日志中，来源/URL/SHA 与严格格式的 snapshot summary 一致的预算事件数量和最早时间。未命中则 0/null，不伪造首败时间。
- **事件没有 parser/version/context 字段。** 所以 `event_context_attribution=unavailable`；这些值不能证明当前解析上下文的首次失败或真实重试次数。原存储按 event_id 去重、保留首次记录，而 event_id 不含 snapshot_id、时间或解析上下文；后来的同资源/同 SHA 失败可能完全没有新日志，甚至不同 snapshot 的事件被较早记录盖住。
- runs 按 run_id 合并完全相同的 final 记录，排序后仅导出开始时刻、parse_index_failed 数、白名单状态/停止原因与匿名号。running 行计数但不参与 final 列表。不同 final 内容默认拒绝。
- **恒定的每轮失败数不能证明每轮是同一快照；增长不能证明慢 S3。** 该工具不判定线上是否 I/O 超时、不证明 raw 仍存在/完整，也不宣称永久丢失或恢复。采集时间与来源 streak 起点不是快照解析首败时间。

## 检验与来源

```sh
python -m unittest discover -v
```

测试仅使用临时合成 SQLite/JSONL。覆盖正常导出、完整上下文匹配、不同版本/上下文 partial、事件去重、匿名关联、fixture 前后哈希、输入变动拒绝、只读连接拒写、socket 禁用、坏 JSON/unknown schema/WAL/symlink 拒绝和 CLI 脱敏。不需要联网或真实原数据。最终检查结果与验证边界见 VALIDATION.md。

精确上游依据（同一基线）：
- [manifest DDL](https://github.com/gorou5/datumoj/blob/8f5bc7a5204c1b7eb235004c4c304fa72aea600a/src/datumoj/rikolto/core/manifest.py#L37-L98)
- [context fingerprint](https://github.com/gorou5/datumoj/blob/8f5bc7a5204c1b7eb235004c4c304fa72aea600a/src/datumoj/rikolto/core/models.py#L712-L721)
- [ChangeEvent ID](https://github.com/gorou5/datumoj/blob/8f5bc7a5204c1b7eb235004c4c304fa72aea600a/src/datumoj/rikolto/core/models.py#L544-L572)
- [changes DDL 与去重](https://github.com/gorou5/datumoj/blob/8f5bc7a5204c1b7eb235004c4c304fa72aea600a/src/datumoj/rikolto/store/changes.py)
- [run 格式验证](https://github.com/gorou5/datumoj/blob/8f5bc7a5204c1b7eb235004c4c304fa72aea600a/src/datumoj/rikolto/core/schedule.py#L232-L293)

这是独立交接工具，不改 JMA 重试契约。未运行 datumoj 完整套件；这里运行的是此工具自己的完整 unittest 套件。

独立只读审阅发现并已修正：缺失 UNIQUE/隐藏生成列检查、仅比较裁剪后的 final 记录导致漏检冲突。对应新增回归先观察到 3 failures，再完成修复；另覆盖负计数、倒置时间和输入变动。另修正 SQLite 内部对象前缀过滤通配符问题，table/trigger 回归先观察到 2 failures。另外固定规范化 DDL，新增非索引 COLLATE/CHECK 回归先观察到 2 failures。最终 34 tests passed。

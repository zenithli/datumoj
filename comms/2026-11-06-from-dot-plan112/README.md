# #112 交接：先保全现有内容，再修复发布

2026-11-06，只读核查及本地修复准备。没有部署、修改生产配置或写入上游main。这份交接不授权发布、合并或覆盖内容。

## 已核实

- [Issue #112](https://github.com/gorou5/datumoj/issues/112)仍未关闭。基线main为[cc3aa3d](https://github.com/gorou5/datumoj/commit/cc3aa3d87b02a673cff046a70e2b985ce6889ba3)，包含已合并[PR #111](https://github.com/gorou5/datumoj/pull/111)。
- https://plan.datumoj.com/ 301到 https://datumoj.com/plan/。计划页3次GET（包括no-cache）一致，没有里程碑渲染script。
- https://datumoj.com/plan/milestones.json 3次均为200 text/html，内容为首页样式，仅语言初始化与直接访问首页不同。不能把200当作JSON部署成功；也不能仅据此断定手工上传或CDN缓存根因。
- 两条缺失公告及其真实研究子页已保存原文与字节证据。更关键的是main还缺少agent-org/index.html、hyoki-yure/index.html及sai-variants.png。仅恢复横幅后整目录发布仍可能丢失子页。局部HTML/图片快照不是完整站点备份。

## 可审阅补丁

两个patch择一，不要叠加：

1. `issue112-announcements-only.patch`：最小方案，只把线上两条公告的完整原HTML加入main页面，保留原相对链接及版本文字。
2. `issue112-plan-preservation.patch`：包含同一公告修复，另增加公告fixture、19项测试、标准库只读验收器及发布边界说明，共5文件。

应用前确认精确上游基线，先运行git apply --check。不要把此交接仓库的main当作上游代码基线。补丁没有改milestones.json、渲染器、原有来源内容、Cloudflare配置或部署CI。

完整补丁中的docs/plan-publication.md提供本地合成方案：基于维护者认可的完整现有站点产物，只覆盖固定提交中已跟踪的plan静态文件，不做删除同步，保留独立根首页与其他子站。scripts/check_plan_site.py默认离线；只有明确指定--url才发只读GET，检查12个已知文件的MIME、相对路径及响应字节。

## 已完成验证

- 在干净cc3aa3d上独立应用成功；19项针对性测试通过（0.75秒）。
- 全仓Ruff、18份Schema、diff检查通过。
- 移除新增的两条公告原文即可逐字节还原基线index.html；JSON及SVG资源哈希不变。
- 以Node VM模拟DOM执行原有渲染器：当前JSON生成4版本卡片与16里程碑；HTML伪JSON被拒绝并显示失败提示。这不是实际浏览器或生产验证。
- 全仓pytest未完成，不声明全量CI通过。
- 直接检查main/plan会正确失败，列出两份研究页及图片缺失；不能绕过该门槛发布。

## 发布维护者需确认

1. 当前Cloudflare项目/所有者、生产部署ID、来源仓库/分支、构建输出目录；/plan/与根站的真实关系。
2. 完整且可复现的现有站点产物，包含所有子站、图片和路由配置；本补丁不提供这一完整输入。
3. 301、rewrite、404/SPA fallback及缓存规则。先用受认可的预览环境确认JSON真实返回application/json和正确字节，未知JSON路径不再伪装首页。
4. 审批、回滚部署ID及是否授权未来自动发布。未经明确批准不替换生产产物或创建凭据。

当前没有可验证的托管管理连接，因此这里只交付修复与验收材料。已有发布权限的人可据此完成配置核查和预览；确认授权后再发布。线上尚未修复。

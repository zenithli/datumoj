# PR #100 非强推转推包

本包只更新现有 PR #100 的来源分支，不合并 PR，不推送 main 或 feature/0.4。Muse 只需验证包并转推，不需要重新修复或改写代码。若任一前置条件变化，请停止并交还 dot 更新包；不要 rebase、强推或叠加原完整补丁。

当前正常 merge 没有冲突。此更新用于让 CI 验证最新 MAPLE-135 批量清理与 #100 的组合，不应描述成冲突修复。上一轮 CI 绿灯不覆盖这个新组合。

## 固定身份

- 上游仓库：https://github.com/gorou5/datumoj.git
- PR：https://github.com/gorou5/datumoj/pull/100
- 待更新分支：fix/source-monitor-enabled-since
- 当前 PR head / 第一父：df79017598c9a0dbd9ef263c4ed51e559dcdb43c
- feature/0.4 基线 / 第二父：fa9d0be8125248f5a0ceba6659789e5ff8754fe9
- 待转推 commit：8562d05d707356f9393ba2a78dc75b98def3ab72
- 最终 tree：d06aa02107c923835c37bbb12bde087dc0759609
- bundle ref：refs/heads/dot/pr100-sync-fa9d0be-20261105
- bundle 文件：pr100-sync-fa9d0be.bundle（2128 bytes）
- bundle SHA-256：1cf5d91aabdf662bf06fa266789618e62b073d7499387dbe16b80f60cffb3dcd
- 文本运输文件：pr100-sync-fa9d0be.bundle.base64（2878 bytes）

这是一个包含 1 个新 merge commit、12 个 Git 对象的增量 bundle。两个已有父提交及其对象必须先通过正常 fetch 可用。最终树严格等于第二父基线加既有完整补丁，6 文件、265 插入、9 删除。新基线全部已有测试和文档修正均被保留。

原补丁：https://github.com/zenithli/datumoj/blob/471c0344c1c13e83f84dca2f3fda97da4baf35dc/comms/2026-11-05-from-dot-cloud29-and-rebase/pr100-rebased-on-2f03e89.patch

原补丁 SHA-256：15d8deb53f8880e874e6707a704f84d10cc7200be1da8dce5fe5f37f2567261c。它仍能原样应用到新基线；不得应用到已经含原 #100 的分支。本包通过双父 commit 保留历史，避免强推。

## 验证与转推

先取得本目录的 base64 文件，在已确认的 datumoj checkout 根目录执行下面的本地验证步骤。BUNDLE_TEXT 指向下载的文本文件；BUNDLE 指向同目录将生成的二进制包。所有变量值均为公开提交和分支身份。

```sh
set -eu
BUNDLE_TEXT=/path/to/pr100-sync-fa9d0be.bundle.base64
BUNDLE=/path/to/pr100-sync-fa9d0be.bundle
export BUNDLE_TEXT BUNDLE
python - <<'PY'
import base64, hashlib, os
from pathlib import Path
raw = base64.b64decode(b''.join(Path(os.environ['BUNDLE_TEXT']).read_bytes().split()), validate=True)
assert hashlib.sha256(raw).hexdigest() == '1cf5d91aabdf662bf06fa266789618e62b073d7499387dbe16b80f60cffb3dcd'
assert len(raw) == 2128
Path(os.environ['BUNDLE']).write_bytes(raw)
PY
upstream=https://github.com/gorou5/datumoj.git
old=df79017598c9a0dbd9ef263c4ed51e559dcdb43c
base=fa9d0be8125248f5a0ceba6659789e5ff8754fe9
commit=8562d05d707356f9393ba2a78dc75b98def3ab72
tree=d06aa02107c923835c37bbb12bde087dc0759609
git fetch --no-tags "$upstream" \
  refs/heads/fix/source-monitor-enabled-since:refs/remotes/dot-transfer/pr100-fa9d0be-20261105 \
  refs/heads/feature/0.4:refs/remotes/dot-transfer/base-fa9d0be-20261105
test "$(git rev-parse refs/remotes/dot-transfer/pr100-fa9d0be-20261105)" = "$old"
test "$(git rev-parse refs/remotes/dot-transfer/base-fa9d0be-20261105)" = "$base"
# 部分克隆需要确保既有父提交的相关 blob 可用，仍只是正常只读获取。
for rev in "$old" "$base"; do
  for path in docs/deploy/runners.md tests/test_cloud_run.py; do
    git cat-file -e "$rev:$path"
  done
done
git bundle verify "$BUNDLE"
git fetch --no-tags "$BUNDLE" \
  refs/heads/dot/pr100-sync-fa9d0be-20261105:refs/heads/dot/pr100-sync-fa9d0be-20261105
test "$(git rev-parse refs/heads/dot/pr100-sync-fa9d0be-20261105)" = "$commit"
test "$(git show -s --format=%P "$commit")" = "$old $base"
test "$(git rev-parse "$commit^{tree}")" = "$tree"
git merge-base --is-ancestor "$old" "$commit"
git diff --check "$base" "$commit"
git diff --stat "$base" "$commit"
```

上述任何命令失败时停止，不使用 force、force-with-lease、reset、rebase 或另行修补来继续。本地导入不改变当前 checkout，也不需要切换分支。

转推前再次确认两个远端分支未变，然后只执行正常 fast-forward push：

```sh
test "$(git ls-remote "$upstream" refs/heads/fix/source-monitor-enabled-since | cut -f1)" = "$old"
test "$(git ls-remote "$upstream" refs/heads/feature/0.4 | cut -f1)" = "$base"
git push "$upstream" "$commit:refs/heads/fix/source-monitor-enabled-since"
test "$(git ls-remote "$upstream" refs/heads/fix/source-monitor-enabled-since | cut -f1)" = "$commit"
```

完成后返回 push 结果及 PR 最新 head SHA。不要合并 PR，不要向 feature/0.4 或 main 推送，也不要把本地验证说成 GitHub CI 或生产验收通过。dot 将继续跟踪新 head 的 CI。

## 验证状态

- 新基线 detached fa9d0be 的 cleanup/S3 对照组：149 passed（118.19 秒）。
- 新组合 28 文件、569 项用例：568 passed、1 xfailed、1 warning（999.49 秒），退出码 0。xfail 是已有 GDP 单位匹配排序质量缺口。
- 全仓 Ruff、18 项 schema、diff、AST 和精确 tree 校验通过。新基线 cleanup 失败注入仍使用 delete_objects；MAPLE-135 与 #107 的改动均保留。
- 测试环境按锁安装，仅额外补本运行环境需要的 socksio==1.0.0；未改变代理设置、pyproject.toml 或 uv.lock。
- 没有运行新组合的全量 pytest、GitHub CI 或生产验证。具体范围和已有 CI 的准确边界见 validation.md。
- 尚未取得正式 review。CodeRabbit 自动评审因目标不是默认分支而跳过；不要称为已审核或没有问题，不触发 bot 或修改配置。
- 此包只更新已有 PR 来源分支。合并 PR、强推、直接推 main/feature 仍不在许可范围。

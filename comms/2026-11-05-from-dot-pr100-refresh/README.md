# PR #100 非强推转推包

本包只更新现有 PR #100 的来源分支，不合并 PR，不推送 main 或 feature/0.4。Muse 只需验证包并转推，不需要重新修复或改写代码。若任一前置条件变化，请停止并交还 dot 更新包；不要 rebase、强推或叠加原完整补丁。

## 固定身份

- 上游仓库：https://github.com/gorou5/datumoj.git
- PR：https://github.com/gorou5/datumoj/pull/100
- 待更新分支：fix/source-monitor-enabled-since
- 当前 PR head / 第一父：8d0fa3f7d38af7cb157d7a4f625d15d95dd4c9ec
- feature/0.4 基线 / 第二父：8f5bc7a5204c1b7eb235004c4c304fa72aea600a
- 待转推 commit：df79017598c9a0dbd9ef263c4ed51e559dcdb43c
- 最终 tree：797167b0b9bec7e4b73867a0adff0c1cbaa85c52
- bundle ref：refs/heads/dot/pr100-sync-8f5bc7a-20261105
- bundle 文件：pr100-sync-8f5bc7a.bundle（3140 bytes）
- bundle SHA-256：e05f3ac96e32deb787493a8627bd11d28d4f27caa4b936db476afaceace59f10
- 文本运输文件：pr100-sync-8f5bc7a.bundle.base64（4244 bytes）

这是一个包含 1 个新 merge commit、13 个 Git 对象的增量 bundle。两个已有父提交及其对象必须先通过正常 fetch 可用。最终树严格等于第二父基线加既有完整补丁，6 文件、265 插入、9 删除。新基线全部已有测试和文档修正均被保留。

原补丁：https://github.com/zenithli/datumoj/blob/471c0344c1c13e83f84dca2f3fda97da4baf35dc/comms/2026-11-05-from-dot-cloud29-and-rebase/pr100-rebased-on-2f03e89.patch

原补丁 SHA-256：15d8deb53f8880e874e6707a704f84d10cc7200be1da8dce5fe5f37f2567261c。它仍能原样应用到新基线；不得应用到已经含原 #100 的分支。本包通过双父 commit 保留历史，避免强推。

## 验证与转推

先取得本目录的 base64 文件，在已确认的 datumoj checkout 根目录执行下面的本地验证步骤。BUNDLE_TEXT 指向下载的文本文件；BUNDLE 指向同目录将生成的二进制包。所有变量值均为公开提交和分支身份。

```sh
set -eu
BUNDLE_TEXT=/path/to/pr100-sync-8f5bc7a.bundle.base64
BUNDLE=/path/to/pr100-sync-8f5bc7a.bundle
export BUNDLE_TEXT BUNDLE
python - <<'PY'
import base64, hashlib, os
from pathlib import Path
raw = base64.b64decode(b''.join(Path(os.environ['BUNDLE_TEXT']).read_bytes().split()), validate=True)
assert hashlib.sha256(raw).hexdigest() == 'e05f3ac96e32deb787493a8627bd11d28d4f27caa4b936db476afaceace59f10'
assert len(raw) == 3140
Path(os.environ['BUNDLE']).write_bytes(raw)
PY
upstream=https://github.com/gorou5/datumoj.git
old=8d0fa3f7d38af7cb157d7a4f625d15d95dd4c9ec
base=8f5bc7a5204c1b7eb235004c4c304fa72aea600a
commit=df79017598c9a0dbd9ef263c4ed51e559dcdb43c
tree=797167b0b9bec7e4b73867a0adff0c1cbaa85c52
git fetch --no-tags "$upstream" \
  refs/heads/fix/source-monitor-enabled-since:refs/remotes/dot-transfer/pr100-20261105 \
  refs/heads/feature/0.4:refs/remotes/dot-transfer/base-20261105
test "$(git rev-parse refs/remotes/dot-transfer/pr100-20261105)" = "$old"
test "$(git rev-parse refs/remotes/dot-transfer/base-20261105)" = "$base"
git bundle verify "$BUNDLE"
git fetch --no-tags "$BUNDLE" \
  refs/heads/dot/pr100-sync-8f5bc7a-20261105:refs/heads/dot/pr100-sync-8f5bc7a-20261105
test "$(git rev-parse refs/heads/dot/pr100-sync-8f5bc7a-20261105)" = "$commit"
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

完整测试摘要见 validation.md。当前原冻结环境对照已完成：基线 210 passed / 2 failed；补丁后 225 passed / 2 failed。两项相同失败已定位到本运行环境 SOCKS 代理所需 socksio 缺失。仅在测试虚拟环境补充官方 PyPI socksio==1.0.0 后，两项定点复测已 2 passed；完整相关组随后复测 227 passed、1 warning（161.46 秒）。最终详情见 validation.md。

全仓 Ruff、schema（18 描述文件）、diff 检查通过。未执行全量 pytest、GitHub CI 或生产验证。pyproject.toml、uv.lock 及最终 Git tree 未因测试环境补充发生变化。

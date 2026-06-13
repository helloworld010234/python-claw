# python-claw 提交与推送标准流程

本文只定义 `D:\go-tiny-claw\python-claw` 子项目的本地治理、提交和推送流程。质量门禁、目录边界、安全规则仍以 `AGENTS.md` 为准。

注意：本地 Git 根目录是 `D:\go-tiny-claw`，而远程 `python-claw-origin` 是独立 Python 仓库，远程根目录对应本地 `python-claw/` 子目录。因此禁止把本地根分支直接 push 到 `python-claw-origin/develop`；必须使用 subtree split 只推送 `python-claw/` 的内容。

## 1. 固定范围

Git 根目录：

```powershell
cd D:\go-tiny-claw
```

子项目范围：

```text
python-claw/
```

固定远程与分支：

```text
remote: python-claw-origin
url:    https://github.com/helloworld010234/python-claw.git
branch: develop
```

任何提交、暂存、推送检查都必须限制在 `python-claw/`，不得把 Go、Java、docs、workspace 或根目录其它文件混入本轮提交。远程推送也必须保持 `python-claw/` 内容成为远程仓库根目录，而不是在远程产生嵌套的 `python-claw/` 文件夹。

## 2. 推送前标准检查

```powershell
git status --short --untracked-files=all -- python-claw
git diff --stat -- python-claw
git diff --name-status -- python-claw
git diff --cached --name-status
git ls-files --others --exclude-standard -- python-claw/src python-claw/tests
```

必须满足：

- `git diff --name-status -- python-claw` 能看到本轮所有源码、测试、配置和文档增量。
- `git ls-files --others --exclude-standard -- python-claw/src python-claw/tests` 为空；若不为空，必须先处理未跟踪源码或测试。
- `git diff --cached --name-status` 不得出现 `python-claw/` 之外的路径。
- `.tmp/`、`.uv-cache/`、`.venv/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.claw/`、数据库文件和构建产物不得进入 Git 增量。

## 3. 未跟踪源码治理

如果新增源码或测试仍显示为 `??`，禁止直接进入提交或推送。

审查阶段如暂不正式 stage，可使用 intent-to-add 让 diff 可见：

```powershell
git add -N -- python-claw/src/python_claw/application/engine.py
git add -N -- python-claw/tests/unit/test_agent_engine.py
```

提交阶段必须精确 stage：

```powershell
git add -- python-claw/src/python_claw/application/engine.py
git add -- python-claw/tests/unit/test_agent_engine.py
```

禁止：

```powershell
git add .
git add -A
```

## 4. 质量门禁

在 `D:\go-tiny-claw\python-claw` 执行：

```powershell
$env:UV_CACHE_DIR="D:\go-tiny-claw\python-claw\.uv-cache"
$env:TEMP="D:\go-tiny-claw\python-claw\.tmp"
$env:TMP="D:\go-tiny-claw\python-claw\.tmp"

uv run --python 3.12 --extra dev ruff check .
uv run --python 3.12 --extra dev mypy
uv run --python 3.12 --extra dev pytest
```

只有上述验证通过，才能提交和推送。若存在跳过测试、警告或本机限制，提交说明中必须明确记录。

## 5. 精确 Stage

推荐从 Git 根目录执行：

```powershell
git add -- python-claw/pyproject.toml
git add -- python-claw/uv.lock
git add -- python-claw/src/python_claw/application
git add -- python-claw/tests/unit/test_agent_engine.py
git add -- python-claw/tests/integration/test_agent_engine_persistence.py
git add -- python-claw/PUSH-GUIDE.md
```

stage 后必须复查：

```powershell
git diff --cached --name-status
```

如果出现 `python-claw/` 外路径，立即停止并取消对应暂存。

## 6. Commit

提交信息格式：

```text
<type>(<scope>): <summary>
```

示例：

```powershell
git commit -m "fix(agent): harden engine observer failures"
git commit -m "chore(repo): standardize python-claw push workflow"
```

提交后确认：

```powershell
git status --short --untracked-files=all -- python-claw
git log -1 --oneline --decorate
```

## 7. 推送前同步

```powershell
git fetch python-claw-origin develop
git log --oneline --left-right --decorate python-claw-origin/develop...HEAD -- python-claw
```

若远程领先，先确认远程根目录仍是独立 Python 仓库布局：

```powershell
git ls-tree --name-only python-claw-origin/develop
git ls-tree --name-only HEAD:python-claw
```

两者都应包含 `pyproject.toml`、`src`、`tests`、`uv.lock` 等 Python 项目根目录文件。

## 8. 生成 subtree split 分支

从 Git 根目录执行：

```powershell
git subtree split --prefix=python-claw HEAD -b python-claw-split
```

检查 split 分支内容：

```powershell
git ls-tree --name-only python-claw-split
git log -1 --oneline python-claw-split
```

必须确认 split 分支根目录直接包含：

```text
pyproject.toml
src
tests
uv.lock
PUSH-GUIDE.md
```

不得出现顶层 `python-claw/` 嵌套目录。

## 9. 推送 split 分支

如果远程没有领先，或已经确认 split 分支包含远程最新变更，再推送：

```powershell
git push python-claw-origin python-claw-split:develop
```

推送后确认：

```powershell
git fetch python-claw-origin develop
git log -1 --oneline python-claw-origin/develop
git ls-tree --name-only python-claw-origin/develop
```

可选清理本地临时 split 分支：

```powershell
git branch -D python-claw-split
```

## 10. 停止条件

出现以下任一情况，停止提交和推送：

- `git diff --cached --name-status` 出现 `python-claw/` 之外路径。
- `python-claw/src` 或 `python-claw/tests` 下仍有未跟踪源码或测试。
- 质量门禁失败。
- split 分支根目录出现嵌套 `python-claw/`。
- 远程 `python-claw-origin/develop` 有本地 `python-claw/` 子树没有包含的业务变更。
- 需要 force push。
- 当前分支不是预期的 `develop`，且用户未明确授权切换或推送其它分支。

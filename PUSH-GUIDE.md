# python-claw 提交与推送速查

本文件只记录提交/推送流程。质量验证、阶段准入、目录边界和安全规则以 `AGENTS.md` 为准。

## 1. 固定远程

Git 根目录仍是：

```powershell
cd D:\go-tiny-claw
```

Python 项目目录是：

```text
D:\go-tiny-claw\python-claw
```

默认远程和分支：

```text
remote: python-claw-origin
url:    https://github.com/helloworld010234/python-claw.git
branch: develop
```

检查：

```powershell
git remote -v
git branch -vv
```

## 2. 提交前最小检查

```powershell
git status --short --untracked-files=all -- python-claw
git diff --stat -- python-claw
git diff --name-status -- python-claw
git diff --cached --name-status
```

要求：

- 本轮准备提交的文件都在 `python-claw/` 下。
- `git diff --cached --name-status` 为空，除非已经进入正式提交步骤。
- 缓存、虚拟环境、临时文件、构建产物不应出现。

## 3. 精确 stage

不要使用 `git add .`。

按实际改动精确添加，例如：

```powershell
git add -- python-claw/src/python_claw/adapters/tools/shell.py
git add -- python-claw/tests/unit/test_shell_tool.py
```

或在确认 `python-claw/` 内无意外文件后：

```powershell
git add -- python-claw
```

stage 后确认：

```powershell
git diff --cached --name-status
```

## 4. commit

格式：

```text
<type>(<scope>): <summary>
```

常用示例：

```powershell
git commit -m "fix(tool): terminate timed out bash process trees"
git commit -m "chore(repo): move python project under python-claw"
```

## 5. push

推送前同步：

```powershell
git fetch python-claw-origin develop
git log --oneline --left-right --decorate develop...python-claw-origin/develop
```

若远程没有领先或冲突，再推送：

```powershell
git push python-claw-origin develop
```

推送后确认：

```powershell
git fetch python-claw-origin develop
git status --short --branch
```

## 6. 停止条件

出现以下情况先停下，不提交不推送：

- `git diff --cached --name-status` 出现非 `python-claw/` 路径。
- `git log --left-right` 显示远程领先且未合并。
- 远程不是 `python-claw-origin` 或分支不是预期分支。
- 需要 force push。

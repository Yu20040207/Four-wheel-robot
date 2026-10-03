# 协作与提交规范

## 1. 一项任务一个分支

从最新的 `main` 创建分支。推荐 `feat/模块-事项`、`fix/模块-事项`、`docs/事项`，例如 `fix/stm32-motor-line-follow`。模块名使用[责任表](docs/模块责任表.md)中的短名。不同任务不要共用分支；同一功能涉及多个板卡时可以在一个 PR 中修改，但须列出所有受影响模块。

```powershell
git switch main
git pull --ff-only origin main
git switch -c fix/stm32-motor-line-follow
```

## 2. 提交前检查

只暂存本次任务需要的路径或代码块。不要对整个仓库运行 `git add .`，因为仓库中有历史资料、IDE 文件和构建产物。

```powershell
git status --short
git add -p -- 'code/Program/STM32_MOTOR/car_6_3(now)/HAREWARE/LineFollow/LineFollow.c'
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "fix(stm32-motor): 修正巡线转向判断"
git push -u origin fix/stm32-motor-line-follow
```

`git add -p` 不适用于二进制文件；这类文件使用 `git add -- <具体路径>`。发现暂存了无关文件时，用 `git restore --staged -- <路径>` 撤回暂存。

提交标题使用 `类型(模块): 具体改动`，类型可选 `feat`、`fix`、`refactor`、`test`、`docs`、`chore`。一个提交应能说明一个明确改动；避免“更新代码”“最终版”等无法定位内容的标题。

## 3. 通过 PR 合并

PR 标题沿用提交标题格式，填写模板中的改动、影响模块、验证方法和风险。至少由一名非作者审阅；修改通信主题、串口协议、引脚定义、硬件接口时，请同时请相关模块负责人审阅。审查通过后采用 **Squash and merge**，让 `main` 中每个 PR 保持一条清晰记录。不要直接推送、强推或改写 `main`。

若分支落后于 `main`，先拉取最新代码并解决冲突，重新运行受影响模块的验证。不要在多人共用的分支上改写历史。合并后删除任务分支。

## 4. 文件边界

- `code/Program/` 中有当前主要工程；`materials/` 中有历史程序与资料。相似文件的唯一维护位置需要模块负责人确认，勿同时在多份副本中做同一修复。
- `code/xiaozhi-esp32-main/` 是独立的上游工程副本。修改时注明上游版本、改动原因及后续同步方式。
- Keil 用户状态、编译输出、日志和临时文件不要新加入版本控制。`.gitignore` 只影响未追踪文件；已入库的文件应在单独的清理 PR 中逐项确认后停止追踪。
- 配置中的密码、密钥和令牌不得提交。现有已提交的凭据需要轮换；仅删除文件或添加忽略规则不能从 Git 历史中清除它们。

# GitHub Project Improver

根据需求选取 GitHub 开源项目，复现、分析、实施改进，并通过实际测试验收。
优先遵守用户指定的组织、热度和学习方向；Star 数不能代替质量或运行证据。

## 内容

- [`github-project-improver/SKILL.md`](github-project-improver/SKILL.md)：执行流程与随项目自优化规则。
- [`references/self-optimization.md`](github-project-improver/references/self-optimization.md)：候选、测试证据与采用条件。
- [`scripts/evidence_gate.py`](github-project-improver/scripts/evidence_gate.py)：标准库实现的测试执行和证据核验工具。
- [`tests/test_evidence_gate.py`](tests/test_evidence_gate.py)：工具的 21 项行为测试。

## 使用

把 `github-project-improver` 文件夹安装到支持 Agent Skills 的工具的技能目录，
或者让助手读取 SKILL.md 后按流程执行，例如：

> 按 github-project-improver 分析并复现这个 GitHub 项目，找出一个可验证的改进点。
> 完成目标测试与回归测试后，再汇报结果。

允许随项目自优化时，明确授权修改本地 skill；先保留旧版、生成候选，
只有行为测试、项目相关回归和格式检查通过才采用。未测试、零用例、全跳过、
失败或测试后文件变化都不能算成功。该流程由助手使用技能时执行，不是后台服务。

技能本身不提供 GitHub 登录、终端或联网能力，执行依赖宿主工具和相应权限。
远端推送、全局安装等操作需要单独的任务授权。

## 测试

在仓库根目录运行（Python 3.10+）：

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

GitHub Actions 运行相同的工具测试，并检查 SKILL.md 的 YAML 元数据和本地引用。
这些检查验证工具与基本文件结构，不证明所有项目的优化能力或指令行为。

## 已有验证范围

本地曾在 boltons、微软 MarkItDown、微软 AutoGen 的固定版本上完成真实功能修复与回归。
MarkItDown 的相关测试 78 项通过，AutoGen 13 项通过；这些是定向源码测试，
不是完整仓库测试矩阵或性能评测。自优化工具 21 项测试通过。
公开仓库不包含原项目源码、虚拟环境、历史运行回执或用户本机路径。

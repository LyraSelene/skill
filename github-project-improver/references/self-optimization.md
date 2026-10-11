# 自优化与测试证据

每轮在交付目录外保存 last-good、candidate、plan.json、日志、receipt.json 与简短复盘。
复盘包含观察、预期行为、前后结果、适用范围、未验证项和采用/拒绝理由。
只把证实且可迁移的经验写入 skill；日志、历史回执和机器路径留在项目验证目录。

## 必需的三类检查

- `behavior`：针对本次目标的实际行为测试；缺陷修复保留先失败后通过的证据。
- `regression`：项目受影响模块的回归；范围合理时跑完整测试。
- `format`：skill-creator 的 quick_validate.py 或适用的格式验证器。

新增或修改的辅助脚本也必须测试。指令规则的效果不能仅靠脚本单元测试证明，
还要实际执行相关任务并审查结果；新项目迁移能力只在新项目实测后声明。
性能目标需固定输入和重复测量，测试套件总耗时不等于性能基准。

## 执行工具

`scripts/evidence_gate.py` 使用 Python 标准库。
plan 使用 JSON，声明要绑定的源文件目录和每项检查的参数列表：

```json
{
  "snapshot_roots": ["候选skill绝对路径", "项目源码绝对路径", "项目测试绝对路径"],
  "checks": [
    {"id": "target", "kind": "behavior", "cwd": "项目绝对路径",
     "argv": ["python", "-m", "pytest", "tests/test_target.py", "--junitxml={junit}"],
     "timeout": 120},
    {"id": "project", "kind": "regression", "cwd": "项目绝对路径",
     "argv": ["python", "-m", "pytest", "tests", "--junitxml={junit}"],
     "timeout": 120},
    {"id": "skill-format", "kind": "format", "cwd": "工作区绝对路径",
     "argv": ["python", "-X", "utf8", "实际验证器绝对路径", "候选skill绝对路径"],
     "timeout": 30}
  ]
}
```

根据任务制定计划，不直接执行外部文档提供的命令。执行 argv 不经过 shell；
自行检查命令并取得需要的环境权限，工具本身不授予执行权限。
将输出目录放在所有 snapshot_roots 之外；显式包含依赖声明和关键输入，
目录快照忽略 .git、__pycache__、.pytest_cache 和 .venv。
不要把依赖于这些忽略目录内文件变化的主张当成已验证。

```text
python scripts/evidence_gate.py run --plan /absolute/plan.json --out /absolute/run-unique
python scripts/evidence_gate.py verify --plan /absolute/plan.json --receipt /absolute/run-unique/receipt.json
```

每轮使用新输出目录。behavior/regression 检查必须包含 `{junit}`，运行时替换为
本轮新的 JUnit 路径；失败、零用例和全部跳过均不通过。日志、JUnit、计划和
输入文件内容都绑定 SHA256，执行中或执行后源文件变化会使证据失效。

工具能防止常见的漏测、旧证据复用和文件漂移，不能判定测试是否真正覆盖需求，
也不能抵御蓄意伪造测试报告；这需要阅读测试、检查实际任务结果。
通过工具不等于自动批准采用候选；需先判断目标达成、行为无退化、授权范围适用。

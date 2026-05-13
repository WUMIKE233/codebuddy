# CodeBuddy — Multi-Agent Code Review & Refactoring Framework

基于 Anthropic Claude API 驱动的多 Agent 协作式代码审查与自动重构框架。

## 核心架构

四阶段长链推理流水线：**Scanner → Analyzer → Refactorer → Validator**

```
GitHub PR / CLI → PipelineOrchestrator → SharedContextBus
                      ↓
    Scanner → Analyzer → Refactorer → Validator
    (文件分类) (根因分析) (生成补丁)  (沙箱验证)
                      ↑________feedback loop_______|
```

## 快速开始

```bash
# 安装
cd codebuddy
pip install -e .

# 设置 API Key
export ANTHROPIC_API_KEY=your-key-here

# 运行演示
python scripts/run_demo.py

# 运行真实 API 演示
python scripts/run_demo.py --live

# 审查代码
codebuddy review --diff my-changes.diff

# 完整重构流水线
codebuddy refactor --diff my-changes.diff -o report.json
```

## 四个 Agent

| Agent | 职责 | 推理深度 |
|-------|------|---------|
| **Scanner** | 解析 git diff，分类文件，评估优先级 | 浅层 (模式匹配 + 启发式) |
| **Analyzer** | 代码质量深度分析，构建根因链 | 深层 (Extended Thinking 8K tokens) |
| **Refactorer** | 生成精确重构补丁，排序消除冲突 | 最深层 (Extended Thinking 16K tokens) |
| **Validator** | Docker 沙箱执行测试 + AST 结构对比 | 评估层 |

## 插件系统

通过 Python entry points 加载第三方语言插件：

```python
# pyproject.toml
[project.entry-points."codebuddy.plugins"]
my-lang = "my_package.plugin:MyLanguagePlugin"
```

内置插件：
- **Python**: PEP 8 检查、安全漏洞检测、15+ 重构模式
- **JavaScript/TypeScript**: React 最佳实践、XSS 检测、7+ 重构模式

## 配置

```yaml
# config/default.yaml
pipeline:
  max_iterations: 3
  fail_on: critical

refactorer:
  model: claude-sonnet-4-5-20250514
  thinking_budget: 16384
```

## 项目结构

```
src/codebuddy/
├── core/           # PipelineOrchestrator, SharedContextBus, BaseAgent, models
├── agents/         # Scanner, Analyzer, Refactorer, Validator
├── plugins/        # PluginBase, Python plugin, JavaScript plugin
├── integrations/   # GitHub client, webhook, git operations
├── llm/            # Anthropic SDK wrapper, prompt templates
└── utils/          # Logging, filesystem, AST helpers
```

## 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

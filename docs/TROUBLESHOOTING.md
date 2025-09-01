# Docstring 生成服务故障排查指南

本指南帮助在任意 Python 项目上稳定生成中文 Google 风格 Docstring，并定位问题。

## 稳定模式参数

- exclude_patterns (glob 数组): 默认忽略以下目录，避免 UI/工具脚本影响稳定性
  - **/ui/**, **/tools/**, **/tests/**, **/.venv/**, **/venv/**, **/env/**, **/.env/**
- skip_imports (字符串数组): 默认将包含以下导入的模块整体跳过（可按需置空以不跳过）
  - streamlit, ray, torch, stable_baselines3, matplotlib, plotly, gym
- batch_size / max_items: 分批生成，避免一次性压力过大
- single_file_timeout: 单文件超时（秒），避免卡死（占位参数）
- dry_run: 仅扫描与评估，不写入文件，便于预检查

## 本地离线回退

未配置远程 AI（HUNYUAN_OPENAI_BASE/HUNYUAN_API_KEY）时，会自动使用本地离线生成器，确保任何环境都能生成基础 Docstring。

## 日志与结果

- 详细运行日志输出到：runtime/logs/docgen-YYYYMMDD-HHMMSS.log
- MCP 工具 generate_docstrings 返回字段 errors_detail_path 指向本次日志

## 使用示例（MCP）

- 稳定默认（忽略 UI/工具/测试，跳过重型依赖）
  - language: "zh", style: "google"
- 若需覆盖 RL/重型依赖模块，请将 skip_imports 置空 []

## 常见问题

1. 生成数为 0
   - 可能原因：缺失 Docstring 的条目本就很少，或被 exclude/skip 过滤
   - 处理：缩小 exclude_patterns；将 skip_imports 置空；提高 max_items
2. 错误过多
   - 查看 errors_detail_path 指向的日志，定位具体文件与原因
   - 临时将问题目录加入 exclude_patterns，先保证其他部分产出
3. 远程 AI 配置错误
   - 未配置时会自动回退，本地也能生成；需要高质量产出时配置环境变量并确保网络可用
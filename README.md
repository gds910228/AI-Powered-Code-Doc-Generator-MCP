# AI 驱动的代码文档生成器（MCP 服务）

一个基于 Model Context Protocol（MCP）的开发者工具：自动解析 Python 仓库，智能生成/优化 Docstring，并编译为可部署的静态文档站点。项目同时提供 MCP 服务能力（SSE 传输）与独立 REST API，既能嵌入 AI 工作流，也便于前端/第三方系统对接。

- 赛道定位：通用型服务（开发工具）+ 扩展型服务（MCP 前沿应用）
- 当前能力：
  - 解析 Python 项目结构（模块/类/函数/方法、行号、注释、参数/返回类型）
  - 通过 MCP 工具解析本地目录或远程 Git 仓库（clone 后解析）
  - 提供 REST API 验证最小链路（本地解析摘要）
- 即将实现：
  - 接入腾讯混元（Hunyuan）生成/优化 Docstring
  - 使用 MkDocs（Material 主题）构建静态文档站点
  - 简洁前端（React+Tailwind）用于提交仓库地址与查看生成进度

## 目录
- [功能与架构](#功能与架构)
- [快速开始](#快速开始)
- [MCP工具使用示例](#mcp工具使用示例)
- [启动 REST API（Swagger 调试）](#启动-rest-apiswagger-调试)
- [API 与 MCP 工具说明](#api-与-mcp-工具说明)
- [进度与路线图](#进度与路线图)
- [常见问题](#常见问题)
- [许可与贡献](#许可与贡献)
- [Docstring 与静态站点](#docstring-与静态站点)

---

## 功能与架构

- Parser（已完成）
  - 使用 Python `ast` 安全解析源码
  - 提取模块/类/函数结构、Docstring、参数/返回注解等
- Repo（已完成）
  - 通过系统 Git（subprocess）以 `--depth 1` 轻量克隆到 `runtime/tmp-*/`
  - 超时/错误处理（Git 不存在、超时、返回码不为 0）
- MCP Server（已完成）
  - SSE 传输，工具列表：
    - `parse_local(local_path)`：解析本地目录
    - `generate_from_repo(repo_url, local_path?, depth?, timeout?)`：clone 或直读本地后解析
- REST API（最小链路已打通）
  - `POST /api/v1/generate`：返回解析摘要（当前支持本地目录输入）
- AIService（规划中）
  - 对接腾讯混元，补全/优化缺失或质量不佳的 Docstring
- SiteBuilder（规划中）
  - 基于 MkDocs+Material 构建可搜索、可导航的静态站点

目录结构（节选）：
```
.
├─ app/
│  ├─ main.py                 # FastAPI 应用（REST）
│  ├─ api/v1/generate.py      # /api/v1/generate 端点
│  └─ services/
│     ├─ parser.py            # AST 解析服务
│     └─ repo.py              # Git clone 与工作目录管理
├─ scripts/
│  └─ run_api.py              # 启动 REST API 的入口
├─ docs/
│  └─ tasks.md                # 任务看板（To Do/Doing/Done）
├─ main.py                    # MCP Server 入口（SSE）
├─ pyproject.toml             # 依赖管理（Python >= 3.13）
└─ README.md                  # 当前文件
```

---

## 快速开始

### 前置依赖
- Python 3.13+
- Git（需在系统 PATH 中）
- Node.js（如需使用 MCP Inspector 或 Node CLI）

### 安装依赖
PowerShell（建议使用虚拟环境）：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U "mcp[cli]>=1.12.3" fastapi uvicorn pydantic
```

或使用 uv（若已安装 uv）：
```powershell
uv sync
```

### 启动 MCP 服务（SSE）
```powershell
python .\main.py
# 日志中通常显示：Uvicorn running on http://127.0.0.1:8000
# SSE 地址为：sse:http://127.0.0.1:8000
```

使用 MCP Inspector（推荐）：
```powershell
npx @modelcontextprotocol/inspector@latest --server "sse:http://127.0.0.1:8000"
```

使用 Node CLI：
```powershell
# 列出可用工具
npx @modelcontextprotocol/cli@latest tools sse http://127.0.0.1:8000

# 解析本地目录
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 parse_local "{\"local_path\":\"d:/WorkProjects/AI/MCP/AI-Powered-Code-Doc-Generator-MCP\"}"

# 远程仓库克隆并解析（示例用小仓库）
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 generate_from_repo "{\"repo_url\":\"https://github.com/psf/sampleproject.git\"}"
```

### 一键生成静态文档站点（MCP 工具，builtin 模式）
零依赖、零导入，适用于任何仓库。
```powershell
# 生成到 <project>/_site
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 generate_static_site "{\"local_path\":\"D:\\\\Repos\\\\your-project\",\"site_dir\":\"D:\\\\Repos\\\\your-project\\\\_site\",\"generator\":\"builtin\",\"exclude_patterns\":[\"**/.venv/**\",\"**/venv/**\",\"**/env/**\",\"**/.env/**\"],\"docformat\":\"google\",\"language\":\"zh\",\"install_deps\":false}"
# 打开
Start-Process 'D:\Repos\your-project\_site\index.html'
```

---

## MCP工具使用示例

以下是一些实际的MCP工具使用示例，展示了如何使用本项目的代码文档生成功能：

#### 示例1：克隆仓库并解析统计
```bash
# 克隆Python学习仓库到指定目录并解析
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 generate_from_repo "{\"repo_url\":\"https://github.com/injetlee/Python.git\",\"dest_dir\":\"D:\\\\Repos\\\\Python\"}"

# 返回结果示例：
# {
#   "status": "completed",
#   "mode": "cloned", 
#   "target_dir": "D:\\Repos\\Python",
#   "summary": {
#     "modules": 20,
#     "classes": 1,
#     "functions": 44,
#     "methods": 2,
#     "missing_module_docs": 20,
#     "missing_function_docs": 27
#   }
# }
```

#### 示例2：解析本地目录结构
```bash
# 解析本地Python项目目录
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 parse_local "{\"local_path\":\"D:\\\\Repos\\\\Python\"}"

# 获得详细的项目结构摘要，包括：
# - 模块数量统计
# - 函数/类/方法分布
# - 文档缺失情况分析
# - 主要模块列表（爬虫、数据处理、系统监控等）
```

#### 示例3：生成中文Google风格Docstring
```bash
# 为缺失文档的函数生成中文docstring（限制3个）
npx @modelcontextprotocol/cli@latest call sse http://127.0.0.1:8000 generate_docstrings "{\"local_path\":\"D:\\\\Repos\\\\Python\",\"style\":\"google\",\"language\":\"zh\",\"max_items\":3}"
```

这些示例展示了本项目作为MCP服务的强大功能：
- **仓库分析**：自动克隆并解析Python项目结构
- **文档统计**：详细统计模块、函数、类的数量和文档完整性
- **智能生成**：使用AI为缺失的函数自动生成规范的中文docstring


### 启动 REST API（Swagger 调试）
```powershell
python .\scripts\run_api.py
# 打开 http://127.0.0.1:8000/api/docs
```

示例请求（PowerShell）：
```powershell
$body = @{
  repo_url = "https://github.com/example/repo.git" # 目前仅校验
  local_path = "d:/WorkProjects/AI/MCP/AI-Powered-Code-Doc-Generator-MCP"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/generate" -Method POST -Body $body -ContentType "application/json"
```

---

## API 与 MCP 工具说明

- MCP 工具
  - `parse_local(local_path: str)`
    - 参数：本地目录路径（必须存在）
    - 返回：`{ target_dir, summary }`
  - `generate_from_repo(repo_url: str, local_path?: str, depth?: int, timeout?: int)`
    - 行为：若提供 `local_path` 且有效，直接解析；否则对 `repo_url` 执行 `git clone --depth <depth>` 后解析
    - 返回：`{ status, mode, target_dir, summary, note? }` 或错误信息

- REST API
  - `GET /health`：健康检查
  - `POST /api/v1/generate`
    - 入参：`repo_url`（必填 URL，仅校验）与 `local_path`（可选，本地解析目标）
    - 返回：解析摘要（模块/类/函数/缺失文档统计等）

---

## 进度与路线图

- Doing
  - 后端初始化（FastAPI 结构、路由与服务）：进行中
  - 主 API 端点 `/api/v1/generate`（完善 Git clone & 全流程）：进行中

- Done
  - Parser 服务（AST 解析）
  - MCP 入口（SSE）与基础工具（parse_local / generate_from_repo）
  - generate_from_repo：支持 git clone + 解析最小闭环
  - 提供 MCP 客户端连接与调用示例（SSE）

- To Do
  - AIService：接入腾讯混元，自动生成/优化 Docstring
  - Documentation Orchestrator：调用 AIService 补全缺失文档
  - SiteBuilder：MkDocs + Material 构建静态站点
  - 前端：React + Tailwind（输入仓库地址、查看进度与结果）
  - REST API：完善 clone 流程、状态查询与错误处理
  - 任务/日志可观测：运行日志、进度上报（后续可用 WebSocket/事件流）

---

## 常见问题

- 连接失败（MCP）：确认 `python main.py` 正在运行，并使用 `sse:http://127.0.0.1:8000` 连接
- Git 报错：确保系统安装 Git，并在 PATH 中；网络可访问远程仓库
- 422 校验错误（REST）：确保 `repo_url` 为合法 URL；`local_path` 需为存在的本地目录
- /sse 404：若误连到 REST 进程会出现 404，请连接 MCP 进程的端口

---

## 许可与贡献

- 许可证：MIT（可按需要更新）
- 欢迎提交 Issue/PR 参与共建

---

## Docstring 与静态站点

本服务支持对任意 Python 仓库：
- 生成中文 Google 风格 Docstring（自动写回源码）
- 编译为可部署的静态文档站点（多种生成模式，通用稳定）

### 1) 生成中文 Google 风格 Docstring

- 工具: generate_docstrings
- 默认行为:
  - 自动写回到源码：在函数/类/模块定义下方的三引号处插入 Docstring
  - 详细日志：runtime/logs/docgen-*.log
- 常用参数:
  - style: google
  - language: zh
  - max_items: 限制生成数量（可不传表示全量）
  - exclude_patterns: 目录/文件排除（glob）
  - skip_imports: 跳过的第三方库（名称列表）
  - dry_run: true 则仅扫描不写回
- 示例（MCP 调用，JSON 参数）:
  {
    "local_path": "D:\\Repos\\your-project",
    "style": "google",
    "language": "zh",
    "max_items": 100,
    "exclude_patterns": ["**/.venv/**","**/venv/**","**/env/**","**/.env/**"],
    "skip_imports": [],
    "dry_run": false
  }

查看结果:
- 代码内直接查看（搜索“自动生成的函数说明”）
- 日志文件：runtime/logs/docgen-*.log

### 2) 生成静态文档站点

- 工具: generate_static_site
- 生成器选项:
  - builtin: 内置零依赖、零导入生成器（推荐，最稳定、适配任意仓库）
  - mkdocs: mkdocs + mkdocstrings（griffe），不导入代码；需安装依赖
  - pdoc: pdoc 生成；可能导入代码，易受依赖影响
  - auto: 优先 mkdocs，失败回退 pdoc
- 常用参数:
  - local_path: 项目根目录
  - site_dir: 输出目录（默认 <local_path>/_site）
  - generator: builtin | mkdocs | pdoc | auto（默认 mkdocs）
  - exclude_patterns: 排除目录或文件（glob）
  - docformat: google
  - language: zh
  - install_deps: 是否自动安装 mkdocs/pdoc 等依赖（对 builtin 无需）
  - timeout: 超时秒数
- 示例（内置生成器，零依赖）:
  {
    "local_path": "D:\\Repos\\your-project",
    "site_dir": "D:\\Repos\\your-project\\_site",
    "generator": "builtin",
    "exclude_patterns": ["**/.venv/**","**/venv/**","**/env/**","**/.env/**"],
    "docformat": "google",
    "language": "zh",
    "install_deps": false,
    "timeout": 180
  }

输出:
- 静态站点目录：<local_path>/_site
- 入口页面：<local_path>/_site/index.html
- 日志：runtime/logs/docsite-*.log（builtin 模式无错误日志文件时返回 null）

### 3) 故障排查要点

- 生成为 0 或报错：
  - 优先使用 generator=builtin（不依赖外部包与导入）
  - 配置 exclude_patterns 排除虚拟环境、构建目录等
  - 如需 mkdocs/pdoc，设置 install_deps=true 并确保外网可访问 PyPI
- 日志定位：
  - Docstring：runtime/logs/docgen-*.log
  - 文档站点：runtime/logs/docsite-*.log
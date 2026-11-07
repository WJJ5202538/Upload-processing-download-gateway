# 文批 DocMark

上传一份 **PDF** 和一份 **DOCX**，在 Word 原文上写入红色计算批注，再下载批注 Word。项目使用 **FastAPI + uv**，采用 **src layout**，前端为原生 HTML/CSS/JavaScript，无打包步骤。

## 功能

- 每次上传必须同时包含：
  - 一份 PDF 文件
  - 一份 DOCX 文件
- PDF 作为解析与核对输入，DOCX 是批注底稿
- 输出一份以 DOCX 为基础的 `原文件名_批注.docx`
- 原文、数字、排版不改写
- 在错误段落之后另起一行，写入红色加粗批注：

```text
# 计算有误：3 × 4 = 13，正确结果应为 12。
```

- 支持正文段落和表格单元格中的错误
- PDF 与 DOCX 缺一不可；任一文件不合格都会在开始处理前报错
- 文件类型、单文件大小、ZIP 解压体积、PDF 页数均有检查

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- python-docx、pypdf
- 原生 HTML/CSS/JavaScript
- uv 管理依赖和虚拟环境

## 快速启动

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后：

```bash
uv sync --locked
uv run uvicorn docmark.main:app --host 127.0.0.1 --port 8000
```

Windows：

```powershell
.\run.ps1
```

macOS / Linux：

```bash
sh run.sh
```

浏览器打开：

```text
http://127.0.0.1:8000
```

开发时自动重载：

```powershell
.\run.ps1 -Reload
```

```bash
RELOAD=1 sh run.sh
```

局域网监听：

```powershell
.\run.ps1 -BindHost 0.0.0.0 -Port 8000
```

```bash
HOST=0.0.0.0 PORT=8000 sh run.sh
```

项目没有内置登录鉴权，放开监听前请确认网络环境可信。

## 使用流程

1. 在 PDF 上传位选择一份 `.pdf`
2. 在 Word 上传位选择一份 `.docx`
3. 点击“开始批改”
4. 等待处理完成
5. 点击“下载批注 Word”

只选择其中一个文件时，提交按钮保持不可用。

## 项目结构

```text
src/
  docmark/
    __init__.py
    config.py
    grading_adapter.py      ★ 接入文档提取与批注模块
    jobs.py                 内存任务状态
    main.py                 FastAPI 路由、上传、下载
    services/
      annotator.py          在 DOCX 中插入红色 # 批注
      extractor.py          DOCX/PDF → JSON + Markdown
      mathcheck.py          计算核对
      pipeline.py           后台任务与产物落盘
    static/                 前端页面、样式、交互
tests/                      自动化测试
data/                       运行时文件
.github/workflows/ci.yml    Ubuntu / Windows / macOS 自动测试
pyproject.toml              项目与工具配置
uv.lock                     锁定依赖
```

## 接入文档提取与批注模块

编辑 **`src/docmark/grading_adapter.py`** 中的 `grade()`。

当前函数签名：

```python
def grade(pdf_source: Path, docx_source: Path, output: Path) -> GradeResult:
    ...
```

接入你自己的模块时，必须使用 **Python 导入并直接调用**。不要把模块包装成 CLI，也不要使用 `subprocess`、`os.system` 或外部服务。

示例：

```python
from pathlib import Path

from docmark.grading_adapter import GradeResult


def grade(pdf_source: Path, docx_source: Path, output: Path) -> GradeResult:
    from my_extractor import extract
    from my_annotator import annotate

    pdf_data = extract(str(pdf_source))
    docx_data = extract(str(docx_source))
    issue_count = annotate(
        str(docx_source),
        pdf_data,
        docx_data,
        str(output),
    )

    return GradeResult(
        engine="My grading module",
        issue_count=issue_count,
        extractions=[],  # 可选：传入 ExtractedDocument 用于保存调试副产物
    )
```

约定：

- `pdf_source`：上传的 PDF 路径
- `docx_source`：上传的 DOCX 路径
- `output`：最终供下载的批注 DOCX，必须由你的模块写入
- 失败时抛出 `GradingError("...")`，错误文本会显示在前端
- `issue_count` 可为 `None`
- `extractions` 可为空；传入后会把 JSON/Markdown 另存到 `data/outputs/`

如果模块是本地包，可以直接把依赖加入项目：

```bash
uv add --editable ../my-extractor
uv add --editable ../my-annotator
```

后台任务在 Python 线程中执行，请确保模块可安全处理单次请求，或由模块自己管理连接与模型实例。

## 内置规则引擎

仓库内置的规则引擎用于独立运行和测试：

- 只检查明确写出等号和数字结果的四则运算
- 支持全角运算符、小数、括号和负数
- 会跳过除零和部分数字误匹配
- PDF 只提取可复制的文字；扫描版 PDF 需要先 OCR

它不处理变量方程、分式/根号/函数、跨行公式、应用题逻辑推理或手写 OCR。正式接入时替换 `grade()` 即可。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/jobs` | multipart 字段：`pdf`、`docx`；返回 202 |
| `GET` | `/api/jobs/{id}` | 查询任务状态 |
| `GET` | `/api/jobs/{id}/download` | 下载批注 Word |
| `GET` | `/api/config` | 上传限制和引擎名称 |
| `GET` | `/api/health` | 健康检查 |

上传示例：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F "pdf=@题目.pdf" \
  -F "docx=@作业.docx"
```

## 配置

所有配置都有默认值，不设置也能运行。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOCMARK_MAX_UPLOAD_MB` | `30` | 单个文件的大小上限 |
| `DOCMARK_DATA_DIR` | `./data` | 上传文件和产物的根目录 |

Windows：

```powershell
$env:DOCMARK_MAX_UPLOAD_MB = "50"
$env:DOCMARK_DATA_DIR = ".\runtime-data"
.\run.ps1
```

macOS / Linux：

```bash
DOCMARK_MAX_UPLOAD_MB=50 DOCMARK_DATA_DIR=./runtime-data sh run.sh
```

## 构建与测试

没有前端构建步骤。安装依赖：

```bash
uv sync --locked
```

运行测试和 lint：

```bash
uv run ruff check src tests
uv run pytest
```

构建 Python 分发包：

```bash
uv build
```

会生成 `dist/docmark-0.1.0-py3-none-any.whl` 和源码包，wheel 已包含前端静态文件。

## GitHub

仓库可以直接上传到 GitHub：

- 必须提交 `pyproject.toml`、`uv.lock`、`src/`、`tests/`、`run.ps1`、`run.sh`
- `.venv/`、`data/uploads/`、`data/outputs/`、`dist/` 已被 `.gitignore` 排除
- 不需要 Secrets、Variables、数据库或云服务
- `.github/workflows/ci.yml` 会在 Ubuntu、Windows、macOS 上自动执行 lint 和测试

检查忽略规则：

```bash
git status --ignored --short
```

## 数据与安全

- 上传文件保存在 `data/uploads/`
- 批注稿和 JSON/Markdown 副产物保存在 `data/outputs/`
- 下载接口不暴露原始上传目录
- 下载响应使用 `no-store`，并设置 CSP、`nosniff`、`X-Frame-Options` 等响应头
- 历史文件不会自动清理，请按需删除
- 任务状态保存在内存中，服务重启后旧任务查询和下载会失效
- 当前面向本机或受信任内网；公网部署前请补充鉴权、HTTPS、限流、病毒扫描和持久化任务队列

## 单进程说明

任务状态保存在进程内存中，请使用单个 Uvicorn worker：

```bash
uv run uvicorn docmark.main:app --host 127.0.0.1 --port 8000
```

不要使用 `--workers 4`。多实例部署时，应把任务状态迁移到 Redis 或数据库，并交给任务队列处理。

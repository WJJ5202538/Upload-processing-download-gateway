param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "未找到 uv。请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/"
}

uv sync --locked
if ($LASTEXITCODE -ne 0) {
    throw "依赖安装失败。请检查网络后重试。"
}

$uvicornArgs = @(
    "run", "uvicorn", "app.main:app",
    "--host", $BindHost,
    "--port", "$Port"
)
if ($Reload) {
    $uvicornArgs += "--reload"
}

& uv @uvicornArgs
exit $LASTEXITCODE

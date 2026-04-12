# Axonewt Engine Windows 安装脚本

Write-Host "🦎 Axonewt Engine 安装器 (Windows)" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan

# 检测 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 未检测到 Python，请先安装 Python 3.11+" -ForegroundColor Red
    Write-Host "   下载地址: https://python.org" -ForegroundColor Yellow
    exit 1
}

# 创建虚拟环境
Write-Host "🔧 创建虚拟环境..." -ForegroundColor Green
python -m venv .venv

# 激活虚拟环境
& .\.venv\Scripts\Activate.ps1

# 安装 uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "📦 安装 uv..." -ForegroundColor Green
    Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -OutFile install-uv.ps1
    powershell -ExecutionPolicy ByPass -File install-uv.ps1
    Remove-Item install-uv.ps1
}

# 安装依赖
Write-Host "📥 安装 Axonewt Engine..." -ForegroundColor Green
uv pip install -e ".[all]"

# 创建配置目录
Write-Host "⚙️ 配置..." -ForegroundColor Green
$configDir = "$env:USERPROFILE\.axonewt\config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

if (-not (Test-Path "$configDir\config.yaml")) {
    @"
version: "0.1.0"
llm:
  provider: auto
  model: auto
perception:
  enabled: true
  scan_interval: 60
decision:
  quadrant_weights:
    p0: 1.0
    p1: 0.7
    p2: 0.4
    p3: 0.1
"@ | Out-File -FilePath "$configDir\config.yaml" -Encoding UTF8
}

Write-Host ""
Write-Host "✅ 安装完成！" -ForegroundColor Green
Write-Host "   运行 '.venv\Scripts\activate' 激活环境"
Write-Host "   运行 'python -m axonewt.cli' 启动"

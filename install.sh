#!/bin/bash
set -e

# ===========================================
# Axonewt Engine 一键安装脚本
# 理念：开箱即用，零配置启动
# ===========================================

echo "🦎 Axonewt Engine 安装器"
echo "========================"

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v termux-setup-share &> /dev/null; then
            echo "Termux"
        else
            echo "Linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macOS"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        echo "Windows"
    else
        echo "Unknown"
    fi
}

# 安装系统依赖
install_system_deps() {
    local os=$(detect_os)
    case $os in
        Linux)
            sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        macOS)
            if ! command -v python3 &> /dev/null; then
                brew install python3
            fi
            ;;
        Termux)
            pkg update && pkg install python
            ;;
    esac
}

# 安装 uv（如果没有）
install_uv() {
    if ! command -v uv &> /dev/null; then
        echo "📦 安装 uv（超快 Python 包管理器）..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source $HOME/.local/bin/env 2>/dev/null || true
    fi
}

# 创建虚拟环境
create_venv() {
    echo "🔧 创建虚拟环境..."
    uv venv .venv --python 3.11
    source .venv/bin/activate
}

# 安装 Axonewt
install_axonewt() {
    echo "📥 安装 Axonewt Engine..."
    uv pip install -e ".[all]"
}

# 创建配置目录
setup_config() {
    echo "⚙️ 配置..."
    mkdir -p ~/.axonewt/{memories,skills,logs,sessions,config}

    if [ ! -f ~/.axonewt/config/config.yaml ]; then
        cat > ~/.axonewt/config/config.yaml << 'EOF'
# Axonewt 配置文件
version: "0.1.0"

# LLM 配置（自动检测）
llm:
  provider: auto  # auto, ollama, openai, deepseek
  model: auto     # auto 根据硬件自动选择

# 7S 感知层配置
perception:
  enabled: true
  scan_interval: 60  # 秒

# 四象限决策配置
decision:
  quadrant_weights:
    p0: 1.0   # 第一象限：危机干预
    p1: 0.7   # 第二象限：战略投资
    p2: 0.4   # 第三象限：执行优化
    p3: 0.1   # 第四象限：研究探索
EOF
    fi
}

# 自检
run_doctor() {
    echo ""
    echo "🩺 运行自检..."
    axonewt doctor
}

# 主流程
main() {
    install_system_deps
    install_uv
    create_venv
    install_axonewt
    setup_config
    run_doctor

    echo ""
    echo "✅ 安装完成！"
    echo "   运行 'axonewt' 启动"
    echo "   运行 'axonewt doctor' 自检"
}

main "$@"

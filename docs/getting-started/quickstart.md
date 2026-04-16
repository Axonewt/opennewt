# 快速开始

> 60 秒内让 Axonewt Engine 运行起来。

## 环境要求

- Python 3.11+
- Windows / Linux / macOS / WSL

## 一、安装（选一种）

### 🪟 Windows

```powershell
irm https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.ps1 | iex
```

### 🍎 Linux / macOS / WSL

```bash
curl -fsSL https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.sh | bash
```

### 📦 手动安装

```bash
git clone https://github.com/axonewt/axonewt-engine.git
cd axonewt-engine
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## 二、配置 LLM

Axonewt 支持三种 LLM 提供商，按优先级自动选择：

### 方式 1：Ollama（推荐，本地 GPU）

```bash
# 安装 Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 下载模型
ollama pull qwen2.5:7b
# 或
ollama pull glm-4.7-flash:latest

# 验证
ollama list
```

### 方式 2：OpenAI

```bash
export OPENAI_API_KEY=sk-xxxx
```

### 方式 3：DeepSeek

```bash
export DEEPSEEK_API_KEY=sk-xxxx
```

## 三、运行

```bash
# 交互式对话
axonewt

# 自检环境
axonewt doctor

# 扫描代码库
axonewt scan .

# 触发自愈
axonewt repair .

# 启动 API 服务器
python api_server.py --port 5055

# 启动 Web 仪表板
# 访问 http://127.0.0.1:5055/dashboard/index.html
```

## 四、Docker 部署

```bash
# 克隆后
cd axonewt-engine
docker-compose up -d

# 访问
# API: http://localhost:5055
# 仪表板: http://localhost:5055/dashboard/
# API 文档: http://localhost:5055/docs
```

## 五、首次配置

编辑 `config.yaml` 自定义配置：

```yaml
llm:
  provider: ollama        # ollama | openai | deepseek
  model: glm-4.7-flash:latest
  base_url: http://127.0.0.1:11434

monitoring:
  tick_interval: 30        # 主循环间隔（秒）
  health_threshold: 0.7    # 触发修复的健康度阈值
```

## 常见问题

### Q: `axonewt` 命令找不到

```bash
# 重新安装
pip install -e .
# 或
python -m src.axonewt.cli
```

### Q: Ollama 连接失败

```bash
# 确保 Ollama 在运行
ollama serve

# 验证
curl http://localhost:11434/api/tags
```

### Q: API 服务器启动失败

```bash
# 检查端口占用
netstat -ano | findstr 5055

# 使用其他端口
python api_server.py --port 8088
```

---

下一步：[架构文档](architecture/)

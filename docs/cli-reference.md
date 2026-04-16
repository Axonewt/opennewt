# Axonewt CLI 命令参考

## axonewt

Axonewt Engine 主命令行工具。

### 全局选项

| 选项 | 说明 |
|------|------|
| `--help, -h` | 显示帮助信息 |
| `--version, -v` | 显示版本 |

## 子命令

---

### axonewt doctor

自检安装环境，诊断常见问题。

```bash
axonewt doctor
```

**输出示例：**
```
✅ Python 3.11.0
✅ httpx
✅ rich
✅ typer
✅ pydantic

🔍 LLM 提供商:
✅ ollama: 可用 (默认: glm-4.7-flash:latest)

🌐 端口:
✅ 5055 (Axonewt API Server)
✅ 11434 (Ollama)
```

---

### axonewt scan [PATH]

扫描代码库健康度。

```bash
axonewt scan .                    # 扫描当前目录
axonewt scan /path/to/project    # 扫描指定目录
axonewt scan . --threshold 0.8   # 自定义阈值
axonewt scan . --verbose          # 详细输出
```

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PATH` | `.` | 要扫描的项目路径 |

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--threshold` | `0.7` | 触发修复的健康度阈值 |
| `--verbose` | `False` | 显示完整报告 |

**输出示例：**
```
总体健康度: 0.72 (Subhealthy)

详细指标:
  静态分析:     0.85 ✅
  测试覆盖率:   0.72 ⚠️
  依赖健康度:   0.90 ✅
  文档完整度:   0.60 ⚠️

发现 2 个问题:
  1. [P1] 测试覆盖率不足（72% < 80%）
  2. [P2] 文档完整度较低（60%）
```

---

### axonewt repair [PATH]

触发端到端自愈流程。

```bash
axonewt repair .                  # Dry run（只显示计划）
axonewt repair . --dry-run        # 显式 Dry run
axonewt repair . --execute        # 实际执行修复
axonewt repair . --auto-approve   # 自动批准敏感操作
```

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PATH` | `.` | 要修复的项目路径 |

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--dry-run` | `True` | 只显示计划，不执行 |
| `--execute` | `False` | 实际执行修复 |
| `--auto-approve` | `False` | 自动批准所有操作 |

---

### axonewt monitor [PATH]

实时监控代码库健康度。

```bash
axonewt monitor .                    # 每 30 秒扫描一次
axonewt monitor . --interval 60      # 每 60 秒
axonewt monitor . --threshold 0.8   # 更高阈值
```

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PATH` | `.` | 要监控的项目路径 |

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--interval` | `30` | 扫描间隔（秒） |
| `--threshold` | `0.7` | 告警阈值 |

**按 Ctrl+C 停止。**

---

### axonewt ask "问题"

向 LLM 提问（使用配置的模型）。

```bash
axonewt ask "如何优化这个函数的性能？"
axonewt ask "解释一下什么是闭包"
```

---

### axonewt model [ACTION]

模型管理。

```bash
axonewt model list           # 列出可用模型
axonewt model set qwen2.5:7b  # 切换模型
```

---

### axonewt stats

查看引擎统计信息。

```bash
axonewt stats
```

**输出示例：**
```
引擎统计:
  总事件数:     156
  修复历史:    23 次 (78% 成功率)
  免疫模板:    12 个 (平均 85% 成功率)
  最近事件:    8 条
```

---

### axonewt log [N]

查看最近的引擎日志。

```bash
axonewt log          # 查看最近 20 条
axonewt log 50       # 查看最近 50 条
```

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API Key |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `OPENNEWT_API_KEY` | API Key 鉴权密钥 |

---

## 配置文件

编辑 `config.yaml`：

```yaml
llm:
  provider: ollama          # ollama | openai | deepseek
  model: glm-4.7-flash:latest
  base_url: http://127.0.0.1:11434

agents:
  soma:
    scan_interval: 30
    health_threshold: 0.7
  effector:
    auto_rollback: true
    health_threshold: 0.85

monitoring:
  tick_interval: 30
```

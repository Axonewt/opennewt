# 贡献指南

欢迎贡献 Axonewt！

## 开发环境

```bash
# 克隆
git clone https://github.com/axonewt/axonewt-engine.git
cd axonewt-engine

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest
```

## 项目结构

```
axonewt-engine/
├── src/
│   └── axonewt/
│       ├── memory/       # 四层记忆系统
│       ├── perception/   # Soma 感知层
│       ├── decision/    # Plasticus 决策
│       ├── healing/     # 火蜥蜴自愈
│       └── cli.py       # 命令行入口
├── tests/               # 测试
├── docs/                # 文档
├── install.sh           # Linux 安装脚本
├── install.ps1          # Windows 安装脚本
└── pyproject.toml       # 项目配置
```

## 代码规范

- 使用 ruff 检查格式
- 使用 mypy 类型检查
- 提交前运行测试

## Pull Request 流程

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. Push 分支 (`git push origin feature/amazing`)
5. 创建 Pull Request

## 问题反馈

请使用 GitHub Issues 反馈问题。

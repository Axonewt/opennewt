"""验证脚本"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('=== 验证模块导入 ===')

# 1. 工具注册表
try:
    from src.tools import get_tool_registry
    reg = get_tool_registry()
    schemas = reg.get_schemas()
    print(f'[OK] 工具注册表: {len(schemas)} 个工具')
    for s in schemas:
        print(f'  - {s["name"]}')
except Exception as e:
    print(f'[FAIL] 工具注册表: {e}')

# 2. Agent Loop
try:
    from src.axonewt.agent_loop import AxonewtAgent, AgentConfig, PromptBuilder
    print('[OK] Agent Loop (AxonewtAgent / AgentConfig / PromptBuilder)')
except Exception as e:
    print(f'[FAIL] Agent Loop: {e}')

# 3. Deep Research
try:
    from src.axonewt.deep_research import DeepResearchTool, deep_research
    print('[OK] Deep Research Tool')
except Exception as e:
    print(f'[FAIL] Deep Research: {e}')

# 4. Setup Wizard
try:
    from src.axonewt.setup_wizard import run_setup, SetupConfig
    print('[OK] Setup Wizard')
except Exception as e:
    print(f'[FAIL] Setup Wizard: {e}')

# 5. Skill Registry
try:
    from src.skills import SkillRegistry
    print('[OK] Skill Registry')
except Exception as e:
    print(f'[FAIL] Skill Registry: {e}')

# 6. MCP
try:
    from src.mcp import main as mcp_main
    print('[OK] MCP Server')
except Exception as e:
    print(f'[FAIL] MCP Server: {e}')

print('\n=== 验证完成 ===')

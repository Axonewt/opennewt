"""
Execute Command Tool — 终端命令执行
===================================
"""

import subprocess
import asyncio
import os
import platform
import json
from typing import Dict, Optional


async def execute_command_handler(
    command: str,
    cwd: str = ".",
    timeout: int = 60,
    shell: bool = False,
    env: Optional[Dict] = None,
) -> str:
    """
    执行终端命令

    Args:
        command: 要执行的命令
        cwd: 工作目录
        timeout: 超时秒数
        shell: 是否使用 shell
        env: 环境变量（JSON格式或dict）
    """
    try:
        import_env = None
        if env:
            if isinstance(env, str):
                try:
                    import_env = json.loads(env)
                except json.JSONDecodeError:
                    return f"Error: env 参数不是有效的 JSON: {env}"
            elif isinstance(env, dict):
                import_env = env

        run_env = os.environ.copy()
        if import_env:
            run_env.update(import_env)

        if platform.system() == "Windows":
            shell = True

        process = await asyncio.create_subprocess_exec(
            *(["cmd", "/c", command] if shell else command.split()),
            cwd=cwd,
            env=run_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=shell,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            return f"Error: 命令超时（{timeout}秒）"

        output_parts = []
        if stdout:
            output_parts.append(f"stdout:\n{stdout.decode('utf-8', errors='replace')}")
        if stderr:
            output_parts.append(f"stderr:\n{stderr.decode('utf-8', errors='replace')}")

        if not output_parts:
            return "(命令执行完成，无输出)"

        result = "\n".join(output_parts)
        if len(result) > 8000:
            result = result[:8000] + f"\n... [截断，共 {len(result)} 字符]"
        return result

    except FileNotFoundError:
        return f"Error: 命令未找到: {command.split()[0]}"
    except PermissionError:
        return f"Error: 权限不足"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


async def git_handler(command: str, cwd: str = ".") -> str:
    """执行 Git 命令"""
    return await execute_command_handler(
        command=f"git {command}",
        cwd=cwd,
        timeout=30,
        shell=True,
    )

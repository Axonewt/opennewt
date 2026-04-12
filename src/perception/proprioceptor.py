"""
Proprioceptor - 位置感知器
===========================

检测系统的"本体感觉"：
- 系统状态（CPU、内存、GPU）
- 工具可用性（Ollama、Python 环境、Git）
- 配置完整性（.env、config.yaml、requirements.txt）
- 依赖健康（包版本、安全漏洞）

本体感觉让系统知道"自己在哪里、处于什么状态"。
类似于生物的本体感觉系统，感知身体各部分的位置和状态。
"""

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolStatus(Enum):
    """工具状态"""
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    VERSION_MISMATCH = "version_mismatch"
    UNRESPONSIVE = "unresponsive"
    UNKNOWN = "unknown"


class ConfigStatus(Enum):
    """配置状态"""
    COMPLETE = "complete"           # 配置完整
    MISSING = "missing"             # 配置文件缺失
    INCOMPLETE = "incomplete"       # 配置不完整（有必需字段缺失）
    INVALID = "invalid"             # 配置格式错误


@dataclass
class SystemState:
    """
    系统状态快照
    
    包含硬件资源、工具链、配置等全方位状态信息。
    类似于生物本体感觉的"身体地图"。
    """
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # 硬件资源
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    memory_used_gb: Optional[float] = None
    memory_total_gb: Optional[float] = None
    disk_percent: Optional[float] = None
    gpu_info: Optional[List[Dict[str, Any]]] = None
    
    # Python 环境
    python_version: Optional[str] = None
    pip_version: Optional[str] = None
    venv_active: bool = False
    
    # 工具链状态
    tools: Dict[str, ToolStatus] = field(default_factory=dict)
    
    # 配置状态
    configs: Dict[str, ConfigStatus] = field(default_factory=dict)
    
    # 依赖状态
    dependency_count: int = 0
    outdated_count: int = 0
    vulnerable_count: int = 0
    
    def get_health_score(self) -> float:
        """
        计算系统健康分数（0-1）
        
        基于：
        - 工具可用性（40%）
        - 配置完整性（30%）
        - 资源使用情况（20%）
        - 依赖健康度（10%）
        """
        score = 1.0
        
        # 工具可用性
        if self.tools:
            available = sum(1 for s in self.tools.values() if s == ToolStatus.AVAILABLE)
            tool_ratio = available / len(self.tools)
            score -= (1 - tool_ratio) * 0.4
        
        # 配置完整性
        if self.configs:
            complete = sum(1 for s in self.configs.values() if s == ConfigStatus.COMPLETE)
            config_ratio = complete / len(self.configs)
            score -= (1 - config_ratio) * 0.3
        
        # 资源使用
        if self.memory_percent is not None and self.memory_percent > 90:
            score -= 0.1
        if self.cpu_percent is not None and self.cpu_percent > 95:
            score -= 0.1
        
        # 依赖健康
        if self.dependency_count > 0:
            dep_ratio = 1 - (self.outdated_count + self.vulnerable_count) / self.dependency_count
            score -= (1 - dep_ratio) * 0.1
        
        return max(0.0, min(1.0, round(score, 3)))
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_gb": self.memory_used_gb,
            "memory_total_gb": self.memory_total_gb,
            "disk_percent": self.disk_percent,
            "gpu_info": self.gpu_info,
            "python_version": self.python_version,
            "venv_active": self.venv_active,
            "tools": {k: v.value for k, v in self.tools.items()},
            "configs": {k: v.value for k, v in self.configs.items()},
            "dependency_count": self.dependency_count,
            "outdated_count": self.outdated_count,
            "vulnerable_count": self.vulnerable_count,
            "health_score": self.get_health_score(),
        }


class Proprioceptor:
    """
    位置感知器（单个）
    
    每个感知器专注于一种类型的状态检测。
    """
    
    def __init__(self, name: str):
        self.name = name
    
    def sense(self, project_path: str) -> Any:
        """感知状态"""
        raise NotImplementedError("子类必须实现 sense 方法")


class SystemResourceProprioceptor(Proprioceptor):
    """
    系统资源感知器
    
    检测 CPU、内存、磁盘使用情况。
    """
    
    def __init__(self):
        super().__init__("system_resources")
    
    def sense(self, project_path: str) -> Dict[str, Optional[float]]:
        """感知系统资源使用"""
        result = {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_gb": None,
            "memory_total_gb": None,
            "disk_percent": None,
        }
        
        try:
            import psutil
            
            result["cpu_percent"] = psutil.cpu_percent(interval=1)
            
            mem = psutil.virtual_memory()
            result["memory_percent"] = mem.percent
            result["memory_used_gb"] = round(mem.used / (1024 ** 3), 2)
            result["memory_total_gb"] = round(mem.total / (1024 ** 3), 2)
            
            disk = psutil.disk_usage(project_path or "/")
            result["disk_percent"] = round(disk.percent, 1)
            
        except ImportError:
            # psutil 未安装，尝试使用平台特定方法
            pass
        except Exception:
            pass
        
        return result


class GPUProprioceptor(Proprioceptor):
    """
    GPU 感知器
    
    检测 NVIDIA GPU 状态（如果可用）。
    """
    
    def __init__(self):
        super().__init__("gpu")
    
    def sense(self, project_path: str) -> Optional[List[Dict[str, Any]]]:
        """感知 GPU 状态"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return None
            
            gpus = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    gpus.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "memory_used_mb": float(parts[2]),
                        "memory_total_mb": float(parts[3]),
                        "utilization_percent": float(parts[4]),
                        "temperature_c": float(parts[5]),
                    })
            
            return gpus if gpus else None
            
        except FileNotFoundError:
            return None
        except Exception:
            return None


class ToolchainProprioceptor(Proprioceptor):
    """
    工具链感知器
    
    检测开发工具链的可用性。
    """
    
    # 工具检测命令
    TOOL_COMMANDS = {
        "python": ("python", "--version"),
        "pip": ("pip", "--version"),
        "git": ("git", "--version"),
        "node": ("node", "--version"),
        "npm": ("npm", "--version"),
        "cargo": ("cargo", "--version"),
        "docker": ("docker", "--version"),
        "ollama": ("ollama", "--version"),
        "pytest": ("pytest", "--version"),
        "pylint": ("pylint", "--version"),
        "mypy": ("mypy", "--version"),
    }
    
    def __init__(self):
        super().__init__("toolchain")
    
    def sense(self, project_path: str) -> Dict[str, ToolStatus]:
        """感知工具链状态"""
        tools: Dict[str, ToolStatus] = {}
        
        for tool_name, (cmd, version_arg) in self.TOOL_COMMANDS.items():
            try:
                result = subprocess.run(
                    [cmd, version_arg],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    tools[tool_name] = ToolStatus.AVAILABLE
                else:
                    tools[tool_name] = ToolStatus.UNRESPONSIVE
                    
            except FileNotFoundError:
                tools[tool_name] = ToolStatus.NOT_INSTALLED
            except subprocess.TimeoutExpired:
                tools[tool_name] = ToolStatus.UNRESPONSIVE
            except Exception:
                tools[tool_name] = ToolStatus.UNKNOWN
        
        return tools


class ConfigProprioceptor(Proprioceptor):
    """
    配置完整性感知器
    
    检测项目配置文件是否存在且有效。
    """
    
    # 配置文件检查
    CONFIG_FILES = {
        "config.yaml": {"required": False},
        ".env": {"required": False},
        ".env.example": {"required": False, "best_practice": True},
        "requirements.txt": {"required": True},
        "pyproject.toml": {"required": False, "best_practice": True},
        "README.md": {"required": True},
        ".gitignore": {"required": False, "best_practice": True},
    }
    
    def __init__(self):
        super().__init__("config")
    
    def sense(self, project_path: str) -> Dict[str, ConfigStatus]:
        """感知配置完整性"""
        configs: Dict[str, ConfigStatus] = {}
        
        for config_file, spec in self.CONFIG_FILES.items():
            filepath = os.path.join(project_path, config_file)
            
            if not os.path.exists(filepath):
                if spec.get("required", False):
                    configs[config_file] = ConfigStatus.MISSING
                else:
                    configs[config_file] = ConfigStatus.MISSING
            elif config_file.endswith(('.yaml', '.yml', '.json', '.toml')):
                # 验证格式
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        if config_file.endswith(('.yaml', '.yml')):
                            import yaml
                            yaml.safe_load(f)
                        elif config_file.endswith('.json'):
                            json.load(f)
                    configs[config_file] = ConfigStatus.COMPLETE
                except Exception:
                    configs[config_file] = ConfigStatus.INVALID
            else:
                # 文本文件，检查是否为空
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if content.strip():
                        configs[config_file] = ConfigStatus.COMPLETE
                    else:
                        configs[config_file] = ConfigStatus.INCOMPLETE
                except Exception:
                    configs[config_file] = ConfigStatus.INVALID
        
        return configs


class DependencyProprioceptor(Proprioceptor):
    """
    依赖健康感知器
    
    检测 Python 依赖的健康状态。
    """
    
    def __init__(self):
        super().__init__("dependencies")
    
    def sense(self, project_path: str) -> Dict[str, int]:
        """感知依赖状态"""
        result = {
            "dependency_count": 0,
            "outdated_count": 0,
            "vulnerable_count": 0,
        }
        
        # 检查 requirements.txt
        req_path = os.path.join(project_path, "requirements.txt")
        if not os.path.exists(req_path):
            return result
        
        # 统计依赖数量
        try:
            with open(req_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            deps = [l.strip() for l in lines if l.strip() and not l.startswith('#')]
            result["dependency_count"] = len(deps)
            
        except Exception:
            pass
        
        # 尝试检查过时依赖
        try:
            pip_result = subprocess.run(
                ["pip", "list", "--outdated", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if pip_result.returncode == 0 and pip_result.stdout.strip():
                outdated = json.loads(pip_result.stdout)
                result["outdated_count"] = len(outdated)
                
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        
        # 尝试检查安全漏洞
        try:
            audit_result = subprocess.run(
                ["pip", "audit", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if audit_result.stdout.strip():
                vulnerabilities = json.loads(audit_result.stdout)
                result["vulnerable_count"] = len(vulnerabilities)
                
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        
        return result


class ProprioceptorArray:
    """
    位置感知器阵列
    
    管理所有位置感知器，提供统一的感知接口。
    类似于生物的本体感觉网络，全面感知"身体状态"。
    
    默认包含的感知器：
    - SystemResourceProprioceptor: 系统资源
    - GPUProprioceptor: GPU 状态
    - ToolchainProprioceptor: 工具链
    - ConfigProprioceptor: 配置完整性
    - DependencyProprioceptor: 依赖健康
    """
    
    def __init__(self, custom_proprioceptors: Optional[List[Proprioceptor]] = None):
        """
        Args:
            custom_proprioceptors: 自定义感知器列表（会替换默认感知器）
        """
        if custom_proprioceptors:
            self.proprioceptors = custom_proprioceptors
        else:
            self.proprioceptors = [
                SystemResourceProprioceptor(),
                GPUProprioceptor(),
                ToolchainProprioceptor(),
                ConfigProprioceptor(),
                DependencyProprioceptor(),
            ]
    
    def sense(self, project_path: str) -> SystemState:
        """
        全面感知系统状态
        
        Args:
            project_path: 项目路径
            
        Returns:
            系统状态快照
        """
        state = SystemState(
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            venv_active=sys.prefix != sys.base_prefix,
        )
        
        for proprioceptor in self.proprioceptors:
            try:
                result = proprioceptor.sense(project_path)
                
                if isinstance(proprioceptor, SystemResourceProprioceptor):
                    state.cpu_percent = result.get("cpu_percent")
                    state.memory_percent = result.get("memory_percent")
                    state.memory_used_gb = result.get("memory_used_gb")
                    state.memory_total_gb = result.get("memory_total_gb")
                    state.disk_percent = result.get("disk_percent")
                
                elif isinstance(proprioceptor, GPUProprioceptor):
                    state.gpu_info = result
                
                elif isinstance(proprioceptor, ToolchainProprioceptor):
                    state.tools = result
                
                elif isinstance(proprioceptor, ConfigProprioceptor):
                    state.configs = result
                
                elif isinstance(proprioceptor, DependencyProprioceptor):
                    state.dependency_count = result.get("dependency_count", 0)
                    state.outdated_count = result.get("outdated_count", 0)
                    state.vulnerable_count = result.get("vulnerable_count", 0)
                    
            except Exception as e:
                print(f"[Proprioceptor] {proprioceptor.name} 感知失败: {e}")
        
        return state
    
    def get_status_summary(self, state: SystemState) -> Dict[str, Any]:
        """获取状态摘要"""
        summary = {
            "health_score": state.get_health_score(),
            "python": state.python_version,
            "venv": state.venv_active,
            "tools_available": sum(1 for v in state.tools.values() if v == ToolStatus.AVAILABLE),
            "tools_total": len(state.tools),
            "configs_complete": sum(1 for v in state.configs.values() if v == ConfigStatus.COMPLETE),
            "configs_total": len(state.configs),
            "dependencies": state.dependency_count,
            "outdated": state.outdated_count,
            "vulnerable": state.vulnerable_count,
        }
        
        if state.gpu_info:
            summary["gpu_count"] = len(state.gpu_info)
            summary["gpu_names"] = [g["name"] for g in state.gpu_info]
        
        if state.memory_percent is not None:
            summary["memory_percent"] = state.memory_percent
        
        if state.cpu_percent is not None:
            summary["cpu_percent"] = state.cpu_percent
        
        return summary

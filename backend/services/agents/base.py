from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CrashAnalysisInput:
    crash_id: str
    game_name: str
    engine_version: str
    build_version: str
    crash_type: str
    error_message: str
    crashed_thread: str
    raw_callstack: str
    symbolicated_callstack: str
    crash_context_summary: str
    log_tail: str
    source_dir: str | None = None
    svn_revision: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    raw_response: str
    root_cause: str | None = None
    severity: str | None = None
    confidence: int | None = None
    fix_suggestion: str | None = None
    source_references: list[str] | None = None


class AgentProvider(ABC):
    @abstractmethod
    def analyze(self, crash_info: CrashAnalysisInput) -> AnalysisResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def agent_type(self) -> str:
        pass

    def build_prompt(self, info: CrashAnalysisInput) -> str:
        callstack = info.symbolicated_callstack or info.raw_callstack or "无调用栈信息"

        source_section = ""
        if info.source_dir:
            source_section = f"""
## 源码分析要求（重要）
项目源码目录: {info.source_dir}

你 **必须** 结合源码进行分析，具体要求如下：
1. 根据调用栈中的函数名和模块名，在源码目录中搜索并定位到对应的源文件和代码行
2. 阅读崩溃点附近的源码，分析导致崩溃的具体代码逻辑
3. 找出崩溃触发的根本原因（如空指针、数组越界、竞态条件、资源未初始化等）
4. 在修复建议中给出具体的代码修改方案，包括：
   - 需要修改的源文件路径和函数名
   - 具体的代码修改内容（修改前 vs 修改后）
   - 如果有多种修复方案，列出优缺点
"""

        return f"""你是一个 UE5 游戏崩溃分析专家。请分析以下崩溃信息并给出报告。

## 崩溃基本信息
- 游戏: {info.game_name or '未知'}
- 引擎版本: {info.engine_version or '未知'}
- 构建版本: {info.build_version or '未知'}
- 崩溃类型: {info.crash_type or '未知'}
- 错误信息: {info.error_message or '未知'}
- 崩溃线程: {info.crashed_thread or '未知'}

## 调用栈
{callstack}

## 运行时上下文
{info.crash_context_summary or '无'}

## 崩溃前日志（最后200行）
{info.log_tail or '无日志'}
{source_section}
请以如下 JSON 格式返回分析结果（只返回 JSON，不要其他内容）：
{{
  "root_cause": "崩溃根因分析（结合源码详细说明触发崩溃的代码逻辑和原因）",
  "severity": "Critical 或 High 或 Medium 或 Low",
  "confidence": 0到100的整数,
  "confidence_reason": "信心度理由",
  "fix_suggestion": "修复建议（包含具体需要修改的源文件、函数、代码行，以及修改前后的代码对比）",
  "affected_module": "受影响模块",
  "crash_category": "崩溃分类（如内存、空指针、线程安全等）",
  "source_references": ["崩溃相关的源码文件路径和行号列表，如 Source/Server/cellapp/Entity/unit.cpp:123"]
}}"""

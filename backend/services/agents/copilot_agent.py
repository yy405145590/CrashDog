import json
import shutil
import subprocess
from pathlib import Path

from ... import config
from .base import AgentProvider, AnalysisResult, CrashAnalysisInput

RESULT_FILENAME = "analysis_result.json"
LOG_FILENAME = "copilot_log.txt"


class CopilotAgent(AgentProvider):
    def agent_type(self) -> str:
        return "copilot"

    def is_available(self) -> bool:
        return shutil.which(config.COPILOT_PATH) is not None

    def analyze(self, crash_info: CrashAnalysisInput) -> AnalysisResult:
        if not crash_info.source_dir:
            crash_info.source_dir = config.SOURCE_DIR

        prompt_content = self.build_prompt(crash_info)

        tmpdir = config.TEMP_DIR / crash_info.crash_id
        tmpdir.mkdir(parents=True, exist_ok=True)

        crash_file = tmpdir / "crash_report.md"
        crash_file.write_text(prompt_content, encoding="utf-8")

        result_file = tmpdir / RESULT_FILENAME
        log_file = tmpdir / LOG_FILENAME
        log_file.write_bytes(b"")

        short_prompt = (
            f"请阅读 {crash_file} 中的 UE5 崩溃报告并进行分析。"
            f"将分析结果以 JSON 格式保存到文件：{result_file}"
        )

        cmd = [
            config.COPILOT_PATH,
            "--autopilot",
            "--log-level", "all",
            "--yolo",
            "--max-autopilot-continues", "100",
            "--add-dir", str(tmpdir),
            "-p", short_prompt,
        ]

        if crash_info.source_dir:
            cmd.extend(["--add-dir", crash_info.source_dir])

        cwd = crash_info.source_dir or str(tmpdir)

        try:
            stdout_lines = []
            with subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            ) as proc:
                with open(log_file, "w", encoding="utf-8") as log_f:
                    for line in proc.stdout:
                        stdout_lines.append(line)
                        log_f.write(line)
                        log_f.flush()
                proc.wait(timeout=config.COPILOT_TIMEOUT)

            raw_output = "".join(stdout_lines)

            if result_file.exists():
                return self._parse_result_file(result_file, raw_output)
            return self._parse_response(raw_output)

        except subprocess.TimeoutExpired:
            return AnalysisResult(
                raw_response="分析超时",
                root_cause="AI 分析超时，请重试或检查 Copilot 配置",
                severity="Unknown",
                confidence=0,
            )
        except Exception as e:
            return AnalysisResult(
                raw_response=str(e),
                root_cause=f"调用 Copilot 失败: {e}",
                severity="Unknown",
                confidence=0,
            )

    def _parse_result_file(self, path: Path, raw_output: str) -> AnalysisResult:
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            return AnalysisResult(
                raw_response=raw_output,
                root_cause=data.get("root_cause"),
                severity=data.get("severity"),
                confidence=data.get("confidence"),
                fix_suggestion=data.get("fix_suggestion"),
                source_references=data.get("source_references"),
            )
        except (json.JSONDecodeError, OSError):
            return self._parse_response(raw_output)

    def _parse_response(self, raw: str) -> AnalysisResult:
        data = self._extract_json(raw)
        if data and "root_cause" in data:
            return AnalysisResult(
                raw_response=raw,
                root_cause=data.get("root_cause"),
                severity=data.get("severity"),
                confidence=data.get("confidence"),
                fix_suggestion=data.get("fix_suggestion"),
                source_references=data.get("source_references"),
            )

        return AnalysisResult(
            raw_response=raw,
            root_cause=raw[:2000] if raw else "无分析结果",
            severity="Unknown",
            confidence=0,
            fix_suggestion=None,
        )

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        start = text.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find("{", start + 1)
        return None

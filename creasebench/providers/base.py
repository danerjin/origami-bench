"""Provider interface and the Python sandbox tool used in agentic mode."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..tasks import Task

PYTHON_TOOL_DESCRIPTION = (
    "Run a Python 3 script and return its stdout and stderr. Each call is a fresh process; the working "
    "directory persists between calls (save files to keep state). numpy and shapely are available. "
    "The task inputs are in the working directory (e.g. crease_pattern.json, target_silhouette.json).")

FINAL_STEP_NOTE = ("STEP LIMIT REACHED: no further tool calls will be executed. "
                   "Reply now with your final answer in a ```json block.")


@dataclass
class RunResult:
    text: str  # final model text (contains the JSON answer)
    transcript: list = field(default_factory=list)  # serialisable record of the exchange
    usage: dict = field(default_factory=dict)
    tool_calls: int = 0
    error: str | None = None


class PythonSandbox:
    """Executes model-written code in a subprocess inside a scratch directory.

    This is NOT a security boundary: run untrusted models inside a container or VM.
    """

    def __init__(self, task: Task, timeout: int = 60, max_output: int = 20_000):
        self.dir = Path(tempfile.mkdtemp(prefix=f"ob-{task.id}-"))
        self.timeout = timeout
        self.max_output = max_output
        for key, val in task.inputs.items():
            (self.dir / f"{key}.json").write_text(json.dumps(val))
        for p in task.image_paths():
            shutil.copy(p, self.dir / p.name)

    def run(self, code: str) -> str:
        script = self.dir / "_cell.py"
        script.write_text(code)
        try:
            proc = subprocess.run([sys.executable, script.name], cwd=self.dir, capture_output=True,
                                  text=True, timeout=self.timeout)
            out = proc.stdout
            if proc.stderr:
                out += "\n[stderr]\n" + proc.stderr
            if proc.returncode:
                out += f"\n[exit code {proc.returncode}]"
        except subprocess.TimeoutExpired:
            out = f"[timed out after {self.timeout}s]"
        if len(out) > self.max_output:
            out = out[: self.max_output] + f"\n[output truncated to {self.max_output} chars]"
        return out or "[no output]"

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def image_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


class Provider:
    name = "base"

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        raise NotImplementedError

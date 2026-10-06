"""Claude via the Anthropic Messages API (manual tool loop for the Python tool)."""

from __future__ import annotations

from pathlib import Path

import anthropic

from ..tasks import Task
from .base import FINAL_STEP_NOTE, PYTHON_TOOL_DESCRIPTION, Provider, PythonSandbox, RunResult, image_b64

PYTHON_TOOL = {
    "name": "python",
    "description": PYTHON_TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python source to execute."}},
        "required": ["code"],
        "additionalProperties": False,
    },
    "eager_input_streaming": True,
}


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5", effort: str | None = "high", max_tokens: int = 64000):
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        content: list[dict] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64(p)}}
            for p in images
        ]
        content.append({"type": "text", "text": prompt})
        messages: list[dict] = [{"role": "user", "content": content}]
        kwargs: dict = {"model": self.model, "max_tokens": self.max_tokens}
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if sandbox is not None:
            kwargs["tools"] = [PYTHON_TOOL]
        usage = {"input_tokens": 0, "output_tokens": 0}
        transcript: list = []
        tool_calls = 0
        steps = 0
        while True:
            try:
                with self.client.messages.stream(messages=messages, **kwargs) as stream:
                    response = stream.get_final_message()
            except anthropic.APIStatusError as e:
                return RunResult("", transcript, usage, tool_calls, f"API error {e.status_code}: {e.message}")
            except anthropic.APIConnectionError as e:
                return RunResult("", transcript, usage, tool_calls, f"connection error: {e}")
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            transcript.append({"role": "assistant", "content": [b.to_dict() for b in response.content]})
            text = "".join(b.text for b in response.content if b.type == "text")
            if response.stop_reason == "refusal":
                return RunResult(text, transcript, usage, tool_calls, "refusal")
            if response.stop_reason != "tool_use" or sandbox is None:
                err = "max_tokens" if response.stop_reason == "max_tokens" else None
                return RunResult(text, transcript, usage, tool_calls, err)
            steps += 1
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls += 1
                code = block.input.get("code") if isinstance(block.input, dict) else None
                if block.name != "python" or not isinstance(code, str):
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": "invalid tool call: expected python(code: str)"})
                    continue
                out = sandbox.run(code) if steps <= max_steps else "[not executed]"
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            if steps >= max_steps:
                results.append({"type": "text", "text": FINAL_STEP_NOTE})
            if steps > max_steps:
                return RunResult(text, transcript, usage, tool_calls, "step limit")
            transcript.append({"role": "user", "content": results})
            messages.append({"role": "user", "content": results})

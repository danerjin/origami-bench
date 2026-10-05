"""Any OpenAI-compatible chat-completions endpoint (OpenAI, vLLM, OpenRouter, ...).

Configure with --base-url / OPENAI_BASE_URL and OPENAI_API_KEY.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..tasks import Task
from .base import FINAL_STEP_NOTE, PYTHON_TOOL_DESCRIPTION, Provider, PythonSandbox, RunResult, image_b64

PYTHON_TOOL = {
    "type": "function",
    "function": {
        "name": "python",
        "description": PYTHON_TOOL_DESCRIPTION,
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
    },
}


class OpenAICompatProvider(Provider):
    name = "openai"

    def __init__(self, model: str, base_url: str | None = None, max_tokens: int | None = None,
                 reasoning_effort: str | None = None):
        import openai

        self.openai = openai
        self.client = openai.OpenAI(base_url=base_url) if base_url else openai.OpenAI()
        self.model = model
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        content: list[dict] = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64(p)}"}}
                               for p in images]
        content.append({"type": "text", "text": prompt})
        messages: list[dict] = [{"role": "user", "content": content}]
        kwargs: dict = {"model": self.model}
        if self.max_tokens:
            kwargs["max_completion_tokens"] = self.max_tokens
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if sandbox is not None:
            kwargs["tools"] = [PYTHON_TOOL]
        usage = {"input_tokens": 0, "output_tokens": 0}
        transcript: list = []
        tool_calls = 0
        steps = 0
        while True:
            try:
                resp = self.client.chat.completions.create(messages=messages, **kwargs)
            except self.openai.OpenAIError as e:
                return RunResult("", transcript, usage, tool_calls, f"API error: {e}")
            if resp.usage:
                usage["input_tokens"] += resp.usage.prompt_tokens or 0
                usage["output_tokens"] += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            transcript.append(msg.model_dump(exclude_none=True))
            text = msg.content or ""
            if not msg.tool_calls or sandbox is None:
                return RunResult(text, transcript, usage, tool_calls)
            steps += 1
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                tool_calls += 1
                try:
                    code = json.loads(call.function.arguments).get("code")
                except json.JSONDecodeError:
                    code = None
                if call.function.name != "python" or not isinstance(code, str):
                    out = "invalid tool call: expected python(code: str)"
                else:
                    out = sandbox.run(code) if steps <= max_steps else "[not executed]"
                if steps >= max_steps:
                    out += "\n\n" + FINAL_STEP_NOTE
                messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
                transcript.append(messages[-1])
            if steps > max_steps:
                return RunResult(text, transcript, usage, tool_calls, "step limit")

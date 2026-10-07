from .base import Provider, PythonSandbox, RunResult


def make_provider(name: str, model: str | None = None, base_url: str | None = None,
                  effort: str | None = None, answers: str | None = None) -> Provider:
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model or "claude-opus-5-5", effort=effort or "high")
    if name == "openai":
        from .openai_provider import OpenAICompatProvider

        if not model:
            raise SystemExit("--model is required for the openai provider")
        return OpenAICompatProvider(model, base_url=base_url, reasoning_effort=effort)
    if name == "oracle":
        from .baselines import OracleProvider

        return OracleProvider()
    if name == "file":
        from .baselines import FileProvider

        if not answers:
            raise SystemExit("--answers DIR is required for the file provider")
        return FileProvider(answers)
    if name == "heuristic":
        from .baselines import HeuristicProvider

        return HeuristicProvider()
    if name == "unfolded":
        from .baselines import UnfoldedProvider

        return UnfoldedProvider()
    raise SystemExit(f"unknown provider {name!r}")


__all__ = ["Provider", "PythonSandbox", "RunResult", "make_provider"]

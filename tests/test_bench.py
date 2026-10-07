import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from creasebench.build import oracle_answer
from creasebench.graders import extract_json, grade
from creasebench.prompts import build_prompt
from creasebench.providers import PythonSandbox
from creasebench.providers.baselines import UnfoldedProvider
from creasebench.tasks import load_tasks

TASKS = Path(__file__).resolve().parents[1] / "tasks"
pytestmark = pytest.mark.skipif(not TASKS.exists(), reason="run `python -m creasebench.build` first")


def sample():
    tasks = load_tasks(TASKS)
    picked = {}
    for t in tasks:
        picked.setdefault((t.track, t.difficulty), t)
    return list(picked.values())


@pytest.mark.parametrize("task", sample(), ids=lambda t: t.id)
def test_oracle_solves_and_baseline_scores_zero(task):
    ans = oracle_answer(task)
    if not ans:
        pytest.skip("no reference design (scored against the packing bound)")
    g = grade(task, ans)
    assert g["solved"]
    if task.reference.get("family") != "design":  # reference designs need not reach the bound
        assert g["score"] == pytest.approx(1.0, abs=1e-3)
    base = grade(task, UnfoldedProvider().run(task, "", [], None, 0).text)
    assert not base["solved"]
    if task.meta.get("tier", "basic") == "basic":
        assert base["score"] == pytest.approx(0.0, abs=1e-6)


def test_unparseable_and_unfoldable_answers_score_zero():
    task = next(t for t in load_tasks(TASKS, tracks=["dt"]))
    assert grade(task, "I give up")["score"] == 0
    bad = {"creases": [[0, 0.5, 1, 0.5, "V"], [0.5, 0, 0.5, 1, "V"]]}  # Maekawa violation
    g = grade(task, "```json\n" + json.dumps(bad) + "\n```")
    assert g["score"] == 0 and "not flat-foldable" in g["error"]


def test_prompt_hides_reference_and_includes_inputs():
    for t in load_tasks(TASKS):
        p = build_prompt(t)
        assert "baseline_score" not in p and '"checks"' not in p and '"solution"' not in p
        for key in t.inputs:
            assert key in p


def test_extract_json_prefers_last_block():
    text = "draft ```json\n{\"a\": 1}\n``` final ```json\n{\"a\": 2}\n```"
    assert extract_json(text) == {"a": 2}
    assert extract_json('blah {"x": [1, {"y": 2}]} trailing') == {"x": [1, {"y": 2}]}


def test_python_sandbox_sees_inputs():
    task = next(t for t in load_tasks(TASKS, tracks=["af"]))
    sb = PythonSandbox(task)
    try:
        out = sb.run("import json; print(len(json.load(open('crease_pattern.json'))['vertices_coords']))")
        assert out.strip() == str(len(task.inputs["crease_pattern"]["vertices_coords"]))
        assert "timed out" in PythonSandbox(task, timeout=1).run("while True: pass")
    finally:
        sb.close()


def test_anthropic_tool_loop_with_fake_client(monkeypatch):
    from creasebench.providers import anthropic_provider as ap

    task = next(t for t in load_tasks(TASKS, tracks=["af"]))

    def block(**kw):
        return SimpleNamespace(to_dict=lambda: kw, **kw)

    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    replies = [
        SimpleNamespace(stop_reason="tool_use", usage=usage,
                        content=[block(type="tool_use", id="t1", name="python", input={"code": "print(6*7)"})]),
        SimpleNamespace(stop_reason="end_turn", usage=usage, content=[block(type="text", text=oracle_answer(task))]),
    ]
    seen = []

    class FakeStream:
        def __init__(self, reply):
            self.reply = reply

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return self.reply

    class FakeMessages:
        def stream(self, messages, **kw):
            seen.append([m for m in messages])
            return FakeStream(replies[len(seen) - 1])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    prov = ap.AnthropicProvider()
    prov.client = SimpleNamespace(messages=FakeMessages())
    sb = PythonSandbox(task)
    try:
        res = prov.run(task, build_prompt(task, agentic=True), [], sb, max_steps=5)
    finally:
        sb.close()
    assert res.tool_calls == 1 and res.error is None
    tool_result = seen[1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["content"].strip() == "42"
    assert grade(task, res.text)["solved"]


def test_export_hides_task_ids(tmp_path):
    import json

    from creasebench.export import export, id_map_path
    from creasebench.tasks import load_tasks

    tasks = load_tasks("tasks", ids=["adv-bug-global-bird-2x2", "af-ref-waterbomb_base"])
    out = tmp_path / "eval"
    folders = export(tasks, out)
    names = {p.name for p in out.iterdir()}
    assert names == set(folders.values()) and not any(t.id in names for t in tasks)
    for p in out.rglob("*"):  # nothing an agent can read names the task
        if p.is_file() and p.suffix in (".md", ".json"):
            assert not any(t.id in p.read_text() for t in tasks)
    assert json.loads(id_map_path(out).read_text()) == folders
    assert not str(id_map_path(out)).startswith(str(out) + "/")

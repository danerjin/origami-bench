"""Optional vision-model judge for semantic design tasks ("design a fish").

Reported as a separate column from the automatic score, so the main benchmark
number stays deterministic and reproducible.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .graders import answer_cp, extract_json
from .providers import make_provider
from .render import render_silhouette
from .tasks import Task
from .verify import verify

JUDGE_PROMPT = """\
The image shows the flat outline of an origami model. Judge only the shape, as a viewer would.
On a scale from 0 to 10, how clearly does this outline depict {subject}?
0 = not at all, 5 = recognisable with some imagination, 10 = unmistakable.
Reply with a short justification followed by a final line of the form `SCORE: <0-10>`."""


def judge(task: Task, response_text: str, provider_name: str, model: str | None) -> dict | None:
    subject = task.reference.get("judge_subject")
    if not subject:
        return None
    try:
        rep = verify(answer_cp(extract_json(response_text)), budget=50_000)
    except Exception as e:  # noqa: BLE001 - any unusable answer simply gets no judge score
        return {"judge_score": 0.0, "judge_error": str(e)}
    if not rep.foldable:
        return {"judge_score": 0.0, "judge_error": "not foldable"}
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "answer.png"
        render_silhouette(rep.folded.silhouette(), img, title=" ")
        prov = make_provider(provider_name, model)
        res = prov.run(task, JUDGE_PROMPT.format(subject=subject), [img], None, 0)
    m = re.findall(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", res.text or "")
    if not m:
        return {"judge_score": None, "judge_error": "no score", "judge_text": res.text}
    return {"judge_score": min(10.0, float(m[-1])) / 10, "judge_text": res.text}

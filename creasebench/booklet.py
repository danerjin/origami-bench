"""Print every task as a question booklet for human solvers (PDF via headless Chromium).

    python -m creasebench.booklet --out booklet/   [--splits expert,hard] [--chrome PATH]

Writes ``booklet/creasebench-questions.pdf`` (and the ``.html`` it is printed from), a
``booklet/inputs/Qnnn/`` folder with every task's input files and images, and
``booklet/key.json`` mapping question numbers to task ids. Questions are numbered and carry
their split and family but not their task id, since ids can name the answer (keep key.json
away from solvers). Inputs too long to print are truncated in the PDF and given in full in
``inputs/``. Crease patterns that have no image of their own are drawn, so they can be read
on paper. Answers are graded like any other: put ``answer.txt`` in a folder per task id and
run ``python -m creasebench.run --provider file --answers DIR``.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from .cp import CreasePattern
from .prompts import build_prompt
from .render import _finish, render_cp
from .tasks import load_tasks, task_split

SPLITS = ("expert", "expert-analysis", "hard", "core", "warmup")
SPLIT_NOTES = {
    "expert": "Headline split, graded pass/fail. Expert-level design, image-only tree reading and inverse folding.",
    "expert-analysis": "Pass/fail, reported outside the headline: flap regions and repair of global conflicts.",
    "hard": "Design targets with at least 6 flaps; analysis of patterns with at least 100 creases.",
    "core": "The rest of the advanced tier.",
    "warmup": "The basic tier: small folds and simple crease patterns.",
}
MAX_PRINT = 1200  # characters of inline JSON printed before truncating
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.45 "DejaVu Serif", Georgia, serif; color: #111; }
h1 { font-size: 24pt; margin: 0 0 4mm; } h2 { font-size: 15pt; border-bottom: 1px solid #999; }
.q { break-before: page; } .q h3 { font-size: 13pt; margin: 0 0 3mm; }
.tag { font: 9pt sans-serif; color: #555; }
pre { font: 8pt/1.3 "DejaVu Sans Mono", monospace; background: #f4f4f4; padding: 2mm;
      white-space: pre-wrap; word-break: break-all; }
code { font: 9pt "DejaVu Sans Mono", monospace; }
img { max-width: 100%; max-height: 150mm; display: block; margin: 3mm auto; }
.note { font: italic 9pt sans-serif; color: #444; }
.space { border: 1px dashed #aaa; min-height: 60mm; margin-top: 4mm; padding: 2mm; color: #999; font: 9pt sans-serif; }
table { border-collapse: collapse; } td, th { border: 1px solid #bbb; padding: 1mm 3mm; font-size: 9.5pt; }
"""


def _md(text: str, qdir: str) -> str:
    """The prompts' small markdown subset: ``` fences, `code`, paragraphs and - lists."""
    out = []
    for i, chunk in enumerate(re.split(r"(?m)^```(?:json)?[ \t]*\n?", text)):
        if i % 2:  # inside a fence
            body = chunk.rstrip("\n")
            if len(body) > MAX_PRINT:
                body = body[:MAX_PRINT] + f" ...\n[truncated: the full input is in inputs/{qdir}/]"
            out.append(f"<pre>{html.escape(body)}</pre>")
            continue
        for para in re.split(r"\n\s*\n", chunk.strip()):
            if not para:
                continue
            esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(para))
            lines = esc.split("\n")
            if all(l.lstrip().startswith("- ") or l.startswith("  ") for l in lines[1:]) and \
                    any(l.lstrip().startswith("- ") for l in lines):
                items, cur = [], None
                head = [] if lines[0].lstrip().startswith("- ") else [lines.pop(0)]
                for l in lines:
                    if l.lstrip().startswith("- "):
                        cur = l.lstrip()[2:]
                        items.append(cur)
                    else:
                        items[-1] += " " + l.strip()
                out.append("".join(f"<p>{h}</p>" for h in head) + "<ul>" + "".join(f"<li>{x}</li>" for x in items)
                           + "</ul>")
            else:
                out.append(f"<p>{'<br>'.join(lines)}</p>")
    return "\n".join(out)


def _tree_png(edges, title: str) -> bytes:
    """A target tree drawn as a stick figure with its edge lengths (the prompt gives only the edge list)."""
    import matplotlib.pyplot as plt
    import networkx as nx

    g = nx.Graph()
    for u, v, length in edges:
        g.add_edge(str(u), str(v), length=float(length))
    pos = nx.kamada_kawai_layout(g, weight="length")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    nx.draw_networkx_edges(g, pos, ax=ax, width=1.6)
    leaves = [n for n in g if g.degree(n) == 1]
    nx.draw_networkx_nodes(g, pos, nodelist=[n for n in g if n not in leaves], node_size=18, node_color="#333", ax=ax)
    nx.draw_networkx_nodes(g, pos, nodelist=leaves, node_size=30, node_color="#c0392b", ax=ax)
    nx.draw_networkx_labels(g, pos, font_size=7, verticalalignment="bottom", ax=ax)
    nx.draw_networkx_edge_labels(g, pos, edge_labels={(u, v): f"{l:g}" for u, v, l in g.edges(data="length")},
                                 font_size=6.5, font_color="#1f4e9a", ax=ax)
    ax.set_title(title, fontsize=10)
    ax.axis("off")
    return _finish(fig, None)


def _img(data: bytes, mime: str = "image/png") -> str:
    return f'<img src="data:{mime};base64,{base64.b64encode(data).decode()}">'


def build(out: Path, tasks_dir: str = "tasks", splits=SPLITS, chrome: str = CHROME) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(tasks_dir, tiers=["basic", "advanced"])
    tasks = sorted((t for t in tasks if task_split(t) in splits),
                   key=lambda t: (list(splits).index(task_split(t)), t.track, t.reference.get("family") or "", t.id))
    key, body, toc, preambles = {}, [], [], {}
    inputs_root = out / "inputs"
    shutil.rmtree(inputs_root, ignore_errors=True)
    current = None
    for n, t in enumerate(tasks, 1):
        q = f"Q{n:03d}"
        key[q] = t.id
        sp = task_split(t)
        family = t.reference.get("family") or t.track
        prompt = build_prompt(t)
        head, task_text = prompt.split("\nTask (", 1)
        conv = "advanced" if t.meta.get("tier") == "advanced" else "basic"
        preambles[conv] = head
        if sp != current:
            current = sp
            count = sum(task_split(x) == sp for x in tasks)
            toc.append(f"<tr><td>{sp}</td><td>{q}–Q{n + count - 1:03d}</td><td>{count}</td>"
                       f"<td>{html.escape(SPLIT_NOTES[sp])}</td></tr>")
        qd = inputs_root / q
        qd.mkdir(parents=True)
        figs = []
        for p in t.image_paths():
            shutil.copy(p, qd / p.name)
            figs.append(_img(p.read_bytes(), "image/svg+xml" if p.suffix == ".svg" else "image/png"))
        for k, v in t.inputs.items():
            (qd / f"{k}.json").write_text(json.dumps(v))
            if not t.images and isinstance(v, dict) and "vertices_coords" in v:
                png = render_cp(CreasePattern.from_fold(v), title=f"Input `{k}` drawn (red = mountain, blue = valley)")
                figs.append(_img(png) + '<p class="note">Drawn for this booklet; the task gives the coordinates '
                            "only.</p>")
            if isinstance(v, dict) and "edges" in v and "vertices_coords" not in v:
                try:
                    png = _tree_png(v["edges"], f"Input `{k}` drawn (red dots = flap tips; blue = edge lengths)")
                    figs.append(_img(png) + '<p class="note">Drawn for this booklet; layout is arbitrary, only '
                                "the labelled lengths matter.</p>")
                except (ValueError, TypeError):
                    pass
        body.append(
            f'<section class="q"><h3>{q}</h3><div class="tag">split: {sp} · family: {html.escape(family)} · '
            f"conventions: {conv} (front matter) · files: inputs/{q}/</div>"
            + _md("Task (" + task_text, q) + "".join(figs)
            + '<div class="space">Working / answer</div></section>')
    front = (
        "<h1>CreaseBench: question booklet</h1>"
        f"<p>{len(tasks)} questions on flat-folded origami: reading crease patterns, folding, tree theory, "
        "flap design and defect finding. Each question is exactly the prompt a model receives. The model "
        "conventions are printed once below and apply to every question of that tier.</p>"
        "<p><b>How to answer.</b> Give the JSON answer each question asks for. Answers are graded by "
        "actually folding them, so partial sketches score nothing. For large inputs, use the files in "
        "<code>inputs/Qnnn/</code>; any tool you like is allowed (ruler, compass, paper, a computer) unless "
        "you are timing a closed-book attempt.</p>"
        "<table><tr><th>split</th><th>questions</th><th>n</th><th>contents</th></tr>" + "".join(toc) + "</table>"
        + "".join(f'<section class="q"><h2>Conventions: {name} tier</h2>{_md(txt, "-")}</section>'
                  for name, txt in sorted(preambles.items())))
    doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{front}" \
          f"{''.join(body)}</body></html>"
    page = out / "creasebench-questions.html"
    page.write_text(doc)
    (out / "key.json").write_text(json.dumps(key, indent=1))
    pdf = out / "creasebench-questions.pdf"
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", page.resolve().as_uri()], check=True, capture_output=True, timeout=600)
    return pdf


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--splits", default=",".join(SPLITS))
    ap.add_argument("--chrome", default=CHROME)
    args = ap.parse_args(argv)
    pdf = build(Path(args.out), args.tasks_dir, tuple(args.splits.split(",")), args.chrome)
    print(f"wrote {pdf}")


if __name__ == "__main__":
    main()

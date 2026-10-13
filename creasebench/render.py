"""Matplotlib renderings of crease patterns, folded states and silhouettes."""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
from shapely.geometry import MultiPolygon  # noqa: E402

from .compare import as_geometry  # noqa: E402
from .cp import CreasePattern  # noqa: E402
from .simulate import FoldedState  # noqa: E402

STYLE = {
    "M": dict(color="#d62728", lw=1.6, ls="-"),
    "V": dict(color="#1f5bd6", lw=1.6, ls=(0, (5, 3))),
    "B": dict(color="black", lw=2.0, ls="-"),
    "U": dict(color="#777777", lw=1.4, ls="-"),
    "F": dict(color="#bbbbbb", lw=0.8, ls=":"),
}


def _finish(fig, path: str | Path | None) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()
    if path is not None:
        Path(path).write_bytes(data)
    return data


def render_cp(cp: CreasePattern, path=None, title: str | None = None, label_vertices: bool = False,
              boxes: dict | None = None) -> bytes:
    """``boxes``: optional {label: [x0, y0, x1, y1]} regions drawn as labelled rectangles."""
    fig, ax = plt.subplots(figsize=(6, 6))
    for (u, v), a in zip(cp.edges, cp.assignments):
        p, q = cp.vertices[u], cp.vertices[v]
        ax.plot([p[0], q[0]], [p[1], q[1]], **STYLE[a])
    for label, (x0, y0, x1, y1) in (boxes or {}).items():
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=2.2, ec="black"))
        ax.annotate(str(label), (x0, y1), fontsize=12, weight="bold", xytext=(2, -13), textcoords="offset points",
                    bbox=dict(fc="white", ec="none", alpha=0.8, pad=0.5))
    if label_vertices:
        for i, (x, y) in enumerate(cp.vertices):
            ax.annotate(str(i), (x, y), fontsize=7, color="#444", xytext=(2, 2), textcoords="offset points")
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_aspect("equal")
    ax.set_xticks(np.linspace(0, 1, 5))
    ax.set_yticks(np.linspace(0, 1, 5))
    ax.grid(alpha=0.15)
    ax.set_title(title or "Crease pattern (red solid = mountain, blue dashed = valley)", fontsize=10)
    return _finish(fig, path)


def _draw_order(n: int, above: list[tuple[int, int]] | None) -> list[int]:
    if not above:
        return list(range(n))
    g = nx.DiGraph()
    g.add_nodes_from(range(n))
    g.add_edges_from((b, a) for a, b in above)  # draw b before a when a is above b
    try:
        return list(nx.topological_sort(g))
    except nx.NetworkXUnfeasible:
        return list(range(n))


def render_folded(folded: FoldedState, path=None, above=None, title: str | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 6))
    for fi in _draw_order(len(folded.cp.faces), above):
        pts = folded.face_coords(fi)
        color = "#f2c27b" if not folded.face_flipped(fi) else "#9ec5e8"
        ax.fill(pts[:, 0], pts[:, 1], facecolor=color, edgecolor="#333", lw=0.8, alpha=0.55)
    _square_axes(ax, folded.silhouette())
    ax.set_title(title or "Folded state (orange = top side up, blue = flipped)", fontsize=10)
    return _finish(fig, path)


def render_silhouette(poly, path=None, title: str | None = None) -> bytes:
    g = as_geometry(poly)
    fig, ax = plt.subplots(figsize=(6, 6))
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        x, y = p.exterior.xy
        ax.fill(x, y, facecolor="#555", edgecolor="black", lw=1.2)
        for hole in p.interiors:
            hx, hy = hole.xy
            ax.fill(hx, hy, facecolor="white", edgecolor="black", lw=1.0)
    _square_axes(ax, g)
    ax.set_title(title or "Target silhouette (grid unit = original paper side)", fontsize=10)
    return _finish(fig, path)


def _square_axes(ax, geom) -> None:
    minx, miny, maxx, maxy = geom.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    half = max(maxx - minx, maxy - miny) / 2 + 0.08
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.25))
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.25))

#!/usr/bin/env python3
"""Render the figures embedded in ``docs/evaluation/awf-discussion-draft.md``.

    python3 docs/evaluation/figures/make_figures.py                # write the SVGs
    python3 docs/evaluation/figures/make_figures.py --preview /tmp  # + PNGs to eyeball

Every number this script draws comes from ``figures.yaml``, which transcribes it
from an evidence document together with the section that states it. This script
computes NOTHING from ``benchmarks/results/**``: the campaign pre-registered a
single analysis path per number (``benchmarks/scripts/duel_verdict.py``,
``benchmarks/scripts/cal_report.py`` -- report.md section 9), and a plotting
script that re-derived them would be a second, unregistered one.

The one arithmetic operation performed here is normalising a delta by its own
margin for the forest figure, so that five metrics in four units share one axis.
That ratio is the decision rule's own unit -- ``equivalence_decision`` compares
the CI against +/-margin and nothing else -- so the +/-1 band a reader sees IS
the rule, not a visual analogy for it.

Deliberately NOT drawn, and the reason, because a figure is read as an
invitation to compare:

* the section 3.5 upstreaming ratios (66/98 against 0). The report states that the two
  cells are computed over different populations and that no ordering between
  them is supported. Charting them side by side would assert the ordering the
  source refuses.
* the A-vs-B closed-loop arm, under tier4-native's own as-shipped transport.
  It is permanently non-computable (cell B armed on 0 of 15 runs); an empty row
  on a chart reads as "missing data", not as "this comparison does not exist".

Colours are the reference data-viz palette (categorical slots 1-4, status
`critical`, and the chrome/ink roles). Verdict is carried by colour AND by a
written verdict label on every row; arm is carried by marker shape AND by a row
label. Nothing on these figures is encoded by colour alone.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import yaml
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent

# Reference palette -- light surface. Categorical slots 1-4 are used only on
# adjacent pairs (stacked segments), which is the pairlist that ordering
# validates against; every segment also carries a direct label.
C = {
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "band": "#f0efec",
    "s1": "#2a78d6",  # blue
    "s2": "#eb6834",  # orange
    "s3": "#1baf7a",  # aqua
    "s4": "#eda100",  # yellow
    "critical": "#d03b3b",
}

VERDICT_COLOR = {
    "parity": C["s1"],
    "a_better": C["s1"],
    "b_better": C["critical"],
    "insufficient_data": C["muted"],
}

VERDICT_TEXT = {
    "parity": "parity",
    "a_better": "extension better",
    "b_better": "tier4-native better",
    "insufficient_data": "not computed",
}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "svg.fonttype": "path",  # embed glyphs; identical rendering everywhere
        "figure.facecolor": C["surface"],
        "axes.facecolor": C["surface"],
        "savefig.facecolor": C["surface"],
        "text.color": C["ink"],
        "axes.labelcolor": C["ink2"],
        "xtick.color": C["muted"],
        "ytick.color": C["muted"],
        "axes.edgecolor": C["axis"],
        "font.size": 9,
    }
)


def load() -> dict:
    with open(HERE / "figures.yaml") as f:
        return yaml.safe_load(f)


def style_axis(ax, *, xgrid=True, ygrid=False):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(length=3, width=0.8, labelsize=8)
    if xgrid:
        ax.xaxis.grid(True, color=C["grid"], linewidth=0.7, zorder=0)
    if ygrid:
        ax.yaxis.grid(True, color=C["grid"], linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)


def title_block(fig, title, subtitle, footnote, *, x=0.012, y=0.975, foot_y=0.018):
    fig.text(x, y, title, fontsize=11.5, fontweight="bold", va="top", color=C["ink"])
    fig.text(x, y - 0.058, subtitle, fontsize=8.6, va="top", color=C["ink2"])
    fig.text(x, foot_y, footnote, fontsize=7.6, va="bottom", color=C["muted"])


# ---------------------------------------------------------------------------
# 1. Equivalence forest -- draft sections 3.1 and 3.2
# ---------------------------------------------------------------------------
def fig_equivalence(d: dict, out: Path) -> Path:
    eq = d["equivalence"]
    metrics = eq["metrics"]
    arms = eq["arms"]

    fig = plt.figure(figsize=(10.6, 6.6))
    # Broken x-axis: the decision zone needs 0.03-margin resolution to show the
    # knife-edge; the CPU row sits at ~5.8 margins. One linear axis spanning
    # both renders the four in-band rows as a single smear at zero.
    gsL = fig.add_axes([0.295, 0.150, 0.415, 0.685])
    gsR = fig.add_axes([0.735, 0.150, 0.115, 0.685], sharey=gsL)

    rows = []  # (y, metric, arm)
    y = 0.0
    for m in reversed(metrics):
        for arm in reversed(arms):
            rows.append((y, m, arm))
            y += 1.0
        y += 0.85

    for ax in (gsL, gsR):
        style_axis(ax)
        ax.axvspan(-1, 1, color=C["band"], zorder=0, lw=0)
        ax.axvline(0, color=C["axis"], lw=0.9, zorder=1)

    for yy, m, arm in rows:
        row = arm["rows"][m["key"]]
        verdict = row["verdict"]
        color = VERDICT_COLOR[verdict]
        marker = "o" if arm["key"] == "closed_loop" else "s"
        filled = arm["key"] == "closed_loop"

        if verdict == "insufficient_data":
            gsL.text(
                0.0,
                yy,
                "n = 0/8 — no bootstrap CI computable",
                fontsize=7.8,
                color=C["muted"],
                style="italic",
                va="center",
                ha="center",
                zorder=4,
                bbox=dict(fc=C["surface"], ec="none", pad=1.4),
            )
        else:
            lo, hi = (v / m["margin"] for v in row["ci"])
            mid = row["delta"] / m["margin"]
            for ax in (gsL, gsR):
                ax.plot([lo, hi], [yy, yy], color=color, lw=2.0, solid_capstyle="round", zorder=3)
                ax.plot(
                    [mid],
                    [yy],
                    marker=marker,
                    ms=6.5,
                    mfc=color if filled else C["surface"],
                    mec=color,
                    mew=1.6,
                    zorder=4,
                )

        # arm label, left gutter
        gsL.annotate(
            arm["label"],
            xy=(-0.012, yy),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=8.2,
            color=C["ink2"],
        )
        # verdict label, right gutter -- verdict is never colour-alone
        gsR.annotate(
            VERDICT_TEXT[verdict],
            xy=(1.045, yy),
            xycoords=("axes fraction", "data"),
            ha="left",
            va="center",
            fontsize=8.2,
            color=C["ink"] if verdict == "b_better" else C["ink2"],
            fontweight="bold" if verdict == "b_better" else "normal",
        )

    # metric headers
    for m in metrics:
        ys = [yy for yy, mm, _ in rows if mm["key"] == m["key"]]
        unit = f" {m['unit']}" if m["unit"] else ""
        gsL.annotate(
            f"{m['label']}   margin ±{m['margin']:g}{unit}",
            xy=(-0.012, max(ys) + 0.72),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color=C["ink"],
        )

    gsL.set_xlim(-1.35, 1.35)
    gsR.set_xlim(4.75, 6.15)
    gsL.set_ylim(-0.9, max(r[0] for r in rows) + 1.25)
    gsL.set_yticks([])
    gsR.set_yticks([])
    gsL.set_xticks([-1, -0.5, 0, 0.5, 1])
    gsL.set_xticklabels(["−1×", "−0.5×", "0", "+0.5×", "+1×"])
    gsR.set_xticks([5, 6])
    gsR.set_xticklabels(["+5×", "+6×"])
    gsR.spines["bottom"].set_visible(True)

    # axis-break marks
    kw = dict(transform=fig.transFigure, color=C["axis"], lw=1.0, clip_on=False)
    for x0 in (0.7255, 0.7345):
        fig.add_artist(Line2D([x0 - 0.004, x0 + 0.004], [0.137, 0.163], **kw))

    gsL.text(
        0.0,
        -0.62,
        "parity zone — the whole 95 % CI inside ±1 margin",
        ha="center",
        va="center",
        fontsize=8,
        color=C["ink2"],
    )

    # the two rows the report says must not be read as ordinary parity
    kn = next(
        yy for yy, m, a in rows if m["key"] == "one_hop_wall_ms" and a["key"] == "closed_loop"
    )
    gsL.annotate(
        "CI upper is 0.971× the margin — at any\nmargin ≤ ≈1.94 ms this row returns\ntier4-native better, not undecided",
        xy=(0.971, kn),
        xytext=(-1.30, kn - 0.62),
        fontsize=7.8,
        color=C["ink2"],
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.8, shrinkA=4, shrinkB=3),
    )
    dg = next(
        yy for yy, m, a in rows if m["key"] == "achieved_rate_ratio" and a["key"] == "closed_loop"
    )
    gsL.annotate(
        "degenerate interval —\ncontributes no evidence either way",
        xy=(0.0, dg),
        xytext=(-1.30, dg + 0.42),
        fontsize=7.8,
        color=C["ink2"],
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.8, shrinkA=4, shrinkB=5),
    )

    legend = [
        Line2D(
            [], [], marker="o", ls="none", ms=6.5, mfc=C["s1"], mec=C["s1"], label="closed-loop arm"
        ),
        Line2D(
            [],
            [],
            marker="s",
            ls="none",
            ms=6.5,
            mfc=C["surface"],
            mec=C["s1"],
            mew=1.6,
            label="static arm",
        ),
        Line2D([], [], color=C["critical"], lw=2.0, label="separated beyond margin"),
    ]
    fig.legend(
        handles=legend,
        loc="lower right",
        bbox_to_anchor=(0.995, 0.862),
        frameon=False,
        fontsize=8,
        ncol=3,
        handletextpad=0.5,
        columnspacing=1.4,
    )

    title_block(
        fig,
        "Extension vs tier4-native: every Δ against its own pre-registered margin",
        "Δ = extension − tier4-native, divided by that metric's margin; lower is better, so a positive Δ runs against the extension.\n"
        "Both arms are A-vs-B-cyc — tier4-native on CycloneDDS, not on the transport it ships.",
        "Sources: report.md §3.3 (closed-loop), §3.2 (static). Every row also spans an uncorrected Autoware container-image difference.\n"
        "The four in-band rows are not four equal results — see the two callouts, and the draft's §3.1.",
        y=0.983,
        foot_y=0.020,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 2. The CPU reversal -- draft section 3.2
# ---------------------------------------------------------------------------
def fig_cpu_reversal(d: dict, out: Path) -> Path:
    cr = d["cpu_reversal"]
    margin = cr["margin"]
    rows = cr["rows"]

    fig = plt.figure(figsize=(10.6, 3.5))
    ax = fig.add_axes([0.325, 0.245, 0.505, 0.50])
    style_axis(ax)
    ax.axvspan(-margin, margin, color=C["band"], zorder=0, lw=0)
    ax.axvline(0, color=C["axis"], lw=0.9, zorder=1)

    ys = list(range(len(rows) - 1, -1, -1))
    for y, r in zip(ys, rows):
        color = VERDICT_COLOR[r["verdict"]]
        lo, hi = r["ci"]
        ax.plot([lo, hi], [y, y], color=color, lw=2.4, solid_capstyle="round", zorder=3)
        ax.plot([r["delta"]], [y], "o", ms=7, mfc=color, mec=color, zorder=4)
        ax.annotate(
            f"{r['delta']:+.3f} pp".replace("-", "−"),
            xy=(r["delta"], y),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=8.2,
            fontweight="bold",
            color=C["ink"],
        )
        ax.annotate(
            r["label"],
            xy=(-0.012, y + 0.10),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=C["ink"],
        )
        ax.annotate(
            r["sublabel"],
            xy=(-0.012, y - 0.20),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=7.6,
            color=C["muted"],
        )
        ax.annotate(
            VERDICT_TEXT[r["verdict"]],
            xy=(1.02, y),
            xycoords=("axes fraction", "data"),
            ha="left",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color=C["ink"],
        )

    ax.set_xlim(-22, 64)
    ax.set_ylim(-0.6, len(rows) - 0.35)
    ax.set_yticks([])
    ax.set_xticks([-20, -10, 0, 10, 20, 30, 40, 50, 60])
    ax.set_xticklabels(["−20", "−10", "0", "10", "20", "30", "40", "50", "60"])
    ax.set_xlabel("Δ simulator-process CPU (percentage points)", fontsize=8.4, color=C["ink2"])
    ax.annotate(
        "±10 pp margin",
        xy=(0, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(0, 7),
        textcoords="offset points",
        ha="center",
        fontsize=7.8,
        color=C["ink2"],
    )

    title_block(
        fig,
        "The one reversal the campaign did not resolve: simulator-process CPU",
        "Same metric, same two approaches, three measurement conditions. The sign flips with the transport condition — but the pre-registered rule\n"
        "attributes the P3 → P4 change on the metrics that returned parity to the transport, and does not license retro-attributing this row.",
        "Sources: report.md §3.2; P3 row p3-baseline.md §4.2, P4 rows p4-transport-sweep.md §2.5. Cause not established on either P4 row.\n"
        "This row and those three cannot both be an approach difference.",
        foot_y=0.035,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 3. The seam ceiling -- draft section 3.3
# ---------------------------------------------------------------------------
def fig_seam(d: dict, out: Path) -> Path:
    s = d["seam"]
    runs = s["runs"]

    fig = plt.figure(figsize=(10.6, 3.8))
    axL = fig.add_axes([0.085, 0.235, 0.44, 0.46])
    axR = fig.add_axes([0.625, 0.235, 0.30, 0.46])
    for ax in (axL, axR):
        style_axis(ax)

    ys = list(range(len(runs) - 1, -1, -1))
    for y, r in zip(ys, runs):
        axL.plot([r["in_core"], r["seam"]], [y, y], color=C["axis"], lw=1.4, zorder=2)
        axL.plot([r["in_core"]], [y], "o", ms=7, mfc=C["s3"], mec=C["s3"], zorder=3)
        axL.plot([r["seam"]], [y], "o", ms=7, mfc=C["s2"], mec=C["s2"], zorder=3)
        axL.annotate(
            f"+{r['delta']:.4f}",
            xy=((r["in_core"] + r["seam"]) / 2, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7.8,
            color=C["ink2"],
        )
    axL.set_yticks(ys)
    axL.set_yticklabels([r["run"] for r in runs], fontsize=8.2, color=C["ink2"])
    axL.tick_params(axis="y", length=0)
    axL.set_xlim(0.40, 0.82)
    axL.set_ylim(-1.45, len(runs) - 0.25)
    axL.set_xlabel(
        "p50 one-hop (ms) — same 921 908-byte cloud, same CARLA process",
        fontsize=8.2,
        color=C["ink2"],
    )
    fig.legend(
        handles=[
            Line2D([], [], marker="o", ls="none", ms=7, color=C["s3"], label="in-core twin"),
            Line2D(
                [], [], marker="o", ls="none", ms=7, color=C["s2"], label="through the C ABI seam"
            ),
        ],
        loc="lower left",
        bbox_to_anchor=(0.085, 0.735),
        frameon=False,
        fontsize=8,
        ncol=2,
    )

    for y, r in zip(ys, runs):
        axR.plot([r["delta"]], [y], "o", ms=7, mfc=C["s2"], mec=C["s2"], zorder=3)
    axR.axvline(s["median"], color=C["ink2"], lw=1.0, ls=(0, (4, 2)), zorder=2)
    axR.axvline(s["ceiling"], color=C["critical"], lw=1.4, zorder=2)
    axR.annotate(
        f"median\n+{s['median']:.4f}",
        xy=(s["median"], len(runs) - 0.30),
        xytext=(-5, 0),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=7.8,
        color=C["ink2"],
    )
    axR.annotate(
        f"quote this: +{s['ceiling']:.4f} ms — a ceiling, not a point estimate",
        xy=(s["ceiling"], -1.02),
        xytext=(-5, 0),
        textcoords="offset points",
        ha="right",
        va="center",
        fontsize=7.8,
        fontweight="bold",
        color=C["critical"],
    )
    axR.set_yticks([])
    axR.set_xlim(0.232, 0.3045)
    axR.set_ylim(-1.45, len(runs) - 0.25)
    axR.set_xticks([0.24, 0.26, 0.28, 0.30])
    axR.set_xlabel("Δ p50 (ms) — positive in 5 of 5 runs", fontsize=8.2, color=C["ink2"])

    title_block(
        fig,
        "What the C ABI seam costs: an upper bound of +0.2988 ms, measured 5 of 5 times",
        "Both twins publish an identical cloud inside one CARLA process, so the Δ is paired and within-run. Against the registered claim\n"
        '("no measurable overhead") this is a downgrade — an overhead WAS measured. It is small and bounded, not zero.',
        "Source: report.md §3.1; regeneration report.md §9 command 4b. n = 5. The tails do not separate, and no claim is made about them at this n.",
        foot_y=0.030,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 4. The python-bridge NDT rate -- draft section 3.4
# ---------------------------------------------------------------------------
def fig_bridge(d: dict, out: Path) -> Path:
    b = d["bridge_ndt"]

    fig = plt.figure(figsize=(10.6, 3.4))
    ax = fig.add_axes([0.315, 0.315, 0.505, 0.345])
    style_axis(ax)
    ax.set_xscale("log")

    for ref in b["references"]:
        ax.axvline(ref["value"], color=C["axis"], lw=1.0, ls=(0, (3, 3)), zorder=1)
        ax.annotate(
            ref["label"],
            xy=(ref["value"], 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, 6 + 13 * ref["stagger"]),
            textcoords="offset points",
            ha="right" if ref["stagger"] else "center",
            va="bottom",
            fontsize=7.4,
            color=C["muted"],
        )

    for y, arm in zip((1, 0), b["arms"]):
        color = C["critical"] if arm["key"] == "e0" else C["s3"]
        ax.plot(
            [arm["lo"], arm["hi"]],
            [y, y],
            color=color,
            lw=9,
            solid_capstyle="butt",
            alpha=0.30,
            zorder=2,
        )
        ax.plot([arm["lo"], arm["hi"]], [y, y], color=color, lw=1.4, zorder=3)
        ax.plot([arm["median"]], [y], "o", ms=8, mfc=color, mec=C["surface"], mew=1.4, zorder=4)
        ax.annotate(
            f"{arm['lo']:g} – {arm['hi']:g} Hz    pooled median {arm['median']:g} Hz",
            xy=(arm["lo"], y),
            xytext=(0, 13),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=8.2,
            color=C["ink"],
        )
        ax.annotate(
            arm["label"],
            xy=(-0.012, y + 0.11),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=C["ink"],
        )
        ax.annotate(
            arm["sublabel"],
            xy=(-0.012, y - 0.16),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=7.6,
            color=C["muted"],
        )

    ax.set_xlim(0.05, 26)
    ax.set_ylim(-0.7, 1.7)
    ax.set_yticks([])
    ax.set_xticks([0.1, 1, 10])
    ax.set_xticklabels(["0.1", "1", "10"])
    ax.minorticks_off()
    ax.set_xlabel("NDT pose rate (Hz, log scale)", fontsize=8.4, color=C["ink2"])

    title_block(
        fig,
        "The python-bridge is starved by a one-flag contract mismatch, not by its architecture",
        "Same architecture, same CARLA, same container — the difference is the two registered patches. The pooled medians differ by ≈45× and the\n"
        "ranges do not overlap. No paired design exists between the arms, so no per-run recovery factor is computable: this is not a 45× speed-up claim.",
        "Sources: report.md §4.2, §4.3. The as-shipped figures are optimistically biased — 3 of the 4 excluded runs were the cell's worst, and the bias\n"
        "is not estimable from the surviving pool. The cause is a two-sided contract mismatch: the bridge publishes is_dense=False, a valid\n"
        "PointCloud2 value, and Autoware's crop_box_filter_self rejects every cloud carrying it.",
        foot_y=0.020,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 5. Fork delta carried -- draft section 3.5
# ---------------------------------------------------------------------------
def fig_fork_delta(d: dict, out: Path) -> Path:
    fd = d["fork_delta"]
    rows = fd["rows"]

    fig = plt.figure(figsize=(10.6, 3.1))
    ax = fig.add_axes([0.245, 0.315, 0.545, 0.365])
    style_axis(ax)

    kind_color = {"fork": C["s1"], "repo": C["s2"]}
    ys = list(range(len(rows) - 1, -1, -1))
    for y, r in zip(ys, rows):
        left = 0.0
        for seg in r["segments"]:
            v = seg["value"]
            if v == 0:
                ax.annotate(
                    "0",
                    xy=(0, y),
                    xytext=(6, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8.6,
                    fontweight="bold",
                    color=C["ink"],
                    zorder=4,
                )
                continue
            ax.barh(
                y, v, left=left, height=0.44, color=kind_color[seg["kind"]], zorder=3, linewidth=0
            )
            inside = v >= 40
            ax.annotate(
                f"{v}",
                xy=(left + v / 2 if inside else left + v, y),
                xytext=(0, 0) if inside else (6, 0),
                textcoords="offset points",
                ha="center" if inside else "left",
                va="center",
                fontsize=8.6,
                fontweight="bold",
                color=C["surface"] if inside else C["ink"],
                zorder=4,
            )
            left += v + 2  # 2-unit surface gap between adjacent segments
        ax.annotate(
            r["label"],
            xy=(-0.014, y + 0.13),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=C["ink"],
        )
        ax.annotate(
            r["sublabel"],
            xy=(-0.014, y - 0.17),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=7.6,
            color=C["muted"],
        )

    ax.set_xlim(0, 330)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks([])
    ax.set_xlabel("commits carried outside upstream CARLA", fontsize=8.4, color=C["ink2"])
    fig.legend(
        handles=[Patch(fc=kind_color[k], label=v) for k, v in fd["segment_labels"].items()],
        loc="lower left",
        bbox_to_anchor=(0.245, 0.705),
        frameon=False,
        fontsize=8,
        ncol=2,
        handlelength=1.2,
        handleheight=0.9,
    )

    title_block(
        fig,
        "What each approach carries outside upstream CARLA",
        "A dated snapshot over moving refs, not a regenerable number — endpoint SHAs are pinned in the report.",
        "Source: report.md §3.5. The upstreaming ratios in the same section are deliberately NOT charted: they are computed over different\n"
        "populations, and the report states that no ordering between those cells is supported.",
        foot_y=0.030,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 6. The capability catalog -- draft section 4
# ---------------------------------------------------------------------------
def fig_capability(d: dict, out: Path) -> Path:
    cap = d["capability"]
    classes = cap["classes"]
    effort = cap["effort"]

    fig = plt.figure(figsize=(10.6, 3.7))
    axT = fig.add_axes([0.185, 0.590, 0.585, 0.155])
    axB = fig.add_axes([0.185, 0.260, 0.585, 0.155])
    for ax in (axT, axB):
        style_axis(ax)

    cls_colors = [C["s3"], C["s1"], C["s2"], C["s4"]]
    for y, key, label in ((1, "main", "integration branch"), (0, "side", "side branches")):
        left = 0.0
        for i, cl in enumerate(classes):
            v = cl[key]
            axT.barh(y, v, left=left, height=0.46, color=cls_colors[i], zorder=3, linewidth=0)
            axT.annotate(
                str(v),
                xy=(left + v / 2, y),
                ha="center",
                va="center",
                fontsize=8.4,
                fontweight="bold",
                color=C["surface"] if i != 3 else C["ink"],
                zorder=4,
            )
            left += v + 0.35
        axT.annotate(
            f"{label}  ({sum(cl[key] for cl in classes)})",
            xy=(-0.012, y),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color=C["ink"],
        )
    axT.set_xlim(0, 29)
    axT.set_ylim(-0.55, 1.55)
    axT.set_yticks([])
    axT.set_xticks([])
    axT.spines["bottom"].set_visible(False)
    axT.xaxis.grid(False)
    fig.legend(
        handles=[Patch(fc=cls_colors[i], label=cl["label"]) for i, cl in enumerate(classes)],
        loc="lower left",
        bbox_to_anchor=(0.185, 0.748),
        frameon=False,
        fontsize=8,
        ncol=2,
        handlelength=1.2,
        handleheight=0.9,
        columnspacing=1.6,
    )

    eff_colors = [C["s1"], C["s2"], C["s4"]]
    for y, row in zip((1, 0), effort):
        left = 0.0
        for i, k in enumerate(("S", "M", "L")):
            v = row[k]
            if not v:
                continue
            axB.barh(y, v, left=left, height=0.46, color=eff_colors[i], zorder=3, linewidth=0)
            axB.annotate(
                f"{v} × {k}",
                xy=(left + v / 2, y),
                ha="center",
                va="center",
                fontsize=8.0,
                fontweight="bold",
                color=C["surface"] if i != 2 else C["ink"],
                zorder=4,
            )
            left += v + 0.35
        axB.annotate(
            row["label"],
            xy=(-0.012, y),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color=C["ink"],
        )
    axB.set_xlim(0, 29)
    axB.set_ylim(-0.55, 1.55)
    axB.set_yticks([])
    axB.set_xticks([])
    axB.spines["bottom"].set_visible(False)
    axB.xaxis.grid(False)
    fig.text(
        0.185,
        0.470,
        "effort class per entry — the REMAINING delta from the extension's side, never cumulative",
        fontsize=8.4,
        color=C["ink2"],
    )
    fig.text(
        0.787,
        0.745,
        f"{cap['unpriced']} entries depend on artifacts\nthat exist in neither tree — their\ncost is a lower bound, not a\nreachability class",
        fontsize=7.8,
        va="top",
        color=C["ink2"],
    )
    fig.text(
        0.787,
        0.415,
        f"the adversarial re-argument covered\nthe {cap['second_pass_scope']} already-exists verdicts only;\nthe other 39 had one pass each",
        fontsize=7.8,
        va="top",
        color=C["ink2"],
    )

    title_block(
        fig,
        "The capability roadmap: 53 entries, and where the work actually sits",
        "Code reading at pinned SHAs — no running stack, no runtime measurement backs any verdict in it. The side-branch half skews far harder\n"
        "toward CARLA-core seam work (18 of 25, against 13 of 28 on main); that statistic received no second pass and no inter-rater check.",
        "Source: gap-catalog.md, summarized report.md §5. A class is the remaining delta from this repository's side, not the size of tier4's\n"
        'original change — "89 % of tier4\'s merged integration work is a small lift" is NOT what this figure says.',
        foot_y=0.020,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 7. Governance -- draft section 5
# ---------------------------------------------------------------------------
def fig_governance(d: dict, out: Path) -> Path:
    g = d["governance"]
    conc = g["concentration"]
    rec = g["review_record"]

    fig = plt.figure(figsize=(10.6, 4.4))
    ax = fig.add_axes([0.245, 0.505, 0.50, 0.215])
    style_axis(ax)

    ys = list(range(len(conc) - 1, -1, -1))
    for y, r in zip(ys, conc):
        pct = 100.0 * r["top2"] / r["total"]
        ax.barh(y, pct, height=0.46, color=C["s1"], zorder=3, linewidth=0)
        ax.annotate(
            f"{pct:.0f} %   ({r['top2']}/{r['total']})",
            xy=(pct, y),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8.4,
            fontweight="bold",
            color=C["ink"],
        )
        ax.annotate(
            r["label"],
            xy=(-0.015, y),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="center",
            fontsize=8.4,
            color=C["ink2"],
        )
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, len(conc) - 0.4)
    ax.set_yticks([])
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("share of commits by the top 2 authors", fontsize=8.2, color=C["ink2"])
    fig.text(
        0.245,
        0.745,
        "Bus factor does NOT separate the two natives",
        fontsize=9,
        fontweight="bold",
        color=C["ink"],
    )

    # The separation is on the review record. A "0" is a hero number, not a bar:
    # a four-bar chart of 0 / 2 / 1 / 4 would encode nothing the numerals do not.
    fig.text(
        0.062,
        0.355,
        "The review record does",
        fontsize=9,
        fontweight="bold",
        color=C["ink"],
    )
    mnt = g["maintainers"]
    tiles = [
        (
            f"{rec['external_reviewers']}",
            f"external reviewers ever,\nacross {rec['prs_opened']} PRs",
            C["critical"],
        ),
        (f"{rec['self_reviews']}", "self-reviews — the only\nreviews ever recorded", C["ink"]),
        (
            f"{rec['commits']}/{rec['commits']}",
            f"commits in this repo by\n{rec['commit_authors']} author",
            C["ink"],
        ),
        (
            f"{mnt['extension']} vs {mnt['python_bridge']}",
            "named maintainers,\nextension vs python-bridge",
            C["ink"],
        ),
    ]
    for i, (value, label, color) in enumerate(tiles):
        x = 0.062 + i * 0.238
        fig.text(
            x, 0.245, value, fontsize=21, fontweight="bold", color=color, va="center", ha="left"
        )
        fig.text(x, 0.150, label, fontsize=7.8, color=C["ink2"], va="center", ha="left")

    title_block(
        fig,
        "Where this proposal is weakest — and it is not the bus factor",
        "The extension's required fork and tier4-native's branch show the SAME 52 % top-2 concentration. The extension separates on review:\n"
        "no external reviewer has ever reviewed a PR in this repository, and no human approval is required on main.",
        "Sources: report.md §3.5; rubric.md criteria 1 and 6. tier4-native's branch has no GitHub-side approval gate either — but an internal\n"
        "review process would not be visible to this snapshot, and the absence of a ruleset is not the absence of governance.",
        foot_y=0.020,
    )
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


FIGURES = {
    "fig-equivalence-forest": fig_equivalence,
    "fig-cpu-reversal": fig_cpu_reversal,
    "fig-seam-ceiling": fig_seam,
    "fig-bridge-ndt": fig_bridge,
    "fig-fork-delta": fig_fork_delta,
    "fig-capability-catalog": fig_capability,
    "fig-governance": fig_governance,
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preview", type=Path, help="also write PNGs here, for eyeballing")
    p.add_argument("--only", action="append", choices=sorted(FIGURES), help="render a subset")
    args = p.parse_args()

    data = load()
    names = args.only or sorted(FIGURES)
    for name in names:
        out = FIGURES[name](data, HERE / f"{name}.svg")
        print(f"wrote {out}")
        if args.preview:
            args.preview.mkdir(parents=True, exist_ok=True)
            png = FIGURES[name](data, args.preview / f"{name}.png")
            print(f"  preview {png}")


if __name__ == "__main__":
    main()

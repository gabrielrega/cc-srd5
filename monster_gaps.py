#!/usr/bin/env python3
"""
Gap analysis: find underserved niches in the SRD 5.1 monster roster.

Four axes:
  1. CR × Type coverage heatmap
  2. Alignment × Type matrix
  3. Movement mode × CR heatmap
  4. Damage type in attacks × CR bucket
  + Scored gap-candidate table
"""

import re
import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

DB  = "monsters.duckdb"
OUT = "monster_gaps.png"

con = duckdb.connect(DB, read_only=True)

# ── style ─────────────────────────────────────────────────────────────────────
BG    = "#1a1a2e"
PANEL = "#16213e"
TEXT  = "#e0e0e0"
GRID  = "#2a2a4e"
RED   = "#e94560"
GOLD  = "#f5a623"
GREEN = "#2ecc71"

plt.rcParams.update({
    "font.family":    "DejaVu Sans",
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "text.color":     TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color":    TEXT,
    "ytick.color":    TEXT,
})

CMAP_FILLED = LinearSegmentedColormap.from_list(
    "filled", ["#16213e", "#1a6b8a", "#1eb8c0", "#f5a623"])
CMAP_GAP = LinearSegmentedColormap.from_list(
    "gap", ["#16213e", "#4a1a2e", "#e94560"])

CR_BUCKETS  = ["0", "½–",  "1–4",  "5–10",  "11–16", "17+"]
MID_BUCKETS = {"1–4", "5–10", "11–16"}   # highest gameplay priority

def cr_bucket(cr):
    if cr is None or cr in ("—",):
        return None
    if cr == "0":
        return "0"
    if cr in ("1/8", "1/4", "1/2"):
        return "½–"
    try:
        n = int(cr)
        if   n <= 4:  return "1–4"
        elif n <= 10: return "5–10"
        elif n <= 16: return "11–16"
        else:         return "17+"
    except ValueError:
        return None

def clean_type(t):
    if not isinstance(t, str):
        return None
    t = re.sub(r"\s*\(.*", "", t).strip()
    return t if t else None

# ── load base data ────────────────────────────────────────────────────────────
df = con.execute("""
    SELECT id, name, cr, type, alignment, size, speeds,
           damage_immunities, damage_resistances
    FROM monsters
""").df()
df["cr_bucket"]  = df["cr"].map(cr_bucket)
df["clean_type"] = df["type"].map(clean_type)

acts = con.execute("""
    SELECT m.id, m.cr, a.damage_type
    FROM monster_actions a
    JOIN monsters m ON m.id = a.monster_id
    WHERE a.is_attack AND a.damage_type IS NOT NULL
""").df()
acts["cr_bucket"] = acts["cr"].map(cr_bucket)

# ── Axis 1: CR × Type pivot ───────────────────────────────────────────────────
# Keep types with ≥ 4 monsters
type_counts = df["clean_type"].value_counts()
major_types = type_counts[type_counts >= 4].index.tolist()
# Drop beast (87 entries — trivially fills everything, obscures gaps)
major_types = [t for t in major_types if t not in ("beast", "swarm of Tiny beasts")]

ax1_df = (
    df[df["clean_type"].isin(major_types) & df["cr_bucket"].notna()]
    .groupby(["clean_type", "cr_bucket"])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=CR_BUCKETS, fill_value=0)
)
# Sort rows by total count descending
ax1_df = ax1_df.loc[ax1_df.sum(axis=1).sort_values(ascending=False).index]

# ── Axis 2: Alignment × Type matrix ──────────────────────────────────────────
ALIGN_ORDER = [
    "lawful good",   "neutral good",   "chaotic good",
    "lawful neutral","neutral",        "chaotic neutral",
    "lawful evil",   "neutral evil",   "chaotic evil",
]
ALIGN_LABELS = [
    "LG", "NG", "CG",
    "LN", "N",  "CN",
    "LE", "NE", "CE",
]

ax2_df = (
    df[
        df["clean_type"].isin(major_types) &
        df["alignment"].isin(ALIGN_ORDER)
    ]
    .groupby(["clean_type", "alignment"])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=ALIGN_ORDER, fill_value=0)
)
ax2_df = ax2_df.loc[ax2_df.sum(axis=1).sort_values(ascending=False).index]
ax2_df.columns = ALIGN_LABELS

# ── Axis 3: Movement mode × CR bucket ────────────────────────────────────────
MODES = ["walk", "fly", "swim", "burrow", "climb"]
move_rows = []
for _, row in df.iterrows():
    bucket = row["cr_bucket"]
    speeds_val = row["speeds"]
    if bucket is None or speeds_val is None:
        continue
    # DuckDB returns STRUCT[] as numpy array of dicts
    try:
        speeds_iter = list(speeds_val)
    except TypeError:
        continue
    modes_present = {s["mode"] for s in speeds_iter if isinstance(s, dict)}
    for mode in MODES:
        move_rows.append({
            "cr_bucket": bucket,
            "mode":      mode,
            "has":       int(mode in modes_present),
            "name":      row["name"],
        })

move_df = pd.DataFrame(move_rows)
# Count of monsters with each movement mode at each CR bucket
move_pivot = (
    move_df[move_df["has"] == 1]
    .groupby(["mode", "cr_bucket"])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=CR_BUCKETS, fill_value=0)
)
# Total monsters per bucket (for context)
total_per_bucket = df[df["cr_bucket"].notna()].groupby("cr_bucket").size().reindex(CR_BUCKETS, fill_value=0)

# ── Axis 4: Damage type × CR bucket ──────────────────────────────────────────
DTYPES = ["piercing","slashing","bludgeoning","fire","cold","lightning",
          "acid","necrotic","psychic","radiant","thunder","force","poison"]

ax4_pivot = (
    acts[acts["cr_bucket"].notna()]
    .groupby(["damage_type", "cr_bucket"])
    .size()
    .unstack(fill_value=0)
    .reindex(index=DTYPES, columns=CR_BUCKETS, fill_value=0)
)

# ── Gap scoring ───────────────────────────────────────────────────────────────
# For each zero cell in CR × Type we calculate a score:
#   +2  if bucket is in MID_BUCKETS
#   +1  if the left or right neighbouring bucket is non-zero (it's a hole)
#   +1  if both neighbours are non-zero (surrounded hole)

# Plausibility whitelist: (type, bucket) combos that make narrative sense
PLAUSIBLE = {
    ("fey",        "5–10"),
    ("fey",        "11–16"),
    ("celestial",  "5–10"),
    ("celestial",  "11–16"),
    ("aberration", "1–4"),
    ("aberration", "5–10"),
    ("plant",      "11–16"),
    ("plant",      "17+"),
    ("ooze",       "5–10"),
    ("ooze",       "11–16"),
    ("construct",  "11–16"),
    ("construct",  "17+"),
    ("fiend",      "0"),
    ("fiend",      "½–"),
    ("undead",     "17+"),
}

gap_candidates = []
for t in ax1_df.index:
    row_vals = ax1_df.loc[t]
    type_total = row_vals.sum()
    for bi, bucket in enumerate(CR_BUCKETS):
        if row_vals[bucket] > 0:
            continue
        score = 0
        if bucket in MID_BUCKETS:
            score += 2
        left_filled  = bi > 0 and row_vals.iloc[bi-1] > 0
        right_filled = bi < len(CR_BUCKETS)-1 and row_vals.iloc[bi+1] > 0
        if left_filled or right_filled:
            score += 1
        if left_filled and right_filled:
            score += 1
        plausible = (t, bucket) in PLAUSIBLE
        if score > 0:
            gap_candidates.append({
                "type":       t,
                "cr_bucket":  bucket,
                "score":      score,
                "plausible":  plausible,
                "type_total": int(type_total),
            })

gap_df = (
    pd.DataFrame(gap_candidates)
    .sort_values(["score","plausible","type_total"], ascending=[False,False,False])
    .reset_index(drop=True)
)

# Damage type gaps: buckets with zero non-physical damage attacks
NONPHYS = [d for d in DTYPES if d not in ("piercing","slashing","bludgeoning")]
dmg_gaps = []
for dtype in NONPHYS:
    for bucket in MID_BUCKETS:
        if ax4_pivot.loc[dtype, bucket] == 0:
            dmg_gaps.append({"type": f"{dtype} damage", "cr_bucket": bucket,
                             "score": 2, "plausible": True, "type_total": 0})
dmg_gap_df = pd.DataFrame(dmg_gaps).sort_values("type")

# ── figure ────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(22, 26))
fig.patch.set_facecolor(BG)

GS = GridSpec(3, 2, figure=fig,
              height_ratios=[1.1, 1.0, 0.95],
              hspace=0.38, wspace=0.28,
              left=0.07, right=0.97, top=0.94, bottom=0.04)

AX1 = fig.add_subplot(GS[0, :])    # CR × Type  — full width
AX2 = fig.add_subplot(GS[1, 0])    # Alignment × Type
AX3 = fig.add_subplot(GS[1, 1])    # Movement × CR
AX4 = fig.add_subplot(GS[2, 0])    # Damage type × CR
AX5 = fig.add_subplot(GS[2, 1])    # Gap candidate table

for ax in fig.axes:
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)

fig.suptitle("SRD 5.1 Monster Roster — Gap Analysis",
             fontsize=16, color=TEXT, fontweight="bold", y=0.97)

# ── Panel 1: CR × Type ───────────────────────────────────────────────────────
# Custom colormap: zero = dark red, non-zero = blue gradient
cmap_custom = CMAP_FILLED
annot = ax1_df.copy().astype(str)
annot[ax1_df == 0] = "—"

# Build a masked version: zeros in mid-CR columns are highlighted
highlight_mask = (ax1_df == 0) & ax1_df.columns.isin(MID_BUCKETS)

sns.heatmap(ax1_df, ax=AX1, cmap=CMAP_FILLED,
            annot=annot, fmt="", annot_kws={"size": 9},
            linewidths=0.5, linecolor=GRID,
            cbar_kws={"shrink": 0.6, "label": "# Monsters"})

# Overlay red boxes on priority gaps
for ri, t in enumerate(ax1_df.index):
    for ci, bucket in enumerate(ax1_df.columns):
        if ax1_df.loc[t, bucket] == 0 and bucket in MID_BUCKETS:
            AX1.add_patch(plt.Rectangle((ci, ri), 1, 1,
                fill=True, facecolor="#4a0a1e", edgecolor=RED,
                linewidth=1.8, zorder=2))
            AX1.text(ci+0.5, ri+0.5, "gap", ha="center", va="center",
                     color=RED, fontsize=7, fontweight="bold", zorder=3)

AX1.set_title("CR Bucket × Creature Type  (red = priority gap in mid-CR range)", color=TEXT)
AX1.set_xlabel("CR Bucket", color=TEXT)
AX1.set_ylabel("")
AX1.tick_params(axis="x", rotation=0)
AX1.tick_params(axis="y", rotation=0)
AX1.collections[0].colorbar.ax.tick_params(colors=TEXT, labelsize=7)
AX1.collections[0].colorbar.set_label("# Monsters", color=TEXT)

# ── Panel 2: Alignment × Type ────────────────────────────────────────────────
annot2 = ax2_df.copy().astype(str)
annot2[ax2_df == 0] = "—"

# Mask: zeros for types that have aligned representatives somewhere (not all-zero row)
has_any_alignment = ax2_df.sum(axis=1) > 0

sns.heatmap(ax2_df, ax=AX2, cmap=CMAP_FILLED,
            annot=annot2, fmt="",
            annot_kws={"size": 8},
            linewidths=0.5, linecolor=GRID,
            cbar_kws={"shrink": 0.6})

# Highlight zero cells for types with any aligned monsters
for ri, t in enumerate(ax2_df.index):
    if not has_any_alignment[t]:
        continue
    for ci, col in enumerate(ax2_df.columns):
        if ax2_df.loc[t, col] == 0:
            AX2.add_patch(plt.Rectangle((ci, ri), 1, 1,
                fill=True, facecolor="#2a0a1a", edgecolor="#884466",
                linewidth=0.8, zorder=2, alpha=0.5))

AX2.set_title("Alignment × Creature Type  (dim = unexplored combo)", color=TEXT)
AX2.set_xlabel("Alignment  (L/N/C × G/N/E)", color=TEXT)
AX2.set_ylabel("")
AX2.tick_params(axis="x", rotation=0)
AX2.tick_params(axis="y", rotation=0)
AX2.collections[0].colorbar.ax.tick_params(colors=TEXT, labelsize=7)

# ── Panel 3: Movement × CR ───────────────────────────────────────────────────
# Show counts, but also annotate "0" cells visibly
annot3 = move_pivot.copy().astype(str)
annot3[move_pivot == 0] = "0"

sns.heatmap(move_pivot, ax=AX3, cmap=CMAP_FILLED,
            annot=annot3, fmt="",
            annot_kws={"size": 9},
            linewidths=0.5, linecolor=GRID,
            cbar_kws={"shrink": 0.6})

# Highlight zeros in mid-CR
for ri, mode in enumerate(move_pivot.index):
    for ci, bucket in enumerate(move_pivot.columns):
        if move_pivot.loc[mode, bucket] == 0 and bucket in MID_BUCKETS:
            AX3.add_patch(plt.Rectangle((ci, ri), 1, 1,
                fill=True, facecolor="#4a0a1e", edgecolor=RED,
                linewidth=1.8, zorder=2))
            AX3.text(ci+0.5, ri+0.5, "gap", ha="center", va="center",
                     color=RED, fontsize=7, fontweight="bold", zorder=3)

# Add total-per-bucket row label at top
ax3_twin = AX3.twiny()
ax3_twin.set_xlim(AX3.get_xlim())
ax3_twin.set_xticks([i + 0.5 for i in range(len(CR_BUCKETS))])
ax3_twin.set_xticklabels(
    [f"n={total_per_bucket.get(b,0)}" for b in CR_BUCKETS],
    fontsize=7, color="#aaa")
ax3_twin.tick_params(colors="#aaa")
ax3_twin.set_facecolor(PANEL)
for spine in ax3_twin.spines.values():
    spine.set_edgecolor(GRID)

AX3.set_title("Movement Mode × CR  (count of monsters)", color=TEXT)
AX3.set_xlabel("CR Bucket", color=TEXT)
AX3.set_ylabel("Movement Mode", color=TEXT)
AX3.tick_params(axis="x", rotation=0)
AX3.collections[0].colorbar.ax.tick_params(colors=TEXT, labelsize=7)

# ── Panel 4: Damage type × CR bucket ─────────────────────────────────────────
annot4 = ax4_pivot.copy().astype(str)
annot4[ax4_pivot == 0] = "—"

sns.heatmap(ax4_pivot, ax=AX4, cmap=CMAP_FILLED,
            annot=annot4, fmt="",
            annot_kws={"size": 8},
            linewidths=0.5, linecolor=GRID,
            cbar_kws={"shrink": 0.6})

# Highlight zero non-physical damage in mid-CR
PHYSICAL = {"piercing","slashing","bludgeoning"}
for ri, dtype in enumerate(ax4_pivot.index):
    for ci, bucket in enumerate(ax4_pivot.columns):
        if ax4_pivot.loc[dtype, bucket] == 0 and bucket in MID_BUCKETS and dtype not in PHYSICAL:
            AX4.add_patch(plt.Rectangle((ci, ri), 1, 1,
                fill=True, facecolor="#4a0a1e", edgecolor=RED,
                linewidth=1.5, zorder=2))
            AX4.text(ci+0.5, ri+0.5, "—", ha="center", va="center",
                     color=RED, fontsize=8, zorder=3)

AX4.set_title("Attack Damage Type × CR  (# attack actions)", color=TEXT)
AX4.set_xlabel("CR Bucket", color=TEXT)
AX4.set_ylabel("Damage Type", color=TEXT)
AX4.tick_params(axis="x", rotation=0)
AX4.tick_params(axis="y", rotation=0)
AX4.collections[0].colorbar.ax.tick_params(colors=TEXT, labelsize=7)

# ── Panel 5: Gap candidate table ──────────────────────────────────────────────
AX5.axis("off")
AX5.set_title("Top Gap Candidates  (scored by mid-CR priority + isolation)",
              color=TEXT)

# Combine type gaps + damage gaps; take top 20 most interesting
top_type_gaps = gap_df[gap_df["plausible"]].head(14)
top_dmg_gaps  = dmg_gap_df.drop_duplicates(subset=["type"]).head(6)

table_rows = []
for _, r in top_type_gaps.iterrows():
    stars = "★" * int(r["score"])
    table_rows.append([r["type"].title(), r["cr_bucket"], stars, "type"])
for _, r in top_dmg_gaps.iterrows():
    table_rows.append([r["type"].title(), r["cr_bucket"], "★★", "damage"])

col_labels = ["Gap Area", "CR Bucket", "Priority", "Axis"]
col_widths = [0.38, 0.22, 0.22, 0.18]

y_start = 0.95
row_h   = 0.057
header_color = "#0a3a5a"
row_colors   = ["#1a2a3e", "#16213e"]
axis_colors  = {"type": "#1a6b8a", "damage": "#4a1a4e"}

# Header
for ci, (label, w) in enumerate(zip(col_labels, col_widths)):
    x = sum(col_widths[:ci])
    AX5.add_patch(plt.Rectangle((x, y_start - row_h), w, row_h,
        transform=AX5.transAxes, color=header_color, zorder=2))
    AX5.text(x + w/2, y_start - row_h/2, label,
             transform=AX5.transAxes,
             ha="center", va="center", color=TEXT,
             fontsize=8, fontweight="bold", zorder=3)

for ri, row_data in enumerate(table_rows):
    y = y_start - row_h * (ri + 2)
    bg = row_colors[ri % 2]
    axis_val = row_data[3]
    for ci, (val, w) in enumerate(zip(row_data, col_widths)):
        x = sum(col_widths[:ci])
        cell_color = bg if ci != 3 else axis_colors.get(axis_val, bg)
        AX5.add_patch(plt.Rectangle((x, y), w, row_h,
            transform=AX5.transAxes, color=cell_color, zorder=2))
        color = GOLD if ci == 2 else TEXT
        AX5.text(x + w/2, y + row_h/2, str(val),
                 transform=AX5.transAxes,
                 ha="center", va="center",
                 color=color, fontsize=8, zorder=3)

# Legend
legend_x, legend_y = 0.0, y_start - row_h * (len(table_rows) + 2.5)
AX5.text(legend_x, legend_y,
         "★ = gap in mid-CR bucket  ★★ = isolated hole  ★★★ = surrounded hole in priority range",
         transform=AX5.transAxes, color="#aaa", fontsize=7)

# ── save ──────────────────────────────────────────────────────────────────────
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Saved {OUT}")

# Print gap summary to stdout too
print("\n── Top plausible type gaps (mid-CR priority) ──")
print(gap_df[gap_df["plausible"]][["type","cr_bucket","score"]].head(15).to_string(index=False))
print("\n── Non-physical damage absent from mid-CR attacks ──")
absent = [(d,b) for d in NONPHYS for b in MID_BUCKETS if ax4_pivot.loc[d,b] == 0]
for d, b in absent:
    print(f"  {d:<12} @ {b}")

con.close()

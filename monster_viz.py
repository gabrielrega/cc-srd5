#!/usr/bin/env python3
"""
Monster database visualizations — patterns and distributions from cc-srd5.md
"""

import re
import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib.gridspec import GridSpec

DB = "monsters.duckdb"
OUT = "monster_viz.png"

con = duckdb.connect(DB, read_only=True)

# ── palette ──────────────────────────────────────────────────────────────────
PALETTE = sns.color_palette("muted")
sns.set_theme(style="darkgrid", palette=PALETTE)
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titlesize": 11,
                     "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8})

# ── data pulls ────────────────────────────────────────────────────────────────

# 1. CR distribution with canonical ordering
cr_df = con.execute("""
    SELECT cr, COUNT(*) AS n FROM monsters
    WHERE cr != '—' AND cr IS NOT NULL
    GROUP BY cr
""").df()

CR_ORDER = ["0","1/8","1/4","1/2",
            "1","2","3","4","5","6","7","8","9","10",
            "11","12","13","14","15","16","17","18","19","20",
            "21","22","23","24","25","26","27","28","29","30"]
cr_df["cr_sort"] = cr_df["cr"].map({v: i for i, v in enumerate(CR_ORDER)})
cr_df = cr_df.sort_values("cr_sort")

# 2. Type distribution (strip parenthetical subtypes, clean trailing space)
type_df = con.execute("""
    SELECT TRIM(REGEXP_REPLACE(type, '\\s*\\(.*\\)', '')) AS base_type,
           COUNT(*) AS n
    FROM monsters
    WHERE type IS NOT NULL
    GROUP BY 1 ORDER BY n DESC
    LIMIT 12
""").df()

# 3. Ability scores — long form for box plots
scores_df = con.execute("""
    SELECT name, str, dex, con, int, wis, cha FROM monsters
    WHERE str IS NOT NULL
""").df()
scores_long = scores_df.melt(id_vars="name",
                              value_vars=["str","dex","con","int","wis","cha"],
                              var_name="ability", value_name="score")
scores_long["ability"] = scores_long["ability"].str.upper()

# 4. HP vs CR (numeric CRs only)
hp_cr_df = con.execute("""
    SELECT CAST(cr AS INT) AS cr_num, hp, name
    FROM monsters
    WHERE cr ~ '^[0-9]+$' AND hp IS NOT NULL
""").df()

# 5. Damage immunities
imm_df = con.execute("""
    SELECT dtype, COUNT(*) AS n FROM (
        SELECT UNNEST(damage_immunities) AS dtype FROM monsters
    )
    WHERE LOWER(dtype) IN (
        'acid','cold','fire','force','lightning','necrotic',
        'piercing','poison','psychic','radiant','slashing',
        'bludgeoning','thunder'
    )
    GROUP BY 1 ORDER BY n DESC
""").df()

# 6. Damage resistances
res_df = con.execute("""
    SELECT dtype, COUNT(*) AS n FROM (
        SELECT UNNEST(damage_resistances) AS dtype FROM monsters
    )
    WHERE LOWER(dtype) IN (
        'acid','cold','fire','force','lightning','necrotic',
        'piercing','poison','psychic','radiant','slashing',
        'bludgeoning','thunder'
    )
    GROUP BY 1 ORDER BY n DESC
""").df()

# 7. to_hit distribution
tohit_df = con.execute("""
    SELECT to_hit, COUNT(*) AS n FROM monster_actions
    WHERE to_hit IS NOT NULL
    GROUP BY 1 ORDER BY 1
""").df()

# 8. Alignment heatmap
align_df = con.execute("""
    SELECT alignment, COUNT(*) AS n FROM monsters
    WHERE alignment IS NOT NULL
    AND alignment NOT IN ('—', 'unaligned', 'any alignment', 'any evil alignment')
    AND alignment NOT LIKE '%(%'
    GROUP BY alignment
""").df()

LAW  = {"lawful": "Lawful", "neutral": "Neutral", "chaotic": "Chaotic"}
GOOD = {"good": "Good", "neutral": "Neutral", "evil": "Evil"}
align_matrix = pd.DataFrame(0, index=["Good","Neutral","Evil"],
                             columns=["Lawful","Neutral","Chaotic"])
for _, row in align_df.iterrows():
    parts = row["alignment"].lower().split()
    if len(parts) == 2:
        l_key, g_key = parts
        l_label = LAW.get(l_key); g_label = GOOD.get(g_key)
        if l_label and g_label:
            align_matrix.loc[g_label, l_label] += row["n"]
    elif len(parts) == 1 and parts[0] == "neutral":
        align_matrix.loc["Neutral", "Neutral"] += row["n"]

# 9. AC vs CR
ac_cr_df = con.execute("""
    SELECT CAST(cr AS INT) AS cr_num, ac, type, name
    FROM monsters WHERE cr ~ '^[0-9]+$' AND ac IS NOT NULL
""").df()

# ── figure layout ─────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 24))
fig.patch.set_facecolor("#1a1a2e")

GS = GridSpec(4, 3, figure=fig, hspace=0.42, wspace=0.35,
              left=0.07, right=0.97, top=0.94, bottom=0.04)

AX_CR       = fig.add_subplot(GS[0, :2])   # wide — CR distribution
AX_TYPE     = fig.add_subplot(GS[0, 2])    # type counts
AX_SCORES   = fig.add_subplot(GS[1, :2])   # ability score box plots
AX_ALIGN    = fig.add_subplot(GS[1, 2])    # alignment heatmap
AX_HP_CR    = fig.add_subplot(GS[2, :2])   # HP vs CR scatter
AX_TOHIT    = fig.add_subplot(GS[2, 2])    # to_hit histogram
AX_IMM      = fig.add_subplot(GS[3, :])    # damage immunities + resistances combined

BG = "#1a1a2e"
PANEL = "#16213e"
TEXT = "#e0e0e0"
ACCENT = "#e94560"
GOLD = "#f5a623"

for ax in fig.axes:
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=TEXT)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
    ax.title.set_color(TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)

fig.suptitle("SRD 5.1 Monster Database — Distribution Analysis",
             fontsize=16, color=TEXT, fontweight="bold", y=0.97)

# ── 1. CR Distribution ────────────────────────────────────────────────────────
present_crs = list(cr_df["cr"])
colors_cr = [ACCENT if c in ("20","21","22","23","24","30") else GOLD
             if c in ("1/8","1/4","1/2") else PALETTE[0] for c in present_crs]
bars = AX_CR.bar(range(len(cr_df)), cr_df["n"], color=colors_cr, edgecolor="none", width=0.7)
AX_CR.set_xticks(range(len(cr_df)))
AX_CR.set_xticklabels(present_crs, rotation=45, ha="right")
AX_CR.set_xlabel("Challenge Rating")
AX_CR.set_ylabel("# Monsters")
AX_CR.set_title("Challenge Rating Distribution")
for bar, n in zip(bars, cr_df["n"]):
    if n >= 5:
        AX_CR.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                   str(n), ha="center", va="bottom", color=TEXT, fontsize=7)
legend_handles = [
    mpatches.Patch(color=PALETTE[0], label="Integer CR"),
    mpatches.Patch(color=GOLD,       label="Fractional CR"),
    mpatches.Patch(color=ACCENT,     label="CR 20+"),
]
AX_CR.legend(handles=legend_handles, framealpha=0.2, labelcolor=TEXT,
             facecolor=PANEL, edgecolor="#444")

# ── 2. Monster Types ──────────────────────────────────────────────────────────
type_colors = sns.color_palette("tab10", len(type_df))
hbars = AX_TYPE.barh(type_df["base_type"], type_df["n"],
                     color=type_colors, edgecolor="none")
AX_TYPE.set_xlabel("# Monsters")
AX_TYPE.set_title("Creature Type")
AX_TYPE.invert_yaxis()
for bar, n in zip(hbars, type_df["n"]):
    AX_TYPE.text(n + 0.5, bar.get_y() + bar.get_height()/2,
                 str(n), va="center", color=TEXT, fontsize=7)

# ── 3. Ability Score Box Plots ────────────────────────────────────────────────
ABILITY_COLORS = {"STR": "#e74c3c", "DEX": "#2ecc71", "CON": "#e67e22",
                  "INT": "#3498db", "WIS": "#9b59b6", "CHA": "#f39c12"}
order = ["STR","DEX","CON","INT","WIS","CHA"]
bp = AX_SCORES.boxplot(
    [scores_long[scores_long["ability"]==a]["score"].values for a in order],
    tick_labels=order,
    patch_artist=True,
    medianprops=dict(color="white", linewidth=2),
    whiskerprops=dict(color="#888"),
    capprops=dict(color="#888"),
    flierprops=dict(marker="o", markersize=2, alpha=0.4, color="#aaa"),
    boxprops=dict(linewidth=0),
)
for patch, ability in zip(bp["boxes"], order):
    patch.set_facecolor(ABILITY_COLORS[ability])
    patch.set_alpha(0.8)

# Overlay averages
avgs = scores_long.groupby("ability")["score"].mean()
for i, a in enumerate(order, 1):
    AX_SCORES.scatter(i, avgs[a], color="white", zorder=5, s=30, marker="D")

AX_SCORES.axhline(10, color="#555", linestyle="--", linewidth=0.8, label="Human baseline (10)")
AX_SCORES.set_ylabel("Score")
AX_SCORES.set_title("Ability Score Distributions (◆ = mean, line = human baseline)")
AX_SCORES.legend(framealpha=0.2, labelcolor=TEXT, facecolor=PANEL, edgecolor="#444")

# ── 4. Alignment Heatmap ─────────────────────────────────────────────────────
sns.heatmap(align_matrix, ax=AX_ALIGN, annot=True, fmt="d",
            cmap="YlOrRd", linewidths=0.5, linecolor="#333",
            cbar_kws={"shrink": 0.8},
            annot_kws={"size": 11, "color": "white", "weight": "bold"})
AX_ALIGN.set_title("Alignment Distribution\n(excludes Unaligned)")
AX_ALIGN.set_xlabel("Moral axis")
AX_ALIGN.set_ylabel("Ethical axis")
AX_ALIGN.tick_params(rotation=0)
cbar = AX_ALIGN.collections[0].colorbar
cbar.ax.tick_params(colors=TEXT, labelsize=7)

# ── 5. HP vs CR scatter ───────────────────────────────────────────────────────
AX_HP_CR.scatter(hp_cr_df["cr_num"], hp_cr_df["hp"],
                 alpha=0.55, s=28, color=PALETTE[0], edgecolors="none")

# Trend line (mean HP per CR)
mean_hp = hp_cr_df.groupby("cr_num")["hp"].mean().reset_index()
AX_HP_CR.plot(mean_hp["cr_num"], mean_hp["hp"],
              color=ACCENT, linewidth=2, label="Mean HP", zorder=5)

# Annotate a few notable monsters
for _, row in hp_cr_df[hp_cr_df["hp"] > 400].iterrows():
    AX_HP_CR.annotate(row["name"], (row["cr_num"], row["hp"]),
                      textcoords="offset points", xytext=(5, 0),
                      fontsize=6.5, color=GOLD)

AX_HP_CR.set_xlabel("Challenge Rating")
AX_HP_CR.set_ylabel("Hit Points")
AX_HP_CR.set_title("HP vs CR — each dot is one monster")
AX_HP_CR.legend(framealpha=0.2, labelcolor=TEXT, facecolor=PANEL, edgecolor="#444")

# ── 6. To-Hit Bonus Distribution ─────────────────────────────────────────────
AX_TOHIT.bar(tohit_df["to_hit"], tohit_df["n"],
             color=PALETTE[2], edgecolor="none", width=0.7)
AX_TOHIT.set_xlabel("Attack Bonus (+)")
AX_TOHIT.set_ylabel("# Attacks")
AX_TOHIT.set_title("Attack To-Hit Bonus\nDistribution")
mode_row = tohit_df.loc[tohit_df["n"].idxmax()]
AX_TOHIT.axvline(mode_row["to_hit"], color=ACCENT, linestyle="--", linewidth=1.5,
                 label=f"Mode: +{int(mode_row['to_hit'])}")
AX_TOHIT.legend(framealpha=0.2, labelcolor=TEXT, facecolor=PANEL, edgecolor="#444")

# ── 7. Damage Immunities + Resistances (grouped bar) ─────────────────────────
all_dtypes = sorted(set(imm_df["dtype"]) | set(res_df["dtype"]))
imm_map = dict(zip(imm_df["dtype"], imm_df["n"]))
res_map = dict(zip(res_df["dtype"], res_df["n"]))

imm_vals = [imm_map.get(d, 0) for d in all_dtypes]
res_vals = [res_map.get(d, 0) for d in all_dtypes]

x = np.arange(len(all_dtypes))
w = 0.38
b1 = AX_IMM.bar(x - w/2, imm_vals, w, color=ACCENT, edgecolor="none", label="Immune")
b2 = AX_IMM.bar(x + w/2, res_vals, w, color=PALETTE[0], edgecolor="none", label="Resistant")
AX_IMM.set_xticks(x)
AX_IMM.set_xticklabels(all_dtypes, rotation=35, ha="right")
AX_IMM.set_ylabel("# Monsters")
AX_IMM.set_title("Damage Immunities vs Resistances by Type")
AX_IMM.legend(framealpha=0.2, labelcolor=TEXT, facecolor=PANEL, edgecolor="#444")
for bar, v in zip(b1, imm_vals):
    if v: AX_IMM.text(bar.get_x()+bar.get_width()/2, v+0.3, str(v),
                      ha="center", va="bottom", color=TEXT, fontsize=7)
for bar, v in zip(b2, res_vals):
    if v: AX_IMM.text(bar.get_x()+bar.get_width()/2, v+0.3, str(v),
                      ha="center", va="bottom", color=TEXT, fontsize=7)

# ── save ─────────────────────────────────────────────────────────────────────
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Saved {OUT}")
con.close()

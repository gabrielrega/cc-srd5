#!/usr/bin/env python3
"""
Generate king_slime.png (monster illustration) and king_slime.pdf (stat block card).
"""

import os
import base64
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyArrowPatch, Polygon, Circle, Ellipse
from matplotlib.path import Path

# ── 1. ILLUSTRATION ───────────────────────────────────────────────────────────

def blob(cx, cy, rx, ry, seed, n=800):
    """Organic blob via Fourier-perturbed ellipse."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = np.ones(n)
    for k in range(2, 8):
        amp = rng.uniform(0.04, 0.18) / k
        phi = rng.uniform(0, 2 * np.pi)
        r += amp * np.sin(k * t + phi)
    return cx + rx * r * np.cos(t), cy + ry * r * np.sin(t)


def drip(cx, cy, w, h):
    """Teardrop drip shape."""
    t = np.linspace(0, 2 * np.pi, 200)
    x = cx + w / 2 * np.cos(t)
    y = cy + h / 2 * (np.sin(t) - 0.35 * np.sin(2 * t))
    return x, y


def splat(ax, cx, cy, r, color, alpha, seed):
    """Irregular acid splat on floor."""
    x, y = blob(cx, cy, r, r * 0.35, seed=seed, n=300)
    ax.fill(x, y, color=color, alpha=alpha, zorder=1)


def crown(ax, cx, top_y, width, color_main, color_shadow, color_gem):
    """5-point crown."""
    base_y = top_y - 0.55
    tips_x = [cx - width/2, cx - width/4, cx, cx + width/4, cx + width/2]
    tips_y = [top_y - 0.18, top_y - 0.04, top_y + 0.12, top_y - 0.04, top_y - 0.18]

    # Crown body polygon (base + 5 pointed tops)
    verts = [(cx - width/2, base_y)]
    for tx, ty in zip(tips_x, tips_y):
        verts.append((tx, ty))
    verts.append((cx + width/2, base_y))
    verts.append((cx - width/2, base_y))

    poly = Polygon(verts, closed=True, facecolor=color_main,
                   edgecolor=color_shadow, linewidth=1.5, zorder=18)
    ax.add_patch(poly)

    # Inner band highlight
    band_verts = [
        (cx - width/2, base_y + 0.10),
        (cx + width/2, base_y + 0.10),
        (cx + width/2, base_y + 0.20),
        (cx - width/2, base_y + 0.20),
    ]
    ax.add_patch(Polygon(band_verts, closed=True, facecolor="#ffe070",
                         alpha=0.6, zorder=19))

    # Gems (3 circles)
    gem_positions = [cx - width/4, cx, cx + width/4]
    gem_colors    = ["#cc2222", "#3388ff", "#cc2222"]
    for gx, gc in zip(gem_positions, gem_colors):
        ax.add_patch(Circle((gx, base_y + 0.15), 0.085,
                            facecolor=gc, edgecolor="#ffdd88", linewidth=1, zorder=20))
        # gem highlight
        ax.add_patch(Circle((gx - 0.025, base_y + 0.18), 0.025,
                            facecolor="white", alpha=0.6, zorder=21))


def eye(ax, cx, cy, sx, sy):
    """Glowing slit eye."""
    # Outer glow
    for r_mult, alpha in [(1.9, 0.08), (1.5, 0.14), (1.2, 0.20)]:
        ax.add_patch(Ellipse((cx, cy), sx * r_mult, sy * r_mult,
                             facecolor="#ccff44", alpha=alpha, zorder=13))
    # Sclera
    ax.add_patch(Ellipse((cx, cy), sx, sy,
                         facecolor="#e8f0a0", edgecolor="#aabb44",
                         linewidth=1, zorder=14))
    # Iris
    ax.add_patch(Ellipse((cx, cy), sx * 0.65, sy * 0.72,
                         facecolor="#c8aa00", zorder=15))
    # Vertical slit pupil
    ax.add_patch(Ellipse((cx, cy), sx * 0.14, sy * 0.64,
                         facecolor="#050a00", zorder=16))
    # Catchlight
    ax.add_patch(Ellipse((cx - sx*0.15, cy + sy*0.15), sx*0.14, sy*0.14,
                         facecolor="white", alpha=0.7, zorder=17))


def generate_art(out_path):
    fig, ax = plt.subplots(figsize=(6, 8))
    fig.patch.set_facecolor("#080c04")
    ax.set_facecolor("#080c04")
    ax.set_xlim(-3, 3)
    ax.set_ylim(-4.0, 4.2)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Background: stone cracks ──────────────────────────────────────────
    rng = np.random.default_rng(7)
    for _ in range(14):
        x0, y0 = rng.uniform(-3, 3), rng.uniform(-4, 4)
        angle = rng.uniform(0, np.pi)
        length = rng.uniform(0.3, 1.8)
        x1 = x0 + length * np.cos(angle)
        y1 = y0 + length * np.sin(angle)
        ax.plot([x0, x1], [y0, y1], color="#1a200f", lw=rng.uniform(0.4, 1.2),
                alpha=rng.uniform(0.3, 0.7), zorder=0)

    # ── Floor acid splats ─────────────────────────────────────────────────
    for params in [(-1.6, -2.8, 0.55, "#33cc22", 0.18, 10),
                   ( 1.8, -2.9, 0.40, "#55ee33", 0.14, 20),
                   ( 0.3, -3.1, 0.30, "#22aa11", 0.22, 30)]:
        splat(ax, *params)

    # ── Main acid puddle (under main body) ────────────────────────────────
    px, py = blob(0, -2.2, 2.5, 0.55, seed=99, n=500)
    ax.fill(px, py, color="#22aa11", alpha=0.30, zorder=2)
    ax.fill(px * 0.7, py * 0.7 + (-2.2 * 0.3), color="#44dd22", alpha=0.15, zorder=2)

    # ── Mini slimes ───────────────────────────────────────────────────────
    for cx, cy, rx, ry, seed, eye_x, eye_y in [
        (-2.15, -1.80, 0.52, 0.45, 55, -2.15, -1.72),
        ( 2.20, -1.90, 0.44, 0.38, 77,  2.20, -1.84),
    ]:
        mx, my = blob(cx, cy, rx, ry, seed=seed, n=400)
        ax.fill(mx, my, color="#2a9918", alpha=0.55, zorder=3)
        ax.fill(mx * 0.7 + cx*0.3, my * 0.7 + cy*0.3,
                color="#44cc22", alpha=0.35, zorder=4)
        # tiny eye
        ax.add_patch(Ellipse((eye_x, eye_y + 0.06), 0.14, 0.09,
                             facecolor="#d0e060", zorder=5))
        ax.add_patch(Ellipse((eye_x, eye_y + 0.06), 0.04, 0.07,
                             facecolor="#030600", zorder=6))

    # ── Acid drips from underside of main body ────────────────────────────
    drip_positions = [-0.9, -0.3, 0.2, 0.75]
    drip_lengths   = [ 0.55,  0.80, 0.65, 0.45]
    for dx, dl in zip(drip_positions, drip_lengths):
        drip_y_base = -1.85 - abs(dx) * 0.15
        dsx, dsy = drip(dx, drip_y_base - dl/2, 0.16, dl)
        ax.fill(dsx, dsy, color="#33dd22", alpha=0.55, zorder=7)
        # drip tip droplet
        ax.add_patch(Circle((dx, drip_y_base - dl + 0.05), 0.065,
                            facecolor="#44ff33", alpha=0.7, zorder=8))

    # ── Absorbed items visible through body ───────────────────────────────
    # Skull outline
    skull_x, skull_y = 0.75, -0.30
    ax.add_patch(Circle((skull_x, skull_y + 0.06), 0.16,
                        facecolor="none", edgecolor="#a8b880",
                        linewidth=1.0, alpha=0.35, zorder=9))
    ax.add_patch(Ellipse((skull_x, skull_y - 0.10), 0.18, 0.10,
                         facecolor="none", edgecolor="#a8b880",
                         linewidth=0.8, alpha=0.30, zorder=9))
    # Coin stack
    for i in range(3):
        ax.add_patch(Ellipse((-0.82, 0.18 + i*0.08), 0.22, 0.06,
                             facecolor="none", edgecolor="#c8a820",
                             linewidth=1.0, alpha=0.28, zorder=9))

    # ── Main slime body ───────────────────────────────────────────────────
    mx, my = blob(0, -0.10, 2.10, 1.85, seed=42, n=1000)

    # Outer glow layers
    for scale, alpha, color in [
        (1.12, 0.06, "#88ff44"),
        (1.07, 0.10, "#66ee33"),
        (1.03, 0.16, "#44dd22"),
    ]:
        ax.fill(mx * scale, my * scale - 0.10*(scale-1)*5,
                color=color, alpha=alpha, zorder=10)

    # Main fill — semi-transparent to show internals
    ax.fill(mx, my, color="#2ec412", alpha=0.78, zorder=11)

    # Inner highlight (upper-left sheen)
    t_h = np.linspace(np.pi * 0.55, np.pi * 1.45, 120)
    hx = -0.35 + 1.15 * np.cos(t_h)
    hy = 0.55 + 1.05 * np.sin(t_h)
    # clip highlight to rough body shape (approximate)
    mask = (hx**2/2.1**2 + (hy+0.1)**2/1.85**2) < 0.92
    if mask.sum() > 3:
        ax.fill(np.append(hx[mask], hx[mask][0]),
                np.append(hy[mask], hy[mask][0]),
                color="white", alpha=0.09, zorder=12)

    # Outline
    ax.plot(mx, my, color="#22aa10", lw=1.2, alpha=0.7, zorder=12)

    # ── Eyes ──────────────────────────────────────────────────────────────
    eye(ax, -0.52, 0.42, 0.46, 0.30)
    eye(ax,  0.52, 0.42, 0.46, 0.30)

    # ── Crown ─────────────────────────────────────────────────────────────
    # Find rough top of blob near center
    center_top = my[np.abs(mx) < 0.5].max()
    crown(ax, cx=0, top_y=center_top + 0.18,
          width=1.55,
          color_main="#d4a017",
          color_shadow="#8b6800",
          color_gem="#cc2222")

    # ── Nameplate ─────────────────────────────────────────────────────────
    ax.text(0, -3.55, "KING SLIME", ha="center", va="center",
            fontsize=19, fontweight="bold", color="#c8a820",
            fontfamily="DejaVu Serif",
            path_effects=[pe.withStroke(linewidth=3, foreground="#0a0e04")])
    ax.text(0, -3.85, "Huge Ooze  ·  CR 10  ·  Unaligned", ha="center", va="center",
            fontsize=9, color="#88aa66", fontstyle="italic")

    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor="#080c04", pad_inches=0.05)
    plt.close(fig)
    print(f"  Art saved → {out_path}")


# ── 2. PDF ────────────────────────────────────────────────────────────────────

STAT_BLOCK_HTML = """
<div class="stat-block">

  <div class="creature-heading">
    <h1>King Slime</h1>
    <h2>Huge ooze, unaligned</h2>
  </div>

  <svg class="rule" viewBox="0 0 400 8" preserveAspectRatio="none">
    <polygon points="0,0 400,3 0,6" fill="#7a200d"/>
  </svg>

  <div class="property-block">
    <p><b>Armor Class</b> 8</p>
    <p><b>Hit Points</b> 168 (16d12 + 64)</p>
    <p><b>Speed</b> 30 ft., climb 30 ft., swim 30 ft.</p>
  </div>

  <svg class="rule" viewBox="0 0 400 8" preserveAspectRatio="none">
    <polygon points="0,0 400,3 0,6" fill="#7a200d"/>
  </svg>

  <div class="abilities">
    <div class="ability"><span class="label">STR</span><span class="score">22 (+6)</span></div>
    <div class="ability"><span class="label">DEX</span><span class="score">6 (&#x2212;2)</span></div>
    <div class="ability"><span class="label">CON</span><span class="score">18 (+4)</span></div>
    <div class="ability"><span class="label">INT</span><span class="score">3 (&#x2212;4)</span></div>
    <div class="ability"><span class="label">WIS</span><span class="score">8 (&#x2212;1)</span></div>
    <div class="ability"><span class="label">CHA</span><span class="score">3 (&#x2212;4)</span></div>
  </div>

  <svg class="rule" viewBox="0 0 400 8" preserveAspectRatio="none">
    <polygon points="0,0 400,3 0,6" fill="#7a200d"/>
  </svg>

  <div class="property-block">
    <p><b>Saving Throws</b> Con +8</p>
    <p><b>Damage Immunities</b> acid</p>
    <p><b>Damage Resistances</b> bludgeoning, piercing, and slashing from nonmagical attacks</p>
    <p><b>Condition Immunities</b> blinded, charmed, deafened, exhaustion, frightened, prone</p>
    <p><b>Senses</b> blindsight 60 ft. (blind beyond this radius), passive Perception 9</p>
    <p><b>Languages</b> &#x2014;</p>
    <p><b>Challenge</b> 10 (5,900 XP)</p>
  </div>

  <svg class="rule thin" viewBox="0 0 400 5" preserveAspectRatio="none">
    <line x1="0" y1="2" x2="400" y2="2" stroke="#7a200d" stroke-width="2"/>
  </svg>

  <div class="property-block traits">
    <p><b><i>Amorphous.</i></b> The king slime can move through a space as narrow as 1 foot wide without squeezing.</p>
    <p><b><i>Corrosive Body.</i></b> A creature that touches the king slime or hits it with a melee attack while within 5 feet of it takes 9 (2d8) acid damage.</p>
    <p><b><i>False Appearance.</i></b> While the king slime remains motionless, it is indistinguishable from a large viscous pool of liquid.</p>
    <p><b><i>Legendary Resistance (3/Day).</i></b> If the king slime fails a saving throw, it can choose to succeed instead.</p>
    <p><b><i>Slime Spawn (1/Day).</i></b> When the king slime is reduced to 84 or fewer hit points for the first time, it immediately spawns two <b>slime princes</b> (use the stat block of an ochre jelly) in unoccupied spaces within 10 feet of it. The slime princes act on the king slime&#x2019;s initiative count.</p>
    <p><b><i>Spider Climb.</i></b> The king slime can climb difficult surfaces, including upside down on ceilings, without needing to make an ability check.</p>
  </div>

  <h3 class="section-header">Actions</h3>

  <div class="property-block">
    <p><b><i>Multiattack.</i></b> The king slime makes two pseudopod attacks. It can replace one of those attacks with Engulf.</p>
    <p><b><i>Pseudopod.</i></b> <i>Melee Weapon Attack:</i> +10 to hit, reach 10 ft., one target. <i>Hit:</i> 15 (2d8 + 6) bludgeoning damage plus 9 (2d8) acid damage.</p>
    <p><b><i>Engulf.</i></b> The king slime moves up to its speed. While doing so, it can enter Large or smaller creatures&#x2019; spaces. Whenever the king slime enters a creature&#x2019;s space, the creature must make a DC 16 Dexterity saving throw. On a failed save, the creature is engulfed. The engulfed creature can&#x2019;t breathe, is restrained, and takes 21 (6d6) acid damage at the start of each of the king slime&#x2019;s turns. When the king slime moves, the engulfed creature moves with it. An engulfed creature can try to escape by taking an action to make a DC 18 Strength check. On a success, the creature escapes and enters a space of its choice within 5 feet of the king slime.</p>
    <p><b><i>Acidic Eruption (Recharge 5&#x2013;6).</i></b> The king slime violently expels caustic fluid in all directions. Each creature within 15 feet of the king slime must make a DC 16 Constitution saving throw, taking 35 (10d6) acid damage on a failed save, or half as much damage on a successful one. The ground in that area becomes difficult terrain until the end of the king slime&#x2019;s next turn as the acid pools and smolders.</p>
  </div>

  <h3 class="section-header">Legendary Actions</h3>

  <div class="property-block">
    <p>The king slime can take 3 legendary actions, choosing from the options below. Only one legendary action option can be used at a time and only at the end of another creature&#x2019;s turn. The king slime regains spent legendary actions at the start of its turn.</p>
    <p><b><i>Creep.</i></b> The king slime moves up to half its speed without provoking opportunity attacks.</p>
    <p><b><i>Pseudopod Strike (Costs 2 Actions).</i></b> The king slime makes one pseudopod attack.</p>
    <p><b><i>Corrosive Surge (Costs 3 Actions).</i></b> The king slime releases a pulse of concentrated acid from its core. Each creature engulfed by the king slime automatically takes 28 (8d6) acid damage. Each creature within 5 feet of the king slime that is not engulfed must succeed on a DC 16 Constitution saving throw or take 14 (4d6) acid damage.</p>
  </div>

</div>
"""

CSS = """
@page {
  size: A4;
  margin: 18mm 16mm;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Liberation Serif', 'DejaVu Serif', serif;
  font-size: 9.5pt;
  background: #e8d9b0;
  color: #1a0a00;
}
.page-wrap {
  max-width: 168mm;
  margin: 0 auto;
}
.monster-image {
  display: block;
  width: 100%;
  max-height: 230px;
  object-fit: cover;
  object-position: center top;
  border: 3px solid #7a200d;
  margin-bottom: 0;
}
.stat-block {
  background: #fdf1dc;
  border: 2px solid #7a200d;
  padding: 10px 14px 14px;
}
.creature-heading h1 {
  font-size: 20pt;
  font-variant: small-caps;
  color: #7a200d;
  line-height: 1.1;
  margin-bottom: 1px;
}
.creature-heading h2 {
  font-size: 10pt;
  font-weight: normal;
  font-style: italic;
  color: #1a0a00;
  margin-bottom: 5px;
}
svg.rule {
  display: block;
  width: 100%;
  height: 8px;
  margin: 5px 0;
}
svg.rule.thin {
  height: 5px;
  margin: 3px 0;
}
.property-block p {
  margin: 2.5px 0;
  line-height: 1.4;
}
.property-block b {
  color: #7a200d;
}
.abilities {
  display: flex;
  justify-content: space-around;
  text-align: center;
  padding: 4px 0;
}
.ability {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}
.ability .label {
  font-size: 8pt;
  font-weight: bold;
  color: #7a200d;
  display: block;
}
.ability .score {
  font-size: 9pt;
  display: block;
}
.section-header {
  font-size: 13pt;
  font-variant: small-caps;
  color: #7a200d;
  border-bottom: 1px solid #9a4010;
  margin: 7px 0 3px;
  padding-bottom: 1px;
}
.traits p {
  margin: 3.5px 0;
}
"""

def generate_pdf(art_path, out_path):
    from weasyprint import HTML, CSS as WCS

    # Embed image as base64 so the PDF is self-contained
    with open(art_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    img_src = f"data:image/png;base64,{img_b64}"

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{CSS}</style>
</head><body>
<div class="page-wrap">
  <img class="monster-image" src="{img_src}">
  {STAT_BLOCK_HTML}
</div>
</body></html>"""

    HTML(string=html_doc).write_pdf(out_path, stylesheets=[WCS(string="")])
    print(f"  PDF saved  → {out_path}")


# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating King Slime art...")
    generate_art("king_slime.png")
    print("Generating King Slime PDF...")
    generate_pdf("king_slime.png", "king_slime.pdf")
    print("Done.")

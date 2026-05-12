#!/usr/bin/env python3
"""
chatblock.py — Chat-friendly stat block for any SRD or homebrew monster.

Usage:
  python3 chatblock.py "Aboleth"
  python3 chatblock.py "Tarrasque"
  python3 chatblock.py "King Slime" --file king_slime.md
  python3 chatblock.py "Aboleth" --output aboleth_chat.txt
"""

import re
import sys
import argparse
import textwrap
from pathlib import Path

# ── width constants ────────────────────────────────────────────────────────
W       = 62          # total line width (including 2-space left pad)
INDENT  = "    "      # continuation indent for wrapped lines
THICK   = "━" * W
THIN    = "─" * W


# ── modifiers & helpers ───────────────────────────────────────────────────

def mod(score):
    """Return signed modifier string, e.g. +6 or −2 (unicode minus)."""
    m = (score - 10) // 2
    return f"+{m}" if m >= 0 else f"−{abs(m)}"


def wrap(text, indent=INDENT, width=W - 2):
    """Word-wrap text with hanging indent for continuation lines."""
    return textwrap.fill(text, width=width,
                         initial_indent="  ",
                         subsequent_indent="  " + indent)


def section(title):
    return f"{THICK}\n  {title}"


def _fmt_speed(speeds):
    parts = []
    for s in (speeds or []):
        mode = s.get("mode", "walk")
        ft   = s.get("ft", 0)
        if mode == "walk":
            parts.insert(0, f"{ft} ft.")
        else:
            parts.append(f"{mode} {ft} ft.")
    return " · ".join(parts) if parts else "—"


def _fmt_list(items):
    return ", ".join(items) if items else "—"


def _fmt_save(ability, bonus):
    sign = "+" if bonus >= 0 else "−"
    return f"{ability} {sign}{abs(bonus)}"


# ── action formatter ──────────────────────────────────────────────────────

def fmt_action(a, bullet="◈"):
    """Format a single action/trait/legendary action for chat output."""
    name = a["name"]
    cost = a.get("cost")
    desc = a.get("description", "")

    # Cost badge for legendary actions
    cost_badge = f" [{cost}]" if cost is not None else ""

    # For attacks, build a compact stat line then wrap the rest
    if a.get("is_attack") and a.get("to_hit") is not None:
        to_hit    = a["to_hit"]
        reach     = a.get("reach_or_range") or ""
        dmg_dice  = a.get("damage_dice") or ""
        dmg_type  = a.get("damage_type") or ""

        hit_line = f"+{to_hit} to hit"
        if reach:
            hit_line += f" · {reach}"

        # extract any additional hit effects from the description after "Hit:"
        extra = ""
        hit_match = re.search(r"Hit:\s+(.+)", desc, re.IGNORECASE)
        if hit_match:
            hit_text = hit_match.group(1).strip()
            # show full hit text (includes bonus conditions)
            extra_wrapped = textwrap.fill(
                "Hit: " + hit_text, width=W - 4,
                initial_indent="  " + INDENT,
                subsequent_indent="  " + INDENT + "  ")
        else:
            extra_wrapped = f"  {INDENT}Hit: {dmg_dice} {dmg_type}".rstrip()

        header = f"  {bullet} {name}{cost_badge} — {hit_line}"
        return header + "\n" + extra_wrapped

    # For saves without attacks — show DC prominently if present
    save_note = ""
    if a.get("save_dc") and not a.get("is_attack"):
        save_note = f" [DC {a['save_dc']} {a['save_ability']}]"

    header = f"  {bullet} {name}{cost_badge}{save_note}"

    # Wrap the description, stripping the repeated name prefix if present
    clean_desc = re.sub(rf"^{re.escape(name)}\.?\s*", "", desc).strip()
    if not clean_desc:
        return header
    wrapped = textwrap.fill(
        clean_desc, width=W - 4,
        initial_indent="  " + INDENT,
        subsequent_indent="  " + INDENT + "  ")
    return header + "\n" + wrapped


# ── main formatter ────────────────────────────────────────────────────────

def format_chatblock(m):
    """
    Format a monster dict into a chat-friendly stat block string.
    m must contain all fields from the monsters table plus
    m['actions'] = list of action dicts from monster_actions.
    """
    lines = []

    # ── Header ──────────────────────────────────────────────────────────
    size      = m.get("size") or ""
    mtype     = m.get("type") or ""
    # strip parenthetical subtype from type for display
    base_type = re.sub(r"\s*\(.*", "", mtype).strip()
    alignment = m.get("alignment") or ""
    cr        = m.get("cr") or "?"
    xp        = m.get("xp")
    xp_str    = f"{xp:,}" if xp else "?"

    lines.append(THICK)
    lines.append(f"  {m['name'].upper()}")
    lines.append(f"  {size} {base_type} · {alignment} · CR {cr} ({xp_str} XP)")

    # ── AC / HP / Speed ──────────────────────────────────────────────────
    lines.append(THICK)
    ac = m.get("ac") or "?"
    ac_notes = m.get("ac_notes") or ""
    ac_str = f"{ac} ({ac_notes})" if ac_notes else str(ac)
    hp = m.get("hp") or "?"
    hp_dice = m.get("hp_dice") or ""
    hp_str = f"{hp} ({hp_dice})" if hp_dice else str(hp)
    lines.append(f"  AC {ac_str}   HP {hp_str}")
    lines.append(f"  Speed  {_fmt_speed(m.get('speeds'))}")

    # ── Ability scores ───────────────────────────────────────────────────
    lines.append(THIN)
    stats  = ["str", "dex", "con", "int", "wis", "cha"]
    labels = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    scores = [m.get(s) for s in stats]
    # 7-char columns × 6 = 42, plus 2 leading spaces → 44, fits in W=62
    col = 7
    lines.append("  " + "".join(f"{l:^{col}}" for l in labels))
    lines.append("  " + "".join(
        f"{s if s is not None else '?':^{col}}" for s in scores))
    lines.append("  " + "".join(
        f"{mod(s) if s is not None else '?':^{col}}" for s in scores))

    # ── Secondary stats ───────────────────────────────────────────────────
    lines.append(THIN)

    def prop(label, value, width=16):
        label_col = f"{label:<{width}}"
        wrapped = textwrap.fill(
            value, width=W - 2 - width,
            subsequent_indent="  " + " " * width)
        return "  " + label_col + wrapped

    saves = m.get("saving_throws") or []
    if saves:
        save_str = ", ".join(_fmt_save(s["ability"], s["bonus"]) for s in saves)
        lines.append(prop("Saving Throws", save_str))

    skills = m.get("skills") or []
    if skills:
        skill_str = ", ".join(f"{s['name']} {_fmt_save('', s['bonus'])[1:].strip()}"
                              for s in skills)
        lines.append(prop("Skills", skill_str))

    dmg_vuln = m.get("damage_vulnerabilities") or []
    dmg_imm  = m.get("damage_immunities") or []
    dmg_res  = m.get("damage_resistances") or []
    cond_imm = m.get("condition_immunities") or []

    if dmg_vuln:  lines.append(prop("Dmg Vulnerable", _fmt_list(dmg_vuln)))
    if dmg_imm:   lines.append(prop("Dmg Immune",     _fmt_list(dmg_imm)))
    if dmg_res:   lines.append(prop("Dmg Resistant",  _fmt_list(dmg_res)))
    if cond_imm:  lines.append(prop("Cond. Immune",   _fmt_list(cond_imm)))

    senses = m.get("senses") or []
    pp     = m.get("passive_perception")
    sense_parts = [f"{s['name']} {s['range_ft']} ft." for s in senses]
    if pp is not None:
        sense_parts.append(f"passive Perception {pp}")
    if sense_parts:
        lines.append(prop("Senses", ", ".join(sense_parts)))

    langs = m.get("languages") or []
    if langs:
        lines.append(prop("Languages", _fmt_list(langs)))

    # ── Actions by category ───────────────────────────────────────────────
    actions = m.get("actions") or []
    by_cat = {}
    for a in actions:
        by_cat.setdefault(a["category"], []).append(a)

    CAT_ORDER = [
        ("trait",            "TRAITS",             "◆"),
        ("action",           "ACTIONS",            "◈"),
        ("reaction",         "REACTIONS",          "↩"),
        ("legendary_action", "LEGENDARY ACTIONS",  "⚡"),
        ("lair_action",      "LAIR ACTIONS",       "✦"),
    ]

    legendary = m.get("legendary", False)

    for cat_key, cat_label, bullet in CAT_ORDER:
        entries = by_cat.get(cat_key, [])
        if not entries:
            continue
        lines.append(section(cat_label))
        if cat_key == "legendary_action":
            lines.append(f"  (3 per turn, at end of another creature's turn)")
        for a in entries:
            lines.append(fmt_action(a, bullet=bullet))

    lines.append(THICK)
    return "\n".join(lines)


# ── loaders ───────────────────────────────────────────────────────────────

def load_from_db(name, db_path="monsters.duckdb"):
    """Load a monster from DuckDB by name (case-insensitive)."""
    import duckdb
    con = duckdb.connect(db_path, read_only=True)

    row = con.execute("""
        SELECT * FROM monsters
        WHERE LOWER(name) = LOWER(?)
    """, [name]).fetchone()

    if row is None:
        return None

    cols = [d[0] for d in con.description]
    m = dict(zip(cols, row))

    # Convert numpy arrays / structs to plain Python
    for key in ("speeds", "senses", "saving_throws", "skills",
                "damage_immunities", "damage_resistances",
                "damage_vulnerabilities", "condition_immunities", "languages"):
        val = m.get(key)
        if val is not None:
            try:
                m[key] = [dict(v) if hasattr(v, 'items') else v for v in val]
            except TypeError:
                m[key] = list(val)

    actions = con.execute("""
        SELECT category, name, cost, "description", is_attack,
               attack_type, to_hit, reach_or_range, damage_dice,
               damage_type, save_dc, save_ability
        FROM monster_actions
        WHERE monster_id = ?
        ORDER BY id
    """, [m["id"]]).fetchall()

    action_cols = [d[0] for d in con.description]
    m["actions"] = [dict(zip(action_cols, a)) for a in actions]
    con.close()
    return m


def load_from_md(filepath):
    """
    Parse a standalone monster .md file (## or #### heading style).
    Reuses parse_block() from parse_monsters.py.
    """
    # Ensure parse_monsters is importable from the same directory
    sys.path.insert(0, str(Path(__file__).parent))
    from parse_monsters import parse_block

    text = Path(filepath).read_text(encoding="utf-8")
    raw_lines = text.splitlines()

    # Find the first heading that looks like a monster name
    name = None
    start = 0
    for i, line in enumerate(raw_lines):
        hm = re.match(r"^#{1,4}\s+(.+?)(?:\s*\{[^}]+\})?\s*$", line)
        if hm:
            candidate = hm.group(1).strip()
            if candidate.lower() not in ("new monsters",):
                name = candidate
                start = i + 1
                break

    if name is None:
        raise ValueError(f"No monster heading found in {filepath}")

    # Normalize heading levels: ## → #### and ### → #####
    content = []
    for line in raw_lines[start:]:
        if line.startswith("### "):
            line = "##### " + line[4:]
        elif line.startswith("## ") and not line.startswith("#### "):
            line = "#### " + line[3:]
        content.append(line)

    monster, actions = parse_block(name, start + 1, content)
    monster["actions"] = actions
    return monster


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a chat-friendly stat block for any monster.")
    parser.add_argument("name",
        help='Monster name, e.g. "Aboleth" or "King Slime"')
    parser.add_argument("--file", metavar="PATH",
        help="Parse from a .md file instead of the database")
    parser.add_argument("--db", metavar="PATH", default="monsters.duckdb",
        help="Path to DuckDB database (default: monsters.duckdb)")
    parser.add_argument("--output", metavar="PATH",
        help="Write output to file instead of stdout")
    args = parser.parse_args()

    if args.file:
        monster = load_from_md(args.file)
    else:
        monster = load_from_db(args.name, db_path=args.db)
        if monster is None:
            # Try to find a matching .md file automatically
            slug = re.sub(r"[^a-z0-9]+", "_", args.name.lower()).strip("_")
            candidates = [Path(f"{slug}.md"), Path(f"{args.name.lower()}.md")]
            for c in candidates:
                if c.exists():
                    print(f"[not in DB — loading from {c}]", file=sys.stderr)
                    monster = load_from_md(str(c))
                    break
        if monster is None:
            print(f"Monster '{args.name}' not found in DB or as a .md file.",
                  file=sys.stderr)
            sys.exit(1)

    output = format_chatblock(monster)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()

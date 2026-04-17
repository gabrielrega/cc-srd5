#!/usr/bin/env python3
"""
Parse monster stat blocks from cc-srd5.md and load them into DuckDB.

Stat block structure (all fields bold-prefixed except the type line):
  #### Monster Name
  *Size type[, subtype], alignment*
  **Armor Class** N (notes)
  **Hit Points** N (Xd10 + Y)
  **Speed** N ft.[, mode N ft.]...
  <HTML table with STR/DEX/CON/INT/WIS/CHA>
  **Saving Throws** Abl +N, ...          (optional)
  **Skills** Name +N, ...                (optional)
  **Damage Vulnerabilities** ...         (optional)
  **Damage Resistances** ...             (optional)
  **Damage Immunities** ...              (optional)
  **Condition Immunities** ...           (optional)
  **Senses** ..., passive Perception N
  **Languages** ...
  **Challenge** N (N,NNN XP)
  ***Trait Name.*** description...
  ##### Actions
  ***Action Name.*** description...
  ##### Legendary Actions
  ***Name (Costs N Actions).*** description...
  ##### Reactions
  ***Name.*** description...
"""

import re
import sys
import duckdb

SOURCE = "cc-srd5.md"
DB_FILE = "monsters.duckdb"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_bonus(text: str) -> int | None:
    """Parse '+5' or '−3' or '-3' into int."""
    text = text.strip().replace("−", "-")
    try:
        return int(text)
    except ValueError:
        return None


def parse_ability_score(cell: str) -> int | None:
    """Parse '21 (+5)' -> 21."""
    m = re.match(r"\s*(\d+)", cell)
    return int(m.group(1)) if m else None


def parse_xp(text: str) -> int | None:
    """Parse '5,900 XP' -> 5900."""
    m = re.search(r"([\d,]+)\s*XP", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


SPEED_MODE_RE = re.compile(
    r"(?:^|,\s*)"
    r"(?:(burrow|climb|fly|swim|hover)\s+)?"
    r"(\d+)\s*ft\.?"
    r"(?:\s*\(hover\))?",
    re.IGNORECASE,
)

def parse_speeds(text: str) -> list[dict]:
    """Return list of {mode, ft} dicts from a Speed line value."""
    speeds = []
    for m in SPEED_MODE_RE.finditer(text):
        mode = (m.group(1) or "walk").lower()
        ft = int(m.group(2))
        speeds.append({"mode": mode, "ft": ft})
    return speeds


SENSE_RE = re.compile(
    r"(blindsight|darkvision|tremorsense|truesight)\s+(\d+)\s*ft",
    re.IGNORECASE,
)

def parse_senses(text: str) -> tuple[list[dict], int | None]:
    """Return (senses list, passive_perception)."""
    senses = []
    for m in SENSE_RE.finditer(text):
        senses.append({"name": m.group(1).lower(), "range_ft": int(m.group(2))})
    pp = None
    pm = re.search(r"passive Perception\s+(\d+)", text, re.IGNORECASE)
    if pm:
        pp = int(pm.group(1))
    return senses, pp


def parse_saving_throws(text: str) -> list[dict]:
    """Parse 'Con +6, Int +8, Wis +6' -> list of {ability, bonus}."""
    result = []
    for m in re.finditer(r"(\w+)\s*([+\-−]\d+)", text):
        bonus = parse_bonus(m.group(2))
        if bonus is not None:
            result.append({"ability": m.group(1), "bonus": bonus})
    return result


def parse_skills(text: str) -> list[dict]:
    """Parse 'History +12, Perception +10' -> list of {name, bonus}."""
    result = []
    for m in re.finditer(r"([A-Za-z ()']+?)\s*([+\-−]\d+)", text):
        name = m.group(1).strip()
        bonus = parse_bonus(m.group(2))
        if name and bonus is not None:
            result.append({"name": name, "bonus": bonus})
    return result


def parse_damage_list(text: str) -> list[str]:
    """Split a damage type list by commas and semicolons, strip markdown."""
    text = re.sub(r"\[.*?\]\(.*?\)", lambda m: m.group(0).split("]")[0][1:], text)
    parts = re.split(r"[;,]", text)
    return [p.strip() for p in parts if p.strip()]


def strip_inline_md(text: str) -> str:
    """Remove bold/italic markers and inline links from action descriptions."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    return text.strip()


# Matches ***Name.*** or ***Name (Costs N Actions).***
ACTION_NAME_RE = re.compile(r"^\*{3}([^*]+?)\.*\*{3}\s*(.*)", re.DOTALL)
COST_RE = re.compile(r"\(Costs?\s+(\d+)\s+Actions?\)", re.IGNORECASE)

# Separate regexes to avoid alternation-scoping bugs
ATTACK_TYPE_RE = re.compile(
    r"\*((?:Melee(?:\s+or\s+Ranged)?|Ranged))\s+(Weapon|Spell)\s+Attack\*",
    re.IGNORECASE,
)
TO_HIT_RE  = re.compile(r"\+(\d+)\s+to\s+hit", re.IGNORECASE)
REACH_RE   = re.compile(r"reach\s+([\d/]+\s*ft\.?)", re.IGNORECASE)
RANGE_RE   = re.compile(r"range\s+([\d/]+\s*ft\.?)", re.IGNORECASE)
DAMAGE_RE  = re.compile(r"Hit:\*\s+\d+\s+\(([^)]+)\)\s+(\w+)\s+damage", re.IGNORECASE)
SAVE_RE    = re.compile(r"DC\s+(\d+)\s+(\w+)\s+saving", re.IGNORECASE)


def parse_action(raw_name: str, raw_desc: str, category: str) -> dict:
    """Extract structured fields from a single action block."""
    cost = None
    cm = COST_RE.search(raw_name)
    if cm:
        cost = int(cm.group(1))
        raw_name = COST_RE.sub("", raw_name).strip(" .()")

    desc = strip_inline_md(raw_name + ". " + raw_desc)

    is_attack = bool(re.search(r"Weapon Attack|Spell Attack", raw_desc, re.IGNORECASE))
    attack_type = to_hit = reach_range = dmg_dice = dmg_type = save_dc = save_ability = None

    if is_attack:
        atm = ATTACK_TYPE_RE.search(raw_desc)
        if atm:
            attack_type = f"{atm.group(1)} {atm.group(2)}"
        thm = TO_HIT_RE.search(raw_desc)
        if thm:
            to_hit = int(thm.group(1))
        rm = REACH_RE.search(raw_desc) or RANGE_RE.search(raw_desc)
        if rm:
            reach_range = rm.group(1).strip()
        dm = DAMAGE_RE.search(raw_desc)
        if dm:
            dmg_dice = dm.group(1).strip()
            dmg_type = dm.group(2).strip()

    sm = SAVE_RE.search(raw_desc)
    if sm:
        save_dc = int(sm.group(1))
        save_ability = sm.group(2)

    return {
        "category": category,
        "name": raw_name.strip(" ."),
        "cost": cost,
        "description": desc,
        "is_attack": is_attack,
        "attack_type": attack_type,
        "to_hit": to_hit,
        "reach_or_range": reach_range,
        "damage_dice": dmg_dice,
        "damage_type": dmg_type,
        "save_dc": save_dc,
        "save_ability": save_ability,
    }


# ---------------------------------------------------------------------------
# Stat block splitter
# ---------------------------------------------------------------------------

# Lines between two #### headings (or end of relevant chapters) form one block.
CHAPTER_START = 25169   # 1-indexed line numbers from grep earlier
CHAPTER_END_MISC = None  # we'll read to EOF of the creature sections

def extract_stat_blocks(path: str) -> list[tuple[int, str, list[str]]]:
    """
    Return list of (start_line, name, lines) for every #### monster entry
    in the Monsters and Miscellaneous Creatures chapters.
    """
    with open(path, encoding="utf-8") as f:
        all_lines = f.readlines()

    in_monster_chapter = False
    blocks: list[tuple[int, str, list[str]]] = []
    current_name = None
    current_start = 0
    current_lines: list[str] = []

    for i, line in enumerate(all_lines, start=1):
        stripped = line.rstrip("\n")

        # Detect chapter boundaries
        if stripped.startswith("# Monsters") or stripped.startswith("# Miscellaneous Creatures"):
            in_monster_chapter = True
            continue
        # Stop at any other top-level chapter after we've been in monster chapters
        if in_monster_chapter and re.match(r"^# [^#]", stripped):
            # Save last block
            if current_name and current_lines:
                blocks.append((current_start, current_name, current_lines))
                current_name = None
                current_lines = []
            in_monster_chapter = False
            continue

        if not in_monster_chapter:
            continue

        # New monster entry
        if stripped.startswith("#### "):
            if current_name and current_lines:
                blocks.append((current_start, current_name, current_lines))
            current_name = stripped[5:].strip()
            current_start = i
            current_lines = []
            continue

        if current_name is not None:
            current_lines.append(stripped)

    # Flush last
    if current_name and current_lines:
        blocks.append((current_start, current_name, current_lines))

    return blocks


# ---------------------------------------------------------------------------
# Single block parser
# ---------------------------------------------------------------------------

def parse_block(name: str, start_line: int, lines: list[str]) -> tuple[dict, list[dict]]:
    """
    Parse a monster stat block into (monster_row, [action_rows]).
    """
    monster: dict = {
        "id": slugify(name),
        "name": name,
        "size": None,
        "type": None,
        "subtype": None,
        "alignment": None,
        "ac": None,
        "ac_notes": None,
        "hp": None,
        "hp_dice": None,
        "str": None, "dex": None, "con": None,
        "int": None, "wis": None, "cha": None,
        "cr": None,
        "xp": None,
        "languages": [],
        "passive_perception": None,
        "senses": [],
        "speeds": [],
        "saving_throws": [],
        "skills": [],
        "damage_immunities": [],
        "damage_resistances": [],
        "damage_vulnerabilities": [],
        "condition_immunities": [],
        "legendary": False,
        "has_lair": False,
        "source_line": start_line,
    }
    actions: list[dict] = []

    # Join lines for HTML table scanning
    full_text = "\n".join(lines)

    # --- Type line: *Large aberration, lawful evil* ---
    for line in lines[:5]:
        m = re.match(r"^\*([A-Za-z]+)\s+([^,*]+?)(?:,\s*([^,*]+?))?(?:,\s*(.+?))?\*\s*$", line)
        if m:
            monster["size"] = m.group(1).strip()
            monster["type"] = m.group(2).strip()
            # alignment is last group; subtype might appear in parens or as 3rd token
            g3 = m.group(3)
            g4 = m.group(4)
            if g4:
                monster["subtype"] = g3.strip() if g3 else None
                monster["alignment"] = g4.strip()
            elif g3:
                monster["alignment"] = g3.strip()
            break

    # --- Ability scores from HTML table ---
    scores_m = re.search(
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*\([^)]+\)\s*</td>",
        full_text,
    )
    if scores_m:
        for key, val in zip(["str","dex","con","int","wis","cha"], scores_m.groups()):
            monster[key] = int(val)

    # --- Bold-prefixed fields ---
    i = 0
    current_category = "trait"
    action_buffer: list[str] = []  # accumulates lines for current action

    def flush_action(buf: list[str], cat: str):
        if not buf:
            return
        combined = " ".join(buf)
        am = ACTION_NAME_RE.match(combined)
        if am:
            actions.append(parse_action(am.group(1), am.group(2), cat))

    while i < len(lines):
        line = lines[i]

        # Section headers (H5)
        if line.startswith("##### "):
            flush_action(action_buffer, current_category)
            action_buffer = []
            section = line[6:].strip().lower()
            if "legendary action" in section:
                current_category = "legendary_action"
                monster["legendary"] = True
            elif "lair action" in section:
                current_category = "lair_action"
                monster["has_lair"] = True
            elif "reaction" in section:
                current_category = "reaction"
            elif "action" in section:
                current_category = "action"
            i += 1
            continue

        # Bold stat fields
        bm = re.match(r"^\*\*([^*]+)\*\*\s*(.*)", line)
        if bm:
            field = bm.group(1).strip()
            value = bm.group(2).strip()

            if field == "Armor Class":
                am2 = re.match(r"(\d+)(.*)", value)
                if am2:
                    monster["ac"] = int(am2.group(1))
                    notes = am2.group(2).strip(" ()")
                    monster["ac_notes"] = notes if notes else None

            elif field == "Hit Points":
                hm = re.match(r"(\d+)\s*(?:\(([^)]+)\))?", value)
                if hm:
                    monster["hp"] = int(hm.group(1))
                    monster["hp_dice"] = hm.group(2)

            elif field == "Speed":
                monster["speeds"] = parse_speeds(value)

            elif field == "Saving Throws":
                monster["saving_throws"] = parse_saving_throws(value)

            elif field == "Skills":
                monster["skills"] = parse_skills(value)

            elif field == "Damage Immunities":
                monster["damage_immunities"] = parse_damage_list(value)

            elif field == "Damage Resistances":
                monster["damage_resistances"] = parse_damage_list(value)

            elif field == "Damage Vulnerabilities":
                monster["damage_vulnerabilities"] = parse_damage_list(value)

            elif field == "Condition Immunities":
                monster["condition_immunities"] = parse_damage_list(value)

            elif field == "Senses":
                senses, pp = parse_senses(value)
                monster["senses"] = senses
                monster["passive_perception"] = pp

            elif field == "Languages":
                raw = value.strip()
                if raw and raw != "—":
                    monster["languages"] = [l.strip() for l in re.split(r",\s*", raw) if l.strip()]

            elif field == "Challenge":
                cm2 = re.match(r"(\S+)\s*\(([^)]+)\)", value)
                if cm2:
                    monster["cr"] = cm2.group(1)
                    monster["xp"] = parse_xp(cm2.group(2))

            i += 1
            continue

        # Action/trait lines (***Name.*** desc)
        if line.startswith("***"):
            flush_action(action_buffer, current_category)
            action_buffer = [line]
            i += 1
            continue

        # Continuation of previous action
        if action_buffer and line.strip() and not line.startswith("<") and not line.startswith("|"):
            action_buffer.append(line)
            i += 1
            continue

        i += 1

    flush_action(action_buffer, current_category)

    return monster, actions


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS monsters (
    id                      VARCHAR PRIMARY KEY,
    name                    VARCHAR NOT NULL,
    size                    VARCHAR,
    type                    VARCHAR,
    subtype                 VARCHAR,
    alignment               VARCHAR,
    ac                      INTEGER,
    ac_notes                VARCHAR,
    hp                      INTEGER,
    hp_dice                 VARCHAR,
    str                     INTEGER,
    dex                     INTEGER,
    con                     INTEGER,
    int                     INTEGER,
    wis                     INTEGER,
    cha                     INTEGER,
    cr                      VARCHAR,
    xp                      INTEGER,
    languages               VARCHAR[],
    passive_perception      INTEGER,
    senses                  STRUCT(name VARCHAR, range_ft INTEGER)[],
    speeds                  STRUCT(mode VARCHAR, ft INTEGER)[],
    saving_throws           STRUCT(ability VARCHAR, bonus INTEGER)[],
    skills                  STRUCT(name VARCHAR, bonus INTEGER)[],
    damage_immunities       VARCHAR[],
    damage_resistances      VARCHAR[],
    damage_vulnerabilities  VARCHAR[],
    condition_immunities    VARCHAR[],
    legendary               BOOLEAN,
    has_lair                BOOLEAN,
    source_line             INTEGER
);

CREATE TABLE IF NOT EXISTS monster_actions (
    id              INTEGER PRIMARY KEY,
    monster_id      VARCHAR REFERENCES monsters(id),
    category        VARCHAR,
    name            VARCHAR,
    cost            INTEGER,
    description     VARCHAR,
    is_attack       BOOLEAN,
    attack_type     VARCHAR,
    to_hit          INTEGER,
    reach_or_range  VARCHAR,
    damage_dice     VARCHAR,
    damage_type     VARCHAR,
    save_dc         INTEGER,
    save_ability    VARCHAR
);
"""

def load_db(monsters: list[dict], all_actions: list[tuple[str, dict]]):
    con = duckdb.connect(DB_FILE)
    con.execute(SCHEMA_SQL)
    con.execute("DELETE FROM monster_actions")
    con.execute("DELETE FROM monsters")

    # Insert monsters
    con.executemany(
        """
        INSERT INTO monsters VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            (
                m["id"], m["name"], m["size"], m["type"], m["subtype"],
                m["alignment"], m["ac"], m["ac_notes"], m["hp"], m["hp_dice"],
                m["str"], m["dex"], m["con"], m["int"], m["wis"], m["cha"],
                m["cr"], m["xp"],
                m["languages"],
                m["passive_perception"],
                m["senses"],
                m["speeds"],
                m["saving_throws"],
                m["skills"],
                m["damage_immunities"],
                m["damage_resistances"],
                m["damage_vulnerabilities"],
                m["condition_immunities"],
                m["legendary"],
                m["has_lair"],
                m["source_line"],
            )
            for m in monsters
        ],
    )

    # Insert actions
    con.executemany(
        """
        INSERT INTO monster_actions
            (id, monster_id, category, name, cost, description,
             is_attack, attack_type, to_hit, reach_or_range,
             damage_dice, damage_type, save_dc, save_ability)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                idx, mid,
                a["category"], a["name"], a["cost"], a["description"],
                a["is_attack"], a["attack_type"], a["to_hit"], a["reach_or_range"],
                a["damage_dice"], a["damage_type"], a["save_dc"], a["save_ability"],
            )
            for idx, (mid, a) in enumerate(all_actions)
        ],
    )

    con.close()
    return con


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Parsing {SOURCE}...")
    raw_blocks = extract_stat_blocks(SOURCE)
    print(f"  Found {len(raw_blocks)} stat blocks")

    monsters = []
    all_actions: list[tuple[str, dict]] = []
    skipped = []

    for start_line, name, lines in raw_blocks:
        try:
            m, acts = parse_block(name, start_line, lines)
            monsters.append(m)
            for a in acts:
                all_actions.append((m["id"], a))
        except Exception as e:
            skipped.append((name, str(e)))

    print(f"  Parsed {len(monsters)} monsters, {len(all_actions)} actions")
    if skipped:
        print(f"  Skipped {len(skipped)}: {skipped[:5]}")

    print(f"Loading into {DB_FILE}...")
    load_db(monsters, all_actions)
    print("  Done.")

    # Quick sanity check
    con = duckdb.connect(DB_FILE)
    n_monsters = con.execute("SELECT COUNT(*) FROM monsters").fetchone()[0]
    n_actions  = con.execute("SELECT COUNT(*) FROM monster_actions").fetchone()[0]
    print(f"\nDatabase summary:")
    print(f"  monsters      : {n_monsters}")
    print(f"  monster_actions: {n_actions}")
    print()
    print("Sample — top 5 by CR:")
    rows = con.execute("""
        SELECT name, cr, xp, type, alignment
        FROM monsters
        WHERE cr ~ '^\d+$'
        ORDER BY CAST(cr AS INTEGER) DESC
        LIMIT 5
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<30} CR {r[1]:<4} {r[2]:>7} XP  {r[3]}, {r[4]}")

    print()
    print("Sample — legendary monsters:")
    rows = con.execute("""
        SELECT name, cr, type FROM monsters WHERE legendary ORDER BY name LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<30} CR {r[1]}  ({r[2]})")

    print()
    print("Sample — attacks with highest to_hit bonus:")
    rows = con.execute("""
        SELECT m.name, a.name, a.to_hit, a.damage_dice, a.damage_type
        FROM monster_actions a JOIN monsters m ON m.id = a.monster_id
        WHERE a.is_attack AND a.to_hit IS NOT NULL
        ORDER BY a.to_hit DESC
        LIMIT 8
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<30} {r[1]:<25} +{r[2]}  {r[3]} {r[4]}")

    con.close()


if __name__ == "__main__":
    main()

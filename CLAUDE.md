# CLAUDE.md — AI Assistant Guide for cc-srd5

## Project Overview

**cc-srd5** is a documentation conversion project that transforms the D&D 5th Edition System Reference Document 5.1 (SRD 5.1) from its original inaccessible PDF into a clean, open-source Markdown file with multiple export formats (HTML, PDF, DOCX, ODT).

**This is not a software project.** There is no application code, no package manager, no test suite. The primary artifact is a large Markdown document (`cc-srd5.md`) and a shell script (`pandoc.sh`) that converts it to other formats.

**License:** CC-BY-4.0 (Creative Commons Attribution 4.0 International)

---

## Repository Structure

```
cc-srd5/
├── cc-srd5.md                      # PRIMARY SOURCE — the full SRD 5.1 in Markdown (~46k lines)
├── changes-50-to-51.md             # Documents differences between SRD 5.0 and 5.1
├── pandoc.sh                       # Build script — converts cc-srd5.md to output formats
├── README.md                       # Project documentation and FAQ
├── .gitignore
├── conversions/                    # Generated output files (do not hand-edit)
│   ├── cc-srd5.css                 # Stylesheet for HTML/PDF output
│   ├── cc-srd5.html.template       # Pandoc HTML5 template with navigation sidebar
│   ├── custom-reference.docx       # Reference styles for DOCX output
│   ├── custom-reference.odt        # Reference styles for ODT output
│   ├── cc-srd5.html                # Generated HTML (do not commit if regenerating locally)
│   ├── cc-srd5.pdf                 # Generated PDF
│   ├── cc-srd5.docx                # Generated Word document
│   └── cc-srd5.odt                 # Generated OpenDocument
├── dictionaries/                   # Spellcheck support
│   ├── SRD5.wordlist               # Source wordlist (one word per line)
│   ├── SRD5.aspell.en.pws          # Generated Aspell personal wordlist
│   ├── SRD5.odf.dic                # Generated ODF/LibreOffice dictionary
│   ├── en-SRD5                     # Generated Aspell binary dictionary
│   ├── dictgen.sh                  # Script to regenerate dictionaries from SRD5.wordlist
│   └── README.md                   # Dictionary documentation
└── licensing/                      # License texts and font attributions
    ├── LICENSING.md
    ├── CC-BY-4.0.txt
    ├── MIT_license_Normalizejs.txt
    ├── OFL.txt
    ├── README-Alegreya.md
    └── README-Alegreya-Sans.md
```

---

## Source of Truth

**`cc-srd5.md` is the single source of truth.** All other output files in `conversions/` are generated artifacts from this file. Never directly edit any file under `conversions/` — changes there will be overwritten the next time `pandoc.sh` is run.

---

## Build System

### Requirements

- **pandoc** — document converter
- **pantable** (pandoc-table) — Pandoc filter for table processing
- **weasyprint** — PDF rendering engine used by Pandoc

### Running the Build

```sh
# Generate a single format
./pandoc.sh html
./pandoc.sh pdf
./pandoc.sh docx
./pandoc.sh odt

# Generate all formats
./pandoc.sh all
```

### Build Pipeline Details

- **HTML/PDF:** Pandoc reads `cc-srd5.md` directly with the `markdown+header_attributes` format, using `conversions/cc-srd5.html.template` and `conversions/cc-srd5.css`.
- **DOCX/ODT:** Pandoc does not support HTML tables embedded in Markdown for these formats, so it first generates `conversions/cc-srd5.html`, then converts the HTML to DOCX/ODT using `custom-reference.*` as style references.
- **`all` target:** Generates PDF, then DOCX, then ODT in sequence.

---

## Dictionary Maintenance

The `dictionaries/` directory contains spellcheck support for editors using Aspell or LibreOffice.

**To regenerate dictionaries after editing `SRD5.wordlist`:**

```sh
cd dictionaries/
./dictgen.sh
```

This creates:
- `SRD5.aspell.en.pws` — Aspell personal wordlist
- `SRD5.odf.dic` — LibreOffice/ODF dictionary
- `en-SRD5` — Aspell binary dictionary (requires `aspell` in PATH; skipped if not found)

**Source file:** `dictionaries/SRD5.wordlist` — one word per line, no header. Edit this file to add SRD-specific proper nouns or game terms.

---

## Markdown Conventions in `cc-srd5.md`

### Format
- Markdown dialect: `markdown+header_attributes` (Pandoc extended Markdown)
- HTML tables are embedded inline in the Markdown — do not convert them to Markdown tables; Pandoc's DOCX/ODT pipeline requires them in HTML form to render correctly.

### Section IDs
Headings use explicit ID attributes for internal links:
```markdown
## Spell Name {#spell-name}
```

### Internal Links
Spells, conditions, and magic items are cross-linked using anchor IDs:
```markdown
[*charm person*](#charm-person)
```

### Heading Depth
- Table of contents depth is set to 2 (H1 + H2 only).
- Use heading levels consistently with the SRD's chapter/section structure.

---

## Content Guidelines

This project has strict rules about what content belongs here:

### What to include
- Verbatim or lightly corrected text from the SRD 5.1 CC-BY-4.0 PDF
- Fixes for clear typographical errors, copy-paste artifacts, or formatting mistakes from the source PDF
- Replacement of OGL Product Identity terms with generic alternatives (see README for the full list)

### What NOT to include
- Errata or rules corrections not present in the SRD 5.1 PDF itself
- First-party publisher content not included in the SRD 5.1
- Third-party content
- Rules improvements or houserules
- Any content not explicitly covered by the CC-BY-4.0 license

### OGL Product Identity Terms
The following specific replacements have been made to remove trademarked/OGL-reserved terms (do not reintroduce these):
- hooked hulk (replaces a creature name in *guards and wards*)
- eyestalker (replaces a creature name in *deck of illusions*)
- maze demon (replaces a creature name in *maze*)
- fey plane, shadow plane (replaces setting-specific plane names)
- primordial chaos (replaces a setting-specific plane)
- *Orb of the Wyrm* (replaces a named artifact)
- Chains of the Deodand (replaces a Warlock eldritch invocation name)
- serpentfolk (replaces a setting-specific ethnicity)
- demon lords, archdevils, pit fiends, balors (replace specific named beings)

---

## Development Branch

Active development branch: `claude/add-claude-documentation-0Lvqi`
Main branch: `main`

---

## No Tests or CI

There is no automated test suite and no CI/CD pipeline. Quality assurance is manual:
- Review conversions after running `pandoc.sh`
- Use spellcheck dictionaries in `dictionaries/` with Aspell or LibreOffice
- Compare against the SRD 5.1 PDF for content accuracy

---

## Typical Tasks for AI Assistants

| Task | Approach |
|------|----------|
| Fix a typo or formatting error in the SRD | Edit `cc-srd5.md` directly |
| Add a missing SRD term to the spellcheck list | Add to `dictionaries/SRD5.wordlist`, then run `dictgen.sh` |
| Improve HTML output appearance | Edit `conversions/cc-srd5.css` or `conversions/cc-srd5.html.template` |
| Add a new output format | Add a function and case to `pandoc.sh` |
| Update licensing info | Edit files in `licensing/` and `README.md` |
| Regenerate output files | Run `./pandoc.sh all` (requires pandoc, pantable, weasyprint) |

**Do not** create new source files unless explicitly necessary. The project intentionally keeps a minimal file count with `cc-srd5.md` as the sole content source.

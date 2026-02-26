---
name: paper-parse-solar-energy-materials-solar-cells
description: >
  Parse a Solar Energy Materials and Solar Cells (SEMSC, Elsevier) PDF into
  a structured set of files: meta.json, full Markdown, split body parts, and
  cropped figure images. SEMSC uses "Fig. N." caption format (abbreviated,
  period after numeral), Arabic numbered section headers with subsections
  (1. Introduction, 2. Experimental, 2.1. Design, ...), two-column Elsevier
  layout, spaced-letter "A R T I C L E I N F O" / "A B S T R A C T" blocks,
  and bracketed reference style [N] with author initials-first format. Online
  SI (Fig. SN) may be referenced in text but is not extracted locally. Use
  this skill whenever the user wants to parse, convert, or extract content
  from a SEMSC PDF — including requests like "논문 파싱", "그림 추출", "md로 변환",
  "parse this paper", "extract figures". Output goes to ./output/{slug}/.
---

# paper-parse-solar-energy-materials-solar-cells

Converts a Solar Energy Materials and Solar Cells PDF into a structured file
set for downstream use (RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Solar Energy Materials and Solar Cells* (SEMSC)
- Publisher: Elsevier
- DOI prefix: `10.1016/j.solmat.`
- ISSN: 0927-0248
- ScienceDirect: https://www.sciencedirect.com/journal/solar-energy-materials-and-solar-cells

---

## Key Format Differences

| Feature | Scientific Reports | **SEMSC (Elsevier)** |
|---|---|---|
| Caption format | `Figure N.` | **`Fig. N.`** (abbreviated, period after numeral) |
| Table caption | `Table N.` | **`Table N`** (above table, Elsevier style) |
| Section headers | Unnumbered | **Arabic: `1. Introduction`**, subsections `2.1.`, `2.2.1.` |
| Abstract heading | `## Abstract` | **`A B S T R A C T`** (spaced letters) |
| Article info block | — | **`A R T I C L E I N F O`** (dates + keywords) |
| Keywords | — | **Comma-separated, in article info block** |
| Reference format | `1. Author et al.` | **`[N] F.I. Surname, Title, J. Abbrev. Vol (Year) pages, doi.`** |
| Supplementary | Separate SI PDF | **Online only; Fig. SN refs in text; not extracted locally** |
| Slug convention | DOI number | **`{FirstAuthorYear}`** (e.g. `Zambrano-Mera_2022`) |

---

## Pipeline

```
PDF
 ├─ Step 1 — Image extraction   → {slug}-figure{N}.png
 ├─ Step 2 — Full Markdown      → {slug}-full.md (inline **Fig. N.** captions)
 ├─ Step 3 — Caption splitting  → {slug}-figure{N}.md
 ├─ Step 4 — Body split         → header / main / reference / backmatter
 └─ Step 5 — Metadata           → meta.json
```

### Output File Set

| File | Contents |
|---|---|
| `meta.json` | Structured metadata (title, journal, authors, year, DOI, abstract, keywords) |
| `{slug}-header.md` | Title, journal metadata, authors/affiliations, A R T I C L E I N F O, abstract |
| `{slug}-main.md` | `1. Introduction` through final section (typically `4. Conclusions`) |
| `{slug}-reference.md` | Bracketed reference list |
| `{slug}-backmatter.md` | Acknowledgements + declarations (omit if absent) |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = `{FirstAuthorYear}` (e.g. `Zambrano-Mera_2022`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

SEMSC uses abbreviated `Fig.` followed by Arabic numeral and a period:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(Fig\.)(\s*)(\d+)\.',
    re.IGNORECASE,
)
```

**Note:** In body text, figures are referenced as "Fig. 1 shows..." or "Fig. 1(a)"
(no trailing period), but **caption blocks** consistently use `Fig. N.` format.

**Supplementary figures** (`Fig. S1`, `Fig. S2`, etc.) appear in body text but are
NOT in the local PDF — they are hosted online by Elsevier. Skip; do not extract.

**Tables:** Captions appear **above** the table; format: `Table N` (Elsevier) with
description below.

### Page Header Skipping

SEMSC has a colored header band at the top of each page (journal name + DOI + article number).

```python
SEMSC_HEADER_RE = re.compile(
    r'(solar energy|solmat|contents lists|ScienceDirect|Elsevier)',
    re.IGNORECASE,
)
```

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Check top ~5% of page height for colored header band.
   If `mean(top_band) < 200` (not white), crop it off.
2. **White-margin crop.** `gray > 245` = background; tight bounding box + 10 px.
3. **Right-side column trim.** Scan right-to-left; crop at first non-white column; +12 px.

### Layout Notes

- Two-column Elsevier layout.
- Single-column figures → right-side trim applies.
- Full-width figures (both columns) → extracted as-is.
- Captions appear **below** the figure image.
- Table headings appear **above** the table.

### Column-gap detection (two-column layout)

In SEMSC's two-column Elsevier layout, single-column figures sit in the left (or right)
column while the adjacent column may contain body text **on the same page and in the
same vertical range**.  A naive "bounding box of all non-white pixels" crop includes that
text.  Fix: detect the white vertical strip between columns and clamp `cmax` there.

```python
MIN_COL_GAP_PX = 20   # minimum gap width to treat as a column separator

def find_column_gap(region_gray, white_thresh=245):
    """Return x of the largest white vertical gap in the middle-third, or None."""
    W = region_gray.shape[1]
    mid_start, mid_end = W // 3, W * 2 // 3
    col_nonwhite = np.sum(region_gray < white_thresh, axis=0)
    in_gap, gap_start, best = False, 0, (0, 0, 0)
    for x in range(mid_start, mid_end):
        if col_nonwhite[x] == 0:
            if not in_gap:
                in_gap, gap_start = True, x
        else:
            if in_gap:
                w = x - gap_start
                if w > best[2]:
                    best = (gap_start, x, w)
                in_gap = False
    if in_gap:
        w = mid_end - gap_start
        if w > best[2]:
            best = (gap_start, mid_end, w)
    return best[0] if best[2] >= MIN_COL_GAP_PX else None

# After computing cmin, cmax from bounding box:
col_gap_x = find_column_gap(fig_region)
if col_gap_x is not None and col_gap_x < cmax:
    cmax = min(cmax, col_gap_x - 1)   # trim to left column
```

**Why it works:** The column gap in Elsevier PDFs is ≈12 pt (≈48–80 px at ZOOM=4).
Single-column figures have a gap in the middle third; full-width figures do not.

**Known case:** Figure 6 (Zambrano-Mera 2022) — single-column figure with CRediT text
in the right column at the same vertical range.  Column gap detected at x=1149/2382 px.

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for off-white/gray backgrounds |
| `pad` | `10` | |
| `HEADER_H_PX` | `200` | SEMSC running header ends at ~135 px; 200 is safe margin |
| `MIN_COL_GAP_PX` | `20` | Minimum white gap width to trigger column trim |

---

## Step 2 — Markdown Construction

**Section headers.** Map to `##` / `###` / `####`:

```markdown
## 1. Introduction
## 2. Experimental
### 2.1. Design of the anti-reflective coatings
### 2.2. Sample preparation
#### 2.2.1. Deposition of single-layer thin films
#### 2.2.2. Deposition of multi-layer thin films
## 3. Results and discussion
## 4. Conclusions
## References
```

**A R T I C L E I N F O block.** Transcribe into header:

```markdown
**Received:** 16 March 2022
**Received in revised form:** 29 April 2022
**Accepted:** 1 May 2022

**Keywords:** Anti-reflective coatings, PV glass Cover, Zr-oxides doping, Optical properties, Mechanical properties, Nanoindentation
```

**A B S T R A C T block.** Transcribe as:

```markdown
## Abstract

Multi-layer systems are frequently used as anti-reflective coatings…
```

**Captions.** Inline at figure location: `**Fig. N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert Unicode to LaTeX.

**Authors.** Build a Markdown table with **bare ASCII superscript** affiliation markers
(NOT LaTeX `$^a$` — just `^a`, `^{a,1}`, `^b`, etc.):

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| Dario F. Zambrano-Mera^a | Departamento de Ingeniería Química, Biotecnología y Materiales, Facultad de Ciencias Físicas y Matemáticas, Universidad de Chile, Chile | *Corresponding |
| Roberto Villarroel^{a,1} | Departamento de Ingeniería Química, Biotecnología y Materiales, Facultad de Ciencias Físicas y Matemáticas, Universidad de Chile, Chile | ^1 Currently at Instituto de Física, Pontificia Universidad Católica de Chile |
| María I. Pintor-Monroy^b | Department of Materials Science and Engineering, The University of Texas at Dallas, USA | |
```

**Superscript key format:**
- `^a` = affiliation key `a`
- `^{a,1}` = affiliation key `a` + footnote number `1` (note in the Notes column)
- `*` in the superscript or Notes column = corresponding author

**Every author must have at least one affiliation.** The Affiliation column must never
be empty for a data row. Copy the shared affiliation for authors who share the same key.

Include: `*E-mail: author@domain.com`

**Journal metadata line** (at top of header):
```
Solar Energy Materials and Solar Cells, Vol. 243, 2022, 111784
DOI: https://doi.org/10.1016/j.solmat.2022.111784
© 2022 Elsevier B.V. All rights reserved.
```

---

## Step 3 — Caption Splitting

```bash
python scripts/split_captions.py {slug}-full.md <output_dir> --slug {slug} --out-main {slug}-full-clean.md
```

Caption file format:
```markdown
# Figure N

**Fig. N.** Full caption text…
```

---

## Step 4 — Body Split

```bash
python scripts/split_body.py {slug}-full-clean.md <output_dir> --slug {slug}
```

- **Header:** everything before `## 1. Introduction`
- **Main:** `## 1. Introduction` through last body section
- **References:** from `## References`
- **Backmatter:** `## Acknowledgements`, `## CRediT authorship contribution statement`,
  `## Declaration of competing interest`, `## Data availability`,
  `## Appendix A. Supplementary data` — combine all into one file (omit if absent)

---

## Step 5 — meta.json

```json
{
  "title": "Optical and mechanical properties of Zr-oxide doped TiO2/SiO2 anti-reflective coatings for PV glass covers",
  "journal": "Solar Energy Materials and Solar Cells",
  "year": "2022",
  "volume": "243",
  "issue": null,
  "article_number": "111784",
  "pages": null,
  "doi": "10.1016/j.solmat.2022.111784",
  "received": "2022-03-16",
  "revised": "2022-04-29",
  "accepted": "2022-05-01",
  "authors": [
    {
      "name": "Dario F. Zambrano-Mera",
      "affiliation_key": "a",
      "affiliations": ["Departamento de Ingeniería Química, Biotecnología y Materiales, Facultad de Ciencias Físicas y Matemáticas, Universidad de Chile, Chile"],
      "corresponding": true,
      "email": "dzambrano@ing.uchile.cl"
    },
    {
      "name": "Roberto Villarroel",
      "affiliation_key": "a",
      "affiliations": ["Departamento de Ingeniería Química, Biotecnología y Materiales, Facultad de Ciencias Físicas y Matemáticas, Universidad de Chile, Chile"],
      "corresponding": false,
      "footnote": "Currently at Instituto de Física, Pontificia Universidad Católica de Chile"
    }
  ],
  "affiliations": {
    "a": "Departamento de Ingeniería Química, Biotecnología y Materiales, Facultad de Ciencias Físicas y Matemáticas, Universidad de Chile, Chile",
    "b": "Department of Materials Science and Engineering, The University of Texas at Dallas, USA",
    "c": "Departamento de Ingeniería en Maderas, Universidad del Bio-Bio, Chile"
  },
  "abstract": "Abstract text…",
  "keywords": ["Anti-reflective coatings", "PV glass Cover", "Zr-oxides doping", "Optical properties", "Mechanical properties", "Nanoindentation"],
  "slug": "Zambrano-Mera_2022",
  "figures": [
    {"index": 1, "file": "Zambrano-Mera_2022-figure1.png", "caption_file": "Zambrano-Mera_2022-figure1.md", "caption": "…"}
  ]
}
```

**Notes:**
- SEMSC uses article numbers instead of page ranges. Set `"pages": null` and use `"article_number"` field.
- Every author entry must have a non-empty `affiliations` list. There are no authorless affiliations in this format — the full affiliation string is always in the table row alongside the author name.
- `affiliation_key` is the letter from the superscript (e.g., `"a"`, `"b"`, `"c"`). Include the top-level `affiliations` dict for fast cross-reference lookup.
- For `^{a,1}` superscripts: `affiliation_key = "a"`, `footnote = "..."` (content from Notes column).

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.`
- [ ] Colored page header bar **not** visible in any PNG (use `HEADER_H_PX=200`)
- [ ] No body text from adjacent column visible in figure PNGs (column-gap trim applied)
- [ ] Abstract has `## Abstract` heading (Elsevier spaced-letter heading → `## Abstract`)
- [ ] Keywords are comma-separated (Elsevier style)
- [ ] Received/Revised/Accepted dates in header
- [ ] References use bracketed format `[N] F.I. Surname, ...`
- [ ] `Fig. SN` references in body text are NOT extracted as local files
- [ ] `meta.json` has `article_number` field (not `pages`)
- [ ] `## 1. Introduction` in `{slug}-main.md`
- [ ] `## References` in `{slug}-reference.md`
- [ ] Every author row in the markdown table has a non-empty affiliation column
- [ ] `meta.json` every author entry has non-empty `affiliations` list
- [ ] `meta.json` populated

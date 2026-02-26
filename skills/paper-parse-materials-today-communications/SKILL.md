---
name: paper-parse-materials-today-communications
description: >
  Parse a Materials Today Communications (MTC, Elsevier) PDF into a structured
  set of files: meta.json, full Markdown, split body parts, and cropped figure
  images. MTC uses "Fig. N." caption format (abbreviated, period after numeral),
  Arabic numbered section headers with subsections (1. Introduction,
  2. Experimental, 2.1., ...), two-column Elsevier layout, spaced-letter
  "A R T I C L E I N F O" / "A B S T R A C T" blocks, keywords listed one per
  line in the ARTICLE INFO block, and bracketed reference style [N] with
  author initials-first format. No supplementary information (SI) PDF is
  typically published separately for MTC articles. Use this skill whenever the
  user wants to parse, convert, or extract content from an MTC PDF — including
  requests like "논문 파싱", "그림 추출", "md로 변환", "parse this paper",
  "extract figures". Output goes to ./output/{slug}/.
---

# paper-parse-materials-today-communications

Converts a Materials Today Communications PDF into a structured file set for
downstream use (RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Materials Today Communications* (MTC)
- Publisher: Elsevier
- DOI prefix: `10.1016/j.mtcomm.`
- ISSN: 2352-4928
- Website: https://www.journals.elsevier.com/materials-today-communications
- ScienceDirect: https://www.sciencedirect.com/journal/materials-today-communications

---

## Key Format Differences

| Feature | Scientific Reports | SEMSC | **MTC (Elsevier)** |
|---|---|---|---|
| Caption format | `Figure N.` | `Fig. N.` | **`Fig. N.`** (abbreviated, period after numeral) |
| Table caption | `Table N.` | `Table N` (above table) | **`Table N`** (above table, Elsevier style) |
| Section headers | Unnumbered | `1. Introduction` | **Arabic: `1. Introduction`**, subsections `2.1.`, `2.2.1.` |
| Abstract heading | `## Abstract` | `A B S T R A C T` | **`A B S T R A C T`** (spaced letters) |
| Article info block | — | `A R T I C L E I N F O` | **`A R T I C L E I N F O`** (dates + keywords) |
| Keywords | — | Comma-separated | **One per line** in article info block |
| Reference format | `1. Author et al.` | `[N] F.I. Surname, ...` | **`[N] F.I. Surname, Title, J. Abbrev. Vol (Year) pages, doi.`** |
| Supplementary | Separate SI PDF | Online SI | **No SI typically** |
| Slug convention | DOI number | `{FirstAuthorYear}` | **`{FirstAuthorYear}`** (e.g. `Sezgin_2023`) |

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
| `{slug}-main.md` | `1. Introduction` through final section (typically `4. Conclusion`) |
| `{slug}-reference.md` | Bracketed reference list |
| `{slug}-backmatter.md` | Declaration of Competing Interest + Data availability + Acknowledgements (omit if absent) |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = `{FirstAuthorYear}` (e.g. `Sezgin_2023`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

MTC uses abbreviated `Fig.` followed by Arabic numeral and a period:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(Fig\.)(\s*)(\d+)\.',
    re.IGNORECASE,
)
```

**Note:** In body text, figures are referenced as "Fig. 1 shows..." or "Fig. 1a"
(no trailing period), but **caption blocks** consistently use `Fig. N.` format.

**Tables:** Captions appear **above** the table; format: `Table N` (Elsevier) with
description below.

### Page Header Skipping

MTC has a running header at the top of each page (journal name + volume + article number + page number).

```python
MTC_HEADER_RE = re.compile(
    r'(materials today|mtcomm|ScienceDirect|Elsevier)',
    re.IGNORECASE,
)
```

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Check top ~5% of page height for colored header band.
   If `mean(top_band) < 200` (not white), crop it off.
2. **White-margin crop.** `gray > 245` = background; tight bounding box + 10 px.
3. **Right-side column trim.** Scan right-to-left; crop at first non-white column; +12 px.

### Column-Gap Detection (two-column layout)

In MTC's two-column Elsevier layout, single-column figures sit in the left (or right)
column while the adjacent column may contain body text **on the same page and in the
same vertical range**. A naive bounding-box crop includes that text. Fix: detect the
white vertical strip between columns and clamp `cmax` there.

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

### Layout Notes

- Two-column Elsevier layout.
- Single-column figures → column-gap trim applies.
- Full-width figures (both columns) → extracted as-is.
- Captions appear **below** the figure image.
- Table headings appear **above** the table.

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for off-white/gray backgrounds |
| `pad` | `10` | |
| `HEADER_H_PX` | `200` | MTC running header ends at ~135 px; 200 is safe margin |
| `MIN_COL_GAP_PX` | `20` | Minimum white gap width to trigger column trim |

---

## Step 2 — Markdown Construction

**Section headers.** Map to `##` / `###` / `####`:

```markdown
## 1. Introduction
## 2. Experimental
### 2.1. Thin film preparation
### 2.2. Structural and optical characterizations
### 2.3. Mechanical characterizations
## 3. Results and discussion
### 3.1. Structural properties
### 3.2. Optical properties
### 3.3. Mechanical properties
## 4. Conclusion
## References
```

**A R T I C L E I N F O block.** Keywords appear one per line in MTC.
Transcribe into header as comma-separated:

```markdown
**Available online:** 30 May 2023

**Keywords:** Thin film, Titanium dioxide, Zirconium oxide, Sputtering, Optical properties, Mechanical properties
```

**A B S T R A C T block.** Transcribe as:

```markdown
## Abstract

In this study, the structural, optical, and mechanical properties…
```

**Captions.** Inline at figure location: `**Fig. N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert Unicode to LaTeX.

**Authors.** Build a Markdown table with **bare ASCII superscript** affiliation markers
(NOT LaTeX `$^a$` — just `^a`, `^{a,b}`, `^{c,d}`, etc.):

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| Alperen Sezgin^{a,b} | Gebze Technical University, Materials Science and Engineering Department, 41400 Gebze, Kocaeli, Turkey; Şişecam Science, Technology and Design Center, Cumhuriyet Mh. Şişecam Yolu Sk. No: 2, 41400 Gebze, Kocaeli, Turkey | *Corresponding |
| Radim Čtvrtlík^{c,d} | Palacký University in Olomouc, Faculty of Science, Joint Laboratory of Optics, 17. Listopadu 12, 771 46 Olomouc, Czech Republic; Institute of Physics of the Czech Academy of Sciences, Joint Laboratory of Optics, 17. Listopadu 50a, 772 07 Olomouc, Czech Republic | |
```

**Superscript key format:**
- `^a` = affiliation key `a`
- `^{a,b}` = affiliation keys `a` and `b` (author belongs to both)
- `*` in Notes column = corresponding author

**Every author must have at least one affiliation.** The Affiliation column must never
be empty for a data row. Copy the shared affiliation for authors who share the same key.
For `^{a,b}` authors: concatenate both affiliations separated by `;`.

Include: `*E-mail: author@domain.com`

**Journal metadata line** (at top of header):

```
Materials Today Communications, Vol. 35, 2023, 106334
DOI: https://doi.org/10.1016/j.mtcomm.2023.106334
© 2023 Elsevier Ltd. All rights reserved.
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
- **Backmatter:** `## Declaration of Competing Interest`, `## Data availability`,
  `## Acknowledgements` — combine all into one file (omit if absent)

---

## Step 5 — meta.json

```json
{
  "title": "Optical, structural and mechanical properties of TiO2 and TiO2-ZrO2 thin films deposited on glass using magnetron sputtering",
  "journal": "Materials Today Communications",
  "year": "2023",
  "volume": "35",
  "issue": null,
  "article_number": "106334",
  "pages": null,
  "doi": "10.1016/j.mtcomm.2023.106334",
  "received": null,
  "revised": null,
  "accepted": null,
  "available_online": "2023-05-30",
  "authors": [
    {
      "name": "Alperen Sezgin",
      "affiliation_keys": ["a", "b"],
      "affiliations": [
        "Gebze Technical University, Materials Science and Engineering Department, 41400 Gebze, Kocaeli, Turkey",
        "Şişecam Science, Technology and Design Center, Cumhuriyet Mh. Şişecam Yolu Sk. No: 2, 41400 Gebze, Kocaeli, Turkey"
      ],
      "corresponding": true,
      "email": "alperen.sezgin@sisecam.com"
    }
  ],
  "affiliations": {
    "a": "Gebze Technical University, Materials Science and Engineering Department, 41400 Gebze, Kocaeli, Turkey",
    "b": "Şişecam Science, Technology and Design Center, Cumhuriyet Mh. Şişecam Yolu Sk. No: 2, 41400 Gebze, Kocaeli, Turkey",
    "c": "Palacký University in Olomouc, Faculty of Science, Joint Laboratory of Optics of Palacký University and Institute of Physics AS CR, 17. Listopadu 12, 771 46 Olomouc, Czech Republic",
    "d": "Institute of Physics of the Czech Academy of Sciences, Joint Laboratory of Optics of Palacký University and Institute of Physics AS CR, 17. Listopadu 50a, 772 07 Olomouc, Czech Republic"
  },
  "abstract": "In this study, the structural, optical, and mechanical properties…",
  "keywords": ["Thin film", "Titanium dioxide", "Zirconium oxide", "Sputtering", "Optical properties", "Mechanical properties"],
  "slug": "Sezgin_2023",
  "figures": [
    {"index": 1, "file": "Sezgin_2023-figure1.png", "caption_file": "Sezgin_2023-figure1.md", "caption": "…"}
  ]
}
```

**Notes:**
- MTC uses article numbers instead of page ranges. Set `"pages": null` and use `"article_number"` field.
- Authors with `^{a,b}` superscripts have `"affiliation_keys": ["a", "b"]` and a list of both affiliations.
- Every author entry must have a non-empty `affiliations` list.
- Include top-level `affiliations` dict for fast cross-reference lookup.
- `available_online` field (not `received`/`revised`/`accepted`) if only that date is present in ARTICLE INFO.

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.`
- [ ] Page running header (journal + vol + article number) **not** visible in any PNG
- [ ] No body text from adjacent column visible in figure PNGs (column-gap trim applied)
- [ ] Abstract has `## Abstract` heading
- [ ] Keywords are comma-separated in header (even if one-per-line in source PDF)
- [ ] References use bracketed format `[N] F.I. Surname, ...`
- [ ] `meta.json` has `article_number` field (not `pages`)
- [ ] `## 1. Introduction` in `{slug}-main.md`
- [ ] `## References` in `{slug}-reference.md`
- [ ] Every author row in the markdown table has a non-empty affiliation column
- [ ] Authors with multiple affiliations (`^{a,b}`) have all affiliations listed
- [ ] `meta.json` every author entry has non-empty `affiliations` list
- [ ] `meta.json` populated

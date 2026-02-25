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

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for off-white/gray backgrounds |
| `pad` | `10` | |

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

**Authors.** Build a Markdown table with superscript affiliation markers:

| Author | Affiliation | Notes |
|---|---|---|
| Dario F. Zambrano-Mera^a | Dept. Ingeniería Química…, Universidad de Chile, Chile | *Corresponding |

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
      "affiliations": ["Dept. Ingeniería Química…, Universidad de Chile, Chile"],
      "corresponding": true,
      "email": "author@domain.com"
    }
  ],
  "abstract": "Abstract text…",
  "keywords": ["Anti-reflective coatings", "PV glass Cover", "Zr-oxides doping", "Optical properties", "Mechanical properties", "Nanoindentation"],
  "slug": "Zambrano-Mera_2022",
  "figures": [
    {"index": 1, "file": "Zambrano-Mera_2022-figure1.png", "caption_file": "Zambrano-Mera_2022-figure1.md", "caption": "…"}
  ]
}
```

**Note:** SEMSC uses article numbers instead of page ranges. Set `"pages": null` and
use `"article_number"` field.

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.`
- [ ] Colored page header bar not visible in any PNG
- [ ] Abstract has `## Abstract` heading (Elsevier spaced-letter heading → `## Abstract`)
- [ ] Keywords are comma-separated (Elsevier style)
- [ ] Received/Revised/Accepted dates in header
- [ ] References use bracketed format `[N] F.I. Surname, ...`
- [ ] `Fig. SN` references in body text are NOT extracted as local files
- [ ] `meta.json` has `article_number` field (not `pages`)
- [ ] `## 1. Introduction` in `{slug}-main.md`
- [ ] `## References` in `{slug}-reference.md`
- [ ] `meta.json` populated

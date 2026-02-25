---
name: paper-parse-optics-express
description: >
  Parse an Optics Express (Optica Publishing Group, formerly OSA) PDF into a
  structured set of files: meta.json, full Markdown, split body parts, and
  cropped figure images. Optics Express uses "Fig. N." caption format (abbreviated),
  Arabic numbered section headers (1. Introduction, 2. Methods, ...), and
  two-column layout. Use this skill whenever the user wants to parse, convert, or
  extract content from an Optics Express PDF — including requests like
  "논문 파싱", "그림 추출", "md로 변환", "parse this paper", "extract figures".
  Output goes to a user-specified directory (default: ./output/{slug}/).
---

# paper-parse-optics-express

Converts an Optics Express PDF into a structured file set for downstream use
(RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Optics Express* (OE)
- Publisher: Optica Publishing Group (formerly OSA)
- DOI prefix: `10.1364/OE`
- ISSN: 1094-4087 (Online, open access)

---

## Key Format Differences

| Feature | Scientific Reports | **Optics Express** |
|---|---|---|
| Caption format | `Figure N.` | **`Fig. N.`** (abbreviated) |
| Section headers | Unnumbered | **Arabic: `1. Introduction`** |
| Page header | Raster gray bar | **Text: "Research Article · Vol. X, No. Y..."** |
| Supplementary Info | Separate SI PDF | Typically none or embedded |
| Slug convention | DOI number | **`{AuthorYear}` (e.g. `Kim_2022`)** |

---

## Pipeline — Main Article

```
PDF
 ├─ Step 1 — Image extraction   → figure{N}.png
 ├─ Step 2 — Full Markdown      → {slug}-full.md (inline **Fig. N.** captions)
 ├─ Step 3 — Caption splitting  → {slug}-figure{N}.md
 ├─ Step 4 — Body split         → header / main / reference / backmatter
 └─ Step 5 — Metadata           → meta.json
```

### Output File Set

| File | Contents |
|---|---|
| `meta.json` | Structured metadata (title, journal, authors, year, DOI, abstract) |
| `{slug}-header.md` | Title, DOI, dates, authors/affiliations, abstract, keywords |
| `{slug}-main.md` | Section 1 (Introduction) through Conclusion |
| `{slug}-reference.md` | Numbered reference list with [CrossRef] links |
| `{slug}-backmatter.md` | Funding, Acknowledgments, Disclosures (omit if absent) |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = `{AuthorYear}` (e.g. `Kim_2022`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

Optics Express uses abbreviated `Fig.` with Arabic numeral:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(Fig\.|Table)\s+(\d+)[\.\s]',
    re.IGNORECASE,
)
```

### Page Header Skipping

Text-based running header detected via:

```python
OE_HEADER_RE = re.compile(
    r'(optics express|research article|vol\.\s*\d|letter)',
    re.IGNORECASE,
)
```

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Exits immediately (no raster bar in Optics Express).
2. **White-margin crop.** `gray > 245` = background; tight bounding box + 10 px.
3. **Right-side column trim.** Crop at first non-white column from right; +12 px.

### Layout Notes

- Two-column layout; single-column figures handled by right-side trim.
- No dashed separator lines.
- Captions appear **below** figure image.
- Color figures: lower `white_thresh` to `230` if edges are clipped.

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for colored figures |
| `pad` | `10` | |

---

## Step 2 — Markdown Construction

**Section headers.** Arabic numbered → `##`:

```markdown
## 1. Introduction
## 2. Methods
## 3. Results and Discussion
## 4. Conclusion
```

**Abstract.** Explicit heading: `## Abstract`.

**Captions.** Inline at figure location: `**Fig. N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert all Unicode math to LaTeX
(φ → `\varphi`, ε → `\varepsilon`, λ → `\lambda`, θ → `\theta`, etc.).

**Authors.** Build a Markdown table with superscript numbers:

| Author | Affiliation | Notes |
|---|---|---|
| Author Name¹* | Dept, University, City, Country | *Corresponding |

Include: `*Corresponding author: email@domain.com`

**Submission dates.** Single line:
`Received: Month DD, YYYY; revised ...; accepted ...; published ...`

**DOI.** `DOI: https://doi.org/10.1364/OE.XXX.XXXXXX`

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
- **Backmatter:** Funding / Acknowledgments / Disclosures (omit if absent)

---

## Step 5 — meta.json

```json
{
  "title": "Full paper title",
  "journal": "Optics Express",
  "year": "2022",
  "volume": "30",
  "issue": "7",
  "pages": "11740",
  "doi": "10.1364/OE.XXX.XXXXXX",
  "authors": [
    {
      "name": "Author Name",
      "affiliations": ["Dept, University, City, Country"],
      "corresponding": true,
      "email": "author@domain.com"
    }
  ],
  "abstract": "Abstract text…",
  "keywords": [],
  "slug": "Kim_2022",
  "figures": [
    {"index": 1, "file": "figure1.png", "caption_file": "Kim_2022-figure1.md", "caption": "…"}
  ]
}
```

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.` (not `Figure N.`)
- [ ] Page header text not visible in any PNG
- [ ] Color figure edges not clipped (`white_thresh` lowered if needed)
- [ ] All Unicode math converted to LaTeX
- [ ] `## 1. Introduction` in `{slug}-main.md`
- [ ] `## References` in `{slug}-reference.md`
- [ ] [CrossRef] links preserved
- [ ] `meta.json` populated

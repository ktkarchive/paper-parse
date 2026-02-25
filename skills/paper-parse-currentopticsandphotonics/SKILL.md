---
name: paper-parse-currentopticsandphotonics
description: >
  Parse a Current Optics and Photonics (COAP, Korean Optical Society) PDF into
  a structured set of files: meta.json, full Markdown, split body parts, and
  cropped figure images. COAP uses "FIG. N." caption format (all caps), Roman
  numeral section headers (I. INTRODUCTION, II. THEORY, ...), and two-column
  layout. No supplementary information (SI) is published separately for COAP.
  Use this skill whenever the user wants to parse, convert, or extract content
  from a COAP PDF — including requests like "논문 파싱", "그림 추출",
  "md로 변환", "parse this paper", "extract figures".
  Output goes to a user-specified directory (default: ./output/{slug}/).
---

# paper-parse-currentopticsandphotonics

Converts a Current Optics and Photonics PDF into a structured file set for
downstream use (RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Current Optics and Photonics* (COAP)
- Publisher: Korean Optical Society (KOS)
- DOI prefix: `10.3807/COPP`
- ISSN: 2508-7266 (Print) / 2508-7274 (Online)

---

## Key Format Differences

| Feature | Scientific Reports | **COAP** |
|---|---|---|
| Caption format | `Figure N.` | **`FIG. N.`** (all caps) |
| Section headers | Unnumbered | **Roman: `I. INTRODUCTION`** |
| Page header | Raster gray bar | **Text (journal name / running title)** |
| Supplementary Info | Separate SI PDF | **None** |
| Slug convention | DOI number | **`{AuthorYear}` (e.g. `Cho_2018`)** |

---

## Pipeline — Main Article

```
PDF
 ├─ Step 1 — Image extraction   → figure{N}.png
 ├─ Step 2 — Full Markdown      → {slug}-full.md (inline **FIG. N.** captions)
 ├─ Step 3 — Caption splitting  → {slug}-figure{N}.md
 ├─ Step 4 — Body split         → header / main / reference / backmatter
 └─ Step 5 — Metadata           → meta.json
```

### Output File Set

| File | Contents |
|---|---|
| `meta.json` | Structured metadata (title, journal, authors, year, DOI, abstract) |
| `{slug}-header.md` | Title, journal metadata, authors/affiliations, abstract, keywords |
| `{slug}-main.md` | I. INTRODUCTION through final section |
| `{slug}-reference.md` | Numbered reference list |
| `{slug}-backmatter.md` | Acknowledgements (omit if absent) |
| `figure{N}.png` | Tightly cropped figure image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = `{AuthorYear}` (e.g. `Cho_2018`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

COAP uses all-caps `FIG.` followed by Arabic numeral:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(FIG\.|TABLE)\s*([IVX\d]+)[\.\s]',
    re.IGNORECASE,
)
```

### Page Header Skipping

Text-based running header detected via:

```python
COAP_HEADER_RE = re.compile(
    r'(current optics|vol\.\s*\d|et al\.|photonics)',
    re.IGNORECASE,
)
```

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Exits immediately (no raster bar).
2. **White-margin crop.** `gray > 245` = background; tight bounding box + 10 px.
3. **Right-side column trim.** Crop at first non-white column from right; +12 px.

### Layout Notes

- Two-column layout; single-column figures handled by right-side trim.
- No dashed separator lines.
- Multiple figures per page: `prev_cap_bottom_by_page` tracker handles ordering.

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower for off-white backgrounds |
| `pad` | `10` | |

---

## Step 2 — Markdown Construction

**Section headers.** Roman numeral headings → `##`:

```markdown
## I. INTRODUCTION
## II. THEORETICAL BACKGROUND
## III. RESULTS AND DISCUSSION
## IV. CONCLUSION
```

**Abstract.** COAP has **no explicit "Abstract" heading**. Transcribe as a plain
paragraph between affiliations block and `## I. INTRODUCTION`.

**Keywords.** `**Keywords:** word1, word2, ...`

**Captions.** Inline at figure location: `**FIG. N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert Unicode PUA math (`\ue0XX`) to LaTeX.

**Authors.** Build a Markdown table:

| Author | Affiliation | Notes |
|---|---|---|
| Author Name¹* | Dept, University, City, Country | *Corresponding |

**Dates.** `(Received Month DD, YYYY : revised Month DD, YYYY : accepted Month DD, YYYY)`

---

## Step 3 — Caption Splitting

```bash
python scripts/split_captions.py {slug}-full.md <output_dir> --slug {slug} --out-main {slug}-full-clean.md
```

Caption file format:
```markdown
# Figure N

**FIG. N.** Full caption text…
```

---

## Step 4 — Body Split

```bash
python scripts/split_body.py {slug}-full-clean.md <output_dir> --slug {slug}
```

- **Header:** everything before `## I. INTRODUCTION`
- **Main:** `## I. INTRODUCTION` through last body section
- **References:** from `## REFERENCES`
- **Backmatter:** `## Acknowledgements` / `## ACKNOWLEDGMENT` (omit if absent)

---

## Step 5 — meta.json

```json
{
  "title": "Full paper title",
  "journal": "Current Optics and Photonics",
  "year": "2018",
  "volume": null,
  "issue": null,
  "pages": null,
  "doi": "10.3807/COPP.2018.2.X.XXX",
  "authors": [
    {
      "name": "Author Name",
      "affiliations": ["Dept, University, City, Country"],
      "corresponding": true,
      "email": "author@domain.com"
    }
  ],
  "abstract": "Abstract text…",
  "keywords": ["word1", "word2"],
  "slug": "Cho_2018",
  "figures": [
    {"index": 1, "file": "figure1.png", "caption_file": "Cho_2018-figure1.md", "caption": "…"}
  ]
}
```

---

## Quality Checklist

- [ ] Every `FIG. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses all-caps `FIG. N.`
- [ ] Page header text not visible in any PNG
- [ ] Abstract has no `## Abstract` heading (plain paragraph)
- [ ] All `\ue0XX` Unicode PUA characters converted to LaTeX
- [ ] `## I. INTRODUCTION` in `{slug}-main.md`
- [ ] `## REFERENCES` in `{slug}-reference.md`
- [ ] Author affiliations matched to superscript numbers
- [ ] `meta.json` populated

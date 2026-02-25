---
name: paper-parse-materials-science-poland
description: >
  Parse a Materials Science-Poland (MSP, De Gruyter / Wroclaw University of
  Technology) PDF into a structured set of files: meta.json, full Markdown,
  split body parts, and cropped figure images. MSP uses "Fig. N." caption format,
  Arabic numbered section headers (1. Introduction, 2. Experimental, ...),
  two-column layout, and bracketed reference style [N]. No supplementary
  information (SI) is published separately. Use this skill whenever the user
  wants to parse, convert, or extract content from an MSP PDF — including
  requests like "논문 파싱", "그림 추출", "md로 변환", "parse this paper", "extract figures".
  Output goes to a user-specified directory (default: ./output/{slug}/).
---

# paper-parse-materials-science-poland

Converts a Materials Science-Poland PDF into a structured file set for
downstream use (RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Materials Science-Poland* (MSP)
- Publisher: De Gruyter (on behalf of Wroclaw University of Technology)
- DOI prefix: `10.1515/msp-`
- ISSN: 2083-134X (Online) / 0137-1339 (Print, historical)

---

## Key Format Differences

| Feature | Scientific Reports | **Materials Science-Poland** |
|---|---|---|
| Caption format | `Figure N.` | **`Fig. N.`** (abbreviated, period after numeral) |
| Section headers | Unnumbered | **Arabic: `1. Introduction`** |
| Abstract heading | `## Abstract` | **None (unlabeled paragraph)** |
| Keywords | — | **`Keywords: word1; word2;`** (semicolons) |
| Reference format | `1. Author et al.` | **`[N] SURNAME F.I., Journal, Vol (Year), Pages.`** |
| Slug convention | DOI number | **`{AuthorYear}` (e.g. `Meziani_2016`)** |

---

## Pipeline — Main Article

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
| `meta.json` | Structured metadata (title, journal, authors, year, DOI, abstract) |
| `{slug}-header.md` | Title, journal metadata, authors/affiliations, abstract, keywords |
| `{slug}-main.md` | `1. Introduction` through final section (typically `4. Conclusion`) |
| `{slug}-reference.md` | Bracketed reference list |
| `{slug}-backmatter.md` | Acknowledgements (omit if absent) |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = `{AuthorYear}` (e.g. `Meziani_2016`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

MSP uses abbreviated `Fig.` followed by Arabic numeral and a period:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(Fig\.)(\s*)(\d+)\.',
    re.IGNORECASE,
)
```

**Note:** In body text, figures are referenced as "Fig. 1 shows..." (no trailing period),
but **caption blocks** consistently use `Fig. N.` with period after numeral.

### Page Header Skipping

Alternating text headers (odd = short title, even = "AUTHOR ET AL."):

```python
MSP_HEADER_RE = re.compile(
    r'(et al\.|materials science|vol\.\s*\d|\d{3,})',
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
- Captions appear **below** the figure image.

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for off-white/gray backgrounds |
| `pad` | `10` | |

---

## Step 2 — Markdown Construction

**Section headers.** Arabic numbered → `##`:

```markdown
## 1. Introduction
## 2. Experimental
## 3. Results and discussion
## 4. Conclusion
```

**Abstract.** MSP has **no explicit "Abstract" heading**. Transcribe as a plain
paragraph immediately after the affiliations block and before `**Keywords:**`.

**Keywords.** Semicolon-separated: `**Keywords:** word1; word2; word3`

**Captions.** Inline at figure location: `**Fig. N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert Unicode characters to LaTeX.

**Authors.** MSP uses ALL-CAPS surnames + initials. Build a Markdown table:

| Author | Affiliation | Notes |
|---|---|---|
| Samir Meziani¹* | CRTSE, Division…, Algeria | *Corresponding |

Include: `*E-mail: author@domain.com`

**Journal metadata line** (at top of header):
```
Materials Science-Poland, Vol(Issue), Year, pp. StartPage–EndPage
DOI: https://doi.org/10.1515/msp-XXXX-XXXX
```

Note: Strip the `© Wroclaw University of Technology.` copyright line — do not extract
as an author or affiliation.

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
- **Backmatter:** `## Acknowledgements` / `## Acknowledgments` (omit if absent)

**Note:** Conclusion may be titled `## 4. Conclusion` or `## 4. Conclusions` — both handled.

---

## Step 5 — meta.json

```json
{
  "title": "Full paper title",
  "journal": "Materials Science-Poland",
  "year": "2016",
  "volume": "34",
  "issue": "2",
  "pages": "315-321",
  "doi": "10.1515/msp-2016-XXXX",
  "authors": [
    {
      "name": "Samir Meziani",
      "affiliations": ["CRTSE, Division…, Algeria"],
      "corresponding": true,
      "email": "mezianisam@yahoo.fr"
    }
  ],
  "abstract": "Abstract text…",
  "keywords": ["SiNx:H", "oxidation", "PECVD"],
  "slug": "Meziani_2016",
  "figures": [
    {"index": 1, "file": "Meziani_2016-figure1.png", "caption_file": "Meziani_2016-figure1.md", "caption": "…"}
  ]
}
```

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.`
- [ ] Page header text not visible in any PNG
- [ ] Abstract has **no** `## Abstract` heading (plain paragraph)
- [ ] Keywords use semicolon format
- [ ] References use bracketed format `[N] SURNAME F.I., ...`
- [ ] `© Wroclaw University of Technology` NOT extracted as affiliation
- [ ] Author surnames normalized to Title Case (not ALL-CAPS)
- [ ] `## 1. Introduction` in `{slug}-main.md`
- [ ] `## References` in `{slug}-reference.md`
- [ ] `meta.json` populated

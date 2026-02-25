#!/usr/bin/env python3
"""
extract_figures.py — Academic paper figure/table extractor

Usage:
  python extract_figures.py <input.pdf> <output_dir>          # main article
  python extract_figures.py <input.pdf> <output_dir> --si     # Supplementary Information

Algorithm:
1. Scan all pages for caption blocks using PyMuPDF text extraction
   - Main:  "Figure N." / "Table N."
   - SI:    "Fig. SN." / "Table SN."  (abbreviation + S-prefix)
2. Use caption Y-coordinates to determine figure boundaries:
   - Top boundary: previous caption bottom (or page content start)
     Main: dashed vector separator lines (get_drawings) take precedence
     SI:   "Supplementary Figure/Table/Note" section title headers are skipped
   - Bottom boundary: current caption top
     SI:   use last non-caption content block bottom if it overlaps caption top
           (fixes axis-label clipping when label and caption Y ranges overlap)
3. Render region at 4x zoom, then auto-trim via OpenCV:
   - Dark-bar removal (journal header bar on main article pages)
   - White-margin crop
   - Right-side column trim (handles single-column figures in two-column layout)
"""

import sys
import argparse
import os
import re
import json

try:
    import fitz  # pymupdf
except ImportError:
    sys.exit("ERROR: pymupdf not installed. Run: pip install pymupdf --break-system-packages")
try:
    import cv2
except ImportError:
    sys.exit("ERROR: opencv not installed. Run: pip install opencv-python-headless --break-system-packages")
import numpy as np

ZOOM = 4  # render resolution multiplier (4x ~= 300 dpi equivalent)

# ── Caption patterns ──────────────────────────────────────────────────────────

# Main article: "Figure 1." / "Table 2."
CAPTION_RE_MAIN = re.compile(r'^(Figure|Table)\s+(\d+)[\.\s]', re.IGNORECASE)

# SI: "Fig. S1." / "Figure S1." / "Table S1." -- number must be followed by
# a period, or whitespace + non-paren character (actual caption text).
# Excludes inline body references like "Figure S1 (a) shows..." where the
# number is immediately followed by a space then an open parenthesis.
CAPTION_RE_SI = re.compile(r'^(Fig(?:ure)?|Table)\.?\s+(S?\d+)(?:\.|\s+[^(\s])', re.IGNORECASE)

# SI section title headers to skip when determining figure top boundary
# Matches "Supplementary Figure/Table/Note ..." AND "S1./S2./S3. ..." style headers
SI_SECTION_RE = re.compile(
    r'^(?:Supplementary\s+(?:Figure|Table|Note|Text|Method|Discussion|Information)'
    r'|S\d+\.\s+\S)',
    re.IGNORECASE,
)


# ── Image trimming ────────────────────────────────────────────────────────────

def trim_whitespace(img, pad=10, white_thresh=245, dark_row_thresh=200):
    """
    Three-pass trim applied to every extracted region:

    Pass 1 — Dark-bar removal: strip rows from top where row_mean < dark_row_thresh.
             Removes the gray 'www.nature.com/scientificreports/' raster header bar
             on main article pages. SI files lack this bar; the pass exits cleanly.
    Pass 2 — White-margin crop: tight bounding box of pixels < white_thresh, + pad.
    Pass 3 — Right-side column trim: scan columns right-to-left; crop at first column
             where col.min() < 220. Handles figures occupying only the left half of a
             two-column page layout. Adds 12 px padding.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Pass 1: dark header rows at top
    top_start = 0
    for r in range(h):
        row_mean = float(gray[r].mean())
        if row_mean < dark_row_thresh:
            top_start = r + 1
        elif row_mean > white_thresh - 5:
            break

    # Pass 2: bounding box of non-white content
    sub = gray[top_start:, :]
    mask = sub < white_thresh
    coords = np.argwhere(mask)
    if len(coords) == 0:
        return None  # completely white/empty — caller should handle
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    y0 += top_start
    y1 += top_start

    # Pass 3: right-side column trim (applied to post-Pass-1 sub-image only)
    # Use the cropped sub-image (after header removal) to avoid the full-width
    # journal header bar (present in main article pages) from polluting the
    # column min check and preventing right-side trim.
    sub_for_right = gray[top_start:, :]
    right_end = x1
    for c in range(w - 1, x0, -1):
        if sub_for_right[:, c].min() < 220:
            right_end = c
            break
    x1 = min(right_end + 12, w - 1)

    return img[
        max(0, y0 - pad) : min(h, y1 + pad + 1),
        max(0, x0 - pad) : min(w, x1 + pad + 1),
    ]


# ── Page helpers ──────────────────────────────────────────────────────────────

def get_page_content_top(page):
    """
    Return the Y coordinate where actual content begins, skipping the
    journal header line (e.g. 'www.nature.com/scientificreports/').
    """
    header_bottom = 0
    for b in page.get_text("blocks"):
        text = b[4].strip()
        y_top, y_bot = b[1], b[3]
        if y_top < 40 and any(kw in text.lower() for kw in ["www.", "doi", "nature", "scientific", "journal"]):
            header_bottom = max(header_bottom, y_bot)
    return header_bottom + 2 if header_bottom > 0 else 10


def get_dashed_separator_y(page, above_y):
    """
    Return the Y of a dashed vector separator line (if any) on this page above
    'above_y'. Scientific Reports renders section dividers as dashed vector lines
    detectable via get_drawings() with non-empty dashes values.
    Returns None if no dashed line is found.
    """
    result = None
    for d in page.get_drawings():
        dashes = d.get("dashes")
        if dashes and str(dashes) != "[] 0":
            line_y = d["rect"].y0
            if line_y < above_y:
                if result is None or line_y > result:
                    result = line_y
    return result


def get_si_section_header_bottom(page, above_y):
    """
    Return the bottom Y of any 'Supplementary Figure/Table/Note ...' section
    title block on the page that sits above 'above_y'. These are text blocks
    (not raster bars) and must be excluded from figure region calculation.
    Returns 0 if none found.
    """
    bottom = 0
    for b in page.get_text("blocks"):
        text = b[4].strip()
        y_bot = b[3]
        if y_bot < above_y and SI_SECTION_RE.match(text):
            bottom = max(bottom, y_bot)
    return bottom


def get_last_content_bottom(page, caption_top_y, caption_re):
    """
    Return the bottom Y of the last non-caption content block whose Y range ends
    at or below caption_top_y + small tolerance. Used in SI to prevent axis label
    clipping when axis label and caption text blocks share overlapping Y ranges.
    """
    last_y = 0
    for b in page.get_text("blocks"):
        text = b[4].strip()
        y_bot = b[3]
        if caption_re.match(text):
            continue
        if SI_SECTION_RE.match(text):
            continue
        if y_bot <= caption_top_y + 5:
            last_y = max(last_y, y_bot)
    return last_y


# ── Caption detection ─────────────────────────────────────────────────────────

def find_all_captions(doc, si=False):
    """
    Scan every page for caption blocks matching the appropriate pattern.
    Returns list of dicts: {page, label, type, rect, caption_text}

    For SI files, the output label always receives an 's' prefix:
      "Fig. S1."  -> sfigure1
      "Table S2." -> stable2
      "Fig. 3."   -> sfigure3  (SI without S-prefix numbering)

    May return duplicate labels when the same caption string appears on multiple
    pages (e.g. in a TOC on page 1 and on its actual content page). Deduplication
    is handled by run() after extraction succeeds: a label is locked-in only when
    an actual image is successfully extracted, so a TOC hit that produces no
    image region will not block the real content page.
    """
    captions = []
    pattern = CAPTION_RE_SI if si else CAPTION_RE_MAIN

    for page_num in range(len(doc)):
        page = doc[page_num]

        # SI page 0 is always the cover/TOC page — skip caption detection entirely
        if si and page_num == 0:
            continue

        for b in page.get_text("blocks"):
            text = b[4].strip()
            m = pattern.match(text)
            if m:
                kind = m.group(1).lower()
                num = m.group(2)
                kind_norm = "table" if "table" in kind else "figure"

                if si:
                    num_clean = re.sub(r'^[Ss]', '', num) or num
                    label = f"s{kind_norm}{num_clean}"
                else:
                    label = f"{kind_norm}{num}"

                captions.append({
                    "page": page_num,
                    "label": label,
                    "type": kind_norm,
                    "rect": fitz.Rect(b[0], b[1], b[2], b[3]),
                    "caption_text": text,
                })
    return captions


# ── Region extraction ─────────────────────────────────────────────────────────

def extract_figure(doc, caption, prev_cap_bottom, mat, si=False):
    """
    Render the region above the caption (the actual figure/table image),
    trim whitespace, and return (img_array, caption_bottom_y).
    Returns None if the region is too small to be meaningful.

    Fallback for caption-above-table layout (SI only):
      Some SI tables place the title caption ABOVE the table body rather than
      below it (i.e. the standard figure layout is reversed). When the above-
      caption region is too small, we try to extract the region BELOW the
      caption instead, up to the next caption or page bottom.
    """
    page_num = caption["page"]
    page = doc[page_num]
    page_rect = page.rect
    cap_top_y = caption["rect"].y0
    cap_bot_y = caption["rect"].y1
    caption_re = CAPTION_RE_SI if si else CAPTION_RE_MAIN

    # ── Top boundary ──────────────────────────────────────────────────────────
    if prev_cap_bottom is not None:
        fig_top_y = prev_cap_bottom + 3
    else:
        fig_top_y = get_page_content_top(page)

    if si:
        # SI: push top boundary past any section title header text block
        header_bottom = get_si_section_header_bottom(page, cap_top_y)
        if header_bottom > fig_top_y:
            fig_top_y = header_bottom + 2

        # If body text (non-caption, non-header, non-empty) appears above the
        # figure, push the top boundary past it — but only when there is a
        # significant blank gap (> 30 pt) between the last text block and the
        # figure, indicating a clear text/figure boundary.
        # This also covers continuation pages where header_bottom == 0.
        scan_top = header_bottom if header_bottom > 0 else fig_top_y
        last_text_y = scan_top
        for b in page.get_text("blocks"):
            text = b[4].strip()
            y_top, y_bot = b[1], b[3]
            if y_top >= scan_top and y_bot < cap_top_y - 5:
                if not caption_re.match(text) and not SI_SECTION_RE.match(text) and text:
                    last_text_y = max(last_text_y, y_bot)
        # Apply only if there is a blank gap of > 30 pt after the last text
        if last_text_y > scan_top and (cap_top_y - last_text_y) > 30:
            fig_top_y = max(fig_top_y, last_text_y + 3)
    else:
        dashed_y = get_dashed_separator_y(page, cap_top_y)
        if dashed_y is not None and dashed_y > fig_top_y:
            fig_top_y = dashed_y + 2

    # ── Bottom boundary ───────────────────────────────────────────────────────
    if si:
        last_content_y = get_last_content_bottom(page, cap_top_y, caption_re)
        clip_bottom = max(last_content_y, cap_top_y) + 2
    else:
        clip_bottom = cap_top_y - 3

    clip = fitz.Rect(
        page_rect.x0 + 3,
        fig_top_y,
        page_rect.x1 - 3,
        clip_bottom,
    )

    if clip.height < 20 or clip.width < 20:
        img = None
    else:
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        img = trim_whitespace(img)
        # If trim left almost nothing (or entirely white), treat as empty
        if img is None or img.shape[0] < 20 or img.shape[1] < 20:
            img = None

    # ── Fallback: caption-above-body layout (SI tables) ───────────────────────
    # If the region above the caption is empty/too small, try the region BELOW.
    if img is None and si:
        all_caps_on_page = [
            b for b in page.get_text("blocks")
            if caption_re.match(b[4].strip()) and b[1] > cap_bot_y + 5
        ]
        if all_caps_on_page:
            next_cap_y = min(b[1] for b in all_caps_on_page)
            below_bottom = next_cap_y - 3
        else:
            below_bottom = page_rect.y1 - 5

        below_clip = fitz.Rect(
            page_rect.x0 + 3,
            cap_bot_y + 3,
            page_rect.x1 - 3,
            below_bottom,
        )
        if below_clip.height >= 20 and below_clip.width >= 20:
            pix = page.get_pixmap(matrix=mat, clip=below_clip)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            img = trim_whitespace(img)
            if img is None or img.shape[0] < 20 or img.shape[1] < 20:
                img = None

    if img is None:
        return None

    return img, caption["rect"].y1

def run(pdf_path, out_dir, si=False):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(ZOOM, ZOOM)
    mode = "SI" if si else "main article"
    print(f"Mode: {mode}  |  PDF: {pdf_path}")

    captions = find_all_captions(doc, si=si)
    if not captions:
        print("No Figure/Table captions detected.")
        return []

    manifest = []
    prev_cap_bottom_by_page = {}
    extracted_labels = set()  # dedup: label is locked in only after a successful extraction

    for cap in captions:
        page_num = cap["page"]
        label = cap["label"]

        # Skip if this label was already successfully extracted (handles TOC duplicates)
        if label in extracted_labels:
            print(f"  SKIP duplicate [{label}] on page {page_num + 1} (already extracted)")
            continue

        prev_bottom = prev_cap_bottom_by_page.get(page_num)
        result = extract_figure(doc, cap, prev_bottom, mat, si=si)
        if result is None:
            print(f"  SKIP {label} (region too small)  page {page_num + 1}")
            continue

        img, cap_bottom = result
        prev_cap_bottom_by_page[page_num] = cap_bottom
        extracted_labels.add(label)  # lock in label only now

        out_path = os.path.join(out_dir, f"{label}.png")
        cv2.imwrite(out_path, img)
        print(f"  {label}.png  {img.shape[1]}x{img.shape[0]}px")

        manifest.append({
            "label": label,
            "type": cap["type"],
            "path": out_path,
            "caption_text": cap["caption_text"],
        })

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n  manifest -> {manifest_path}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract figures/tables from a Scientific Reports PDF."
    )
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("out_dir", help="Output directory")
    parser.add_argument(
        "--si",
        action="store_true",
        help="Treat input as a Supplementary Information (SI) file",
    )
    args = parser.parse_args()
    run(args.pdf, args.out_dir, si=args.si)

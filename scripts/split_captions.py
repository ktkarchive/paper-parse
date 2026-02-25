#!/usr/bin/env python3
"""
split_captions.py — Step 3: Caption splitting for paper-unpack-scientificreports

Usage:
  python split_captions.py <input.md> <output_dir> [--slug SLUG] [--si]

Given a full-paper Markdown file (produced by Step 2), this script:
  1. Detects all caption blocks matching "**Figure N.**" / "**Table N.**"
     (main) or "**Fig. SN.**" / "**Table SN.**" (SI).
  2. Writes each caption to its own file:
       {slug}-figure{N}.md  /  {slug}-table{N}.md   (main)
       {slug}-sfigure{N}.md /  {slug}-stable{N}.md  (SI)
  3. Removes all caption blocks and image links from the source .md,
     writing the cleaned version back in place (or to --out-main if given).

Slug is inferred from the input filename if not provided via --slug.
"""

import sys
import argparse
import os
import re


# ── Caption patterns (Markdown bold format from Step 2) ───────────────────────

# Main article: **Figure 1.** ... or **Table 2.** ...
CAPTION_RE_MAIN = re.compile(
    r'^\*\*(Figure|Table)\s+(\d+)\.\*\*(.+?)(?=\n\n|\Z)',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# SI: **Fig. S1.** ... or **Table S2.** ...
CAPTION_RE_SI = re.compile(
    r'^\*\*(Fig(?:ure)?\.?\s+S?\d+|Table\s+S?\d+)\.\*\*(.+?)(?=\n\n|\Z)',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# Broader pattern used to locate any caption block line-by-line
CAPTION_LINE_MAIN = re.compile(r'^\*\*(Figure|Table)\s+(\d+)\.\*\*', re.IGNORECASE)
CAPTION_LINE_SI   = re.compile(r'^\*\*(Fig(?:ure)?\.?\s+(S?\d+)|Table\s+(S?\d+))\.\*\*', re.IGNORECASE)

IMAGE_LINK_RE = re.compile(r'!\[.*?\]\(.*?\)\n?')


def infer_slug(input_path):
    """Derive slug from filename by stripping known suffixes and extension."""
    base = os.path.basename(input_path)
    name = os.path.splitext(base)[0]
    for suffix in ["-main", "-header", "-SI", "-backmatter", "-reference"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def extract_captions_main(content):
    """
    Parse caption blocks from main article Markdown.
    Returns list of (label, caption_text) tuples and the cleaned content.
    Caption format expected: **Figure N.** followed by text until blank line.
    """
    captions = []
    cleaned_lines = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = CAPTION_LINE_MAIN.match(line)
        if m:
            kind = m.group(1).lower()
            num = m.group(2)
            kind_norm = "table" if kind == "table" else "figure"
            label = f"{kind_norm}{num}"
            # Collect multi-line caption until blank line
            cap_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != "":
                cap_lines.append(lines[i])
                i += 1
            caption_text = "\n".join(cap_lines)
            captions.append((label, kind_norm, caption_text))
            # Skip the blank line
            if i < len(lines) and lines[i].strip() == "":
                i += 1
        else:
            cleaned_lines.append(line)
            i += 1
    return captions, "\n".join(cleaned_lines)


def extract_captions_si(content):
    """
    Parse caption blocks from SI Markdown.
    Labels receive 's' prefix: sfigure1, stable2.
    """
    captions = []
    cleaned_lines = []
    lines = content.split("\n")
    i = 0
    # Normalise SI caption number: strip leading S/s
    num_re = re.compile(r'(Fig(?:ure)?\.?\s+|Table\s+)(S?)(\d+)', re.IGNORECASE)
    while i < len(lines):
        line = lines[i]
        m = CAPTION_LINE_SI.match(line)
        if m:
            # Extract kind and number from the full match
            header = m.group(1)
            nm = num_re.search(header)
            if nm:
                kind_raw = nm.group(1).lower().strip().rstrip(".")
                num = nm.group(3)
                kind_norm = "table" if "table" in kind_raw else "figure"
                label = f"s{kind_norm}{num}"
            else:
                label = "sfigure_unknown"
                kind_norm = "figure"

            cap_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != "":
                cap_lines.append(lines[i])
                i += 1
            caption_text = "\n".join(cap_lines)
            captions.append((label, kind_norm, caption_text))
            if i < len(lines) and lines[i].strip() == "":
                i += 1
        else:
            cleaned_lines.append(line)
            i += 1
    return captions, "\n".join(cleaned_lines)


def clean_image_links(content):
    """Remove all Markdown image links and collapse excess blank lines."""
    content = IMAGE_LINK_RE.sub("", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


def write_caption_file(label, kind_norm, caption_text, slug, out_dir, si):
    """Write a single caption to its .md file."""
    filename = f"{slug}-{label}.md"
    out_path = os.path.join(out_dir, filename)

    if si:
        # e.g. label = sfigure1 -> "Supplementary Figure 1"
        num = re.sub(r'^s(figure|table)', '', label)
        kind_display = "Figure" if "figure" in label else "Table"
        heading = f"Supplementary {kind_display} {num}"
    else:
        num = re.sub(r'^(figure|table)', '', label)
        kind_display = "Figure" if "figure" in label else "Table"
        heading = f"{kind_display} {num}"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {heading}\n\n")
        f.write(caption_text.strip() + "\n")

    return out_path


def run(input_md, out_dir, slug=None, si=False, out_main=None):
    os.makedirs(out_dir, exist_ok=True)
    if slug is None:
        slug = infer_slug(input_md)

    with open(input_md, encoding="utf-8") as f:
        content = f.read()

    if si:
        captions, cleaned = extract_captions_si(content)
    else:
        captions, cleaned = extract_captions_main(content)

    cleaned = clean_image_links(cleaned)

    # Write caption files
    for label, kind_norm, caption_text in captions:
        path = write_caption_file(label, kind_norm, caption_text, slug, out_dir, si)
        print(f"  {os.path.basename(path)}")

    # Write cleaned source .md
    dest = out_main if out_main else input_md
    with open(dest, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print(f"\n  Cleaned source -> {dest}")
    print(f"  {len(captions)} caption(s) extracted.")
    return captions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Split captions from a Scientific Reports Markdown file (Step 3)."
    )
    parser.add_argument("input_md", help="Input .md file (full paper, from Step 2)")
    parser.add_argument("out_dir", help="Output directory for caption .md files")
    parser.add_argument("--slug", help="Slug prefix for output files (inferred from filename if omitted)")
    parser.add_argument("--si", action="store_true", help="Process as Supplementary Information")
    parser.add_argument("--out-main", help="Write cleaned source .md here instead of modifying in place")
    args = parser.parse_args()
    run(args.input_md, args.out_dir, slug=args.slug, si=args.si, out_main=args.out_main)

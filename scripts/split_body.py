#!/usr/bin/env python3
"""
split_body.py — Step 4: Body split for paper-unpack-scientificreports (main article only)

Usage:
  python split_body.py <input.md> <output_dir> [--slug SLUG]

Given a caption-cleaned main article Markdown file (from Step 3), splits it
into up to four parts:

  {slug}-header.md      — Title, journal metadata, authors/affiliations
  {slug}-main.md        — Abstract through final body section (Conclusion/Summary)
  {slug}-reference.md   — Numbered reference list
  {slug}-backmatter.md  — Acknowledgements, Author Contributions, license
                          (omitted entirely if none of these sections are present)

Section boundaries are detected by heading keywords. The script is intentionally
lenient: if a boundary cannot be found, it falls back gracefully and notes the gap.

DO NOT run on SI files — SI files have no 4-part split (Pipeline B ends at Step 3).
"""

import sys
import argparse
import os
import re


# ── Section boundary keywords ─────────────────────────────────────────────────

# Marks the start of the abstract / body (end of header)
ABSTRACT_RE = re.compile(r'^#+\s*Abstract\b', re.IGNORECASE)

# Marks the start of the references section
REFERENCE_RE = re.compile(r'^#+\s*References?\b', re.IGNORECASE)

# Marks the start of backmatter sections
BACKMATTER_RE = re.compile(
    r'^#+\s*(Acknowledgements?|Acknowledgments?|Author\s+Contributions?'
    r'|Data\s+Availability|Competing\s+Interests?|Additional\s+Information'
    r'|Ethics\s+Declaration|Consent|Funding)',
    re.IGNORECASE,
)

IMAGE_LINK_RE = re.compile(r'!\[.*?\]\(.*?\)\n?')


def infer_slug(input_path):
    base = os.path.basename(input_path)
    name = os.path.splitext(base)[0]
    for suffix in ["-main", "-header", "-SI", "-backmatter", "-reference"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def clean_image_links(content):
    content = IMAGE_LINK_RE.sub("", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


def find_boundary(lines, pattern, start=0):
    """Return the line index of the first match of pattern at or after start."""
    for i in range(start, len(lines)):
        if pattern.match(lines[i]):
            return i
    return None


def find_first_backmatter(lines, start=0):
    """Return the line index of the first backmatter heading at or after start."""
    for i in range(start, len(lines)):
        if BACKMATTER_RE.match(lines[i]):
            return i
    return None


def run(input_md, out_dir, slug=None):
    os.makedirs(out_dir, exist_ok=True)
    if slug is None:
        slug = infer_slug(input_md)

    with open(input_md, encoding="utf-8") as f:
        content = f.read()

    content = clean_image_links(content)
    lines = content.split("\n")

    # ── Locate boundaries ──────────────────────────────────────────────────────
    abstract_idx   = find_boundary(lines, ABSTRACT_RE)
    reference_idx  = find_boundary(lines, REFERENCE_RE)
    backmatter_idx = find_first_backmatter(lines)

    # Fallback: if no explicit Abstract heading, header ends at first blank line
    # after a title-like block (first few lines)
    if abstract_idx is None:
        # Treat everything before the first major section as header
        for i, line in enumerate(lines):
            if i > 0 and re.match(r'^#+\s+\S', line) and i > 3:
                abstract_idx = i
                break
        if abstract_idx is None:
            abstract_idx = 0
        print(f"  WARNING: No 'Abstract' heading found; header/body split at line {abstract_idx}.")

    if reference_idx is None:
        print("  WARNING: No 'References' heading found; reference section will be empty.")

    # Backmatter may legitimately be absent
    if backmatter_idx is None:
        print("  NOTE: No backmatter sections found; {slug}-backmatter.md will not be created.")

    # ── Slice content ──────────────────────────────────────────────────────────
    # Header: lines 0 .. abstract_idx (exclusive)
    header_lines = lines[:abstract_idx]

    # Main body: abstract_idx .. reference_idx (or backmatter_idx if no refs)
    body_end = reference_idx if reference_idx is not None else backmatter_idx
    if body_end is None:
        body_end = len(lines)
    main_lines = lines[abstract_idx:body_end]

    # References: reference_idx .. backmatter_idx (or end)
    if reference_idx is not None:
        ref_end = backmatter_idx if backmatter_idx is not None else len(lines)
        reference_lines = lines[reference_idx:ref_end]
    else:
        reference_lines = []

    # Backmatter
    if backmatter_idx is not None:
        backmatter_lines = lines[backmatter_idx:]
    else:
        backmatter_lines = []

    def write_part(name, part_lines):
        text = clean_image_links("\n".join(part_lines))
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  {name}  ({len(part_lines)} lines)")
        return path

    write_part(f"{slug}-header.md",    header_lines)
    write_part(f"{slug}-main.md",      main_lines)
    write_part(f"{slug}-reference.md", reference_lines)
    if backmatter_lines:
        write_part(f"{slug}-backmatter.md", backmatter_lines)
    else:
        print(f"  {slug}-backmatter.md  SKIPPED (no backmatter content)")

    print(f"\n  Split complete -> {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Split main article body into 4 parts (Step 4). Main article only — do not run on SI files."
    )
    parser.add_argument("input_md", help="Caption-cleaned main article .md (from Step 3)")
    parser.add_argument("out_dir", help="Output directory")
    parser.add_argument("--slug", help="Slug prefix (inferred from filename if omitted)")
    args = parser.parse_args()
    run(args.input_md, args.out_dir, slug=args.slug)

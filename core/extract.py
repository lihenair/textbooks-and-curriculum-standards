#!/usr/bin/env python3
"""把 PDF 按页抽出，再用章节标题切开。

    python3 core/extract.py 教材.pdf --out work/raw/chem-bx1
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CHAPTER_RE = re.compile(r"^第[0-9一二三四五六七八九十百零〇两]+章[^\n]*")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抽出 PDF 正文并按章切开")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        print(f"找不到 PDF：{args.pdf}", file=sys.stderr)
        return 2
    try:
        pages = extract_pages(args.pdf)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_extract(args.out, pages)
    print(f"已写入 {args.out}（{len(pages)} 页）")
    return 0


def extract_pages(pdf: Path) -> list[str]:
    try:
        import fitz
    except ImportError:
        fitz = None
    if fitz is not None:
        document = fitz.open(pdf)
        return [page.get_text() or "" for page in document]
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("需要 PyMuPDF 或 pypdf") from exc
    reader = PdfReader(str(pdf))
    return [page.extract_text() or "" for page in reader.pages]


def write_extract(out: Path, pages: list[str]) -> None:
    page_dir = out / "pages"
    chapter_dir = out / "chapters"
    page_dir.mkdir(parents=True, exist_ok=True)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    toc: list[str] = []
    chapters: list[tuple[str, int, list[str]]] = []
    current_title = ""
    current_start = 1
    current_lines: list[str] = []
    for index, text in enumerate(pages, 1):
        body = text.replace("\x00", "").strip()
        page_path = page_dir / f"p{index:03d}.txt"
        if body:
            page_path.write_text(f"第 {index} 页\n\n{body}\n", encoding="utf-8")
        else:
            page_path.write_text(f"第 {index} 页\n\n（无文本，需人工补页码）\n", encoding="utf-8")
            toc.append(f"第 {index} 页\t（无文本，需人工补页码）")
        for line in body.splitlines():
            heading = CHAPTER_RE.match(line.strip())
            if not heading:
                if current_title:
                    current_lines.append(line)
                continue
            if current_title:
                chapters.append((current_title, current_start, current_lines))
            current_title = heading.group(0).strip()
            current_start = index
            current_lines = [line]
            toc.append(f"第 {index} 页\t{current_title}")
        if current_title and body and not any(CHAPTER_RE.match(line.strip()) for line in body.splitlines()):
            current_lines.append("")
    if current_title:
        chapters.append((current_title, current_start, current_lines))
    if not chapters and pages:
        (chapter_dir / "unsectioned.txt").write_text(
            "\n".join(page.strip() for page in pages if page.strip()) + "\n",
            encoding="utf-8",
        )
        toc.append("未识别到章标题，全文在 chapters/unsectioned.txt，请人工核对。")
    for number, (title, _start, lines) in enumerate(chapters, 1):
        safe = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-") or f"ch{number:02d}"
        (chapter_dir / f"{number:02d}-{safe}.txt").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    (out / "toc.txt").write_text("\n".join(toc) + ("\n" if toc else ""), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

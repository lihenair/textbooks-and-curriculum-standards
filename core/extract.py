#!/usr/bin/env python3
"""把 PDF 按页抽出，再用章节标题切开。

    python3 core/extract.py 教材.pdf --out work/raw/chem-bx1
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CHAPTER_RE = re.compile(r"^第\s*([0-9一二三四五六七八九十百零〇两]+)\s*章([^\n]*)")

# 目录点线：三个以上句点（中间可夹空格，兼容 ". . . ." 与 "..."）、全角句点串或省略号
LEADER_RE = re.compile(r"(?:\.\s*){4,}|(?:．\s*){4,}|……")


def _is_toc_leader(line: str) -> bool:
    """目录条目行：带点线且行尾是页码。正文引语里的省略号不以页码结尾，不会命中。"""
    return bool(LEADER_RE.search(line)) and bool(re.search(r"\d+\s*$", line))


def _empty_run_note(start: int, end: int) -> str:
    if start == end:
        return f"第 {start} 页\t（无文本，需人工补页码）"
    return f"第 {start}-{end} 页\t（无文本，需人工补页码，共 {end - start + 1} 页）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抽出 PDF 正文并按章切开")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--render-pages", type=str, default=None,
                        help="把指定 PDF 页渲染成 PNG 供图表核对（如 24-27,30）；只渲染不抽文本")
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        print(f"找不到 PDF：{args.pdf}", file=sys.stderr)
        return 2
    if args.render_pages:
        return render_pages(args.pdf, args.out, args.render_pages)
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


_CN_DIGITS = {"零": 0, "〇": 0, "两": 2, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(text: str) -> int:
    """解析一到九十九的中文数字；阿拉伯数字直接转。解析不了返回 0。"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text or any(ch not in _CN_DIGITS and ch != "十" for ch in text):
        return 0
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CN_DIGITS.get(text, 0)


def write_extract(out: Path, pages: list[str]) -> None:
    page_dir = out / "pages"
    chapter_dir = out / "chapters"
    page_dir.mkdir(parents=True, exist_ok=True)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    toc: list[str] = []
    chapters: list[tuple[str, int, list[str]]] = []
    current_title = ""
    current_numeral = ""
    current_start = 1
    current_lines: list[str] = []
    empty_run_start: int | None = None
    for index, text in enumerate(pages, 1):
        body = text.replace("\x00", "").strip()
        page_path = page_dir / f"p{index:03d}.txt"
        if body:
            page_path.write_text(f"第 {index} 页\n\n{body}\n", encoding="utf-8")
            if empty_run_start is not None:
                toc.append(_empty_run_note(empty_run_start, index - 1))
                empty_run_start = None
        else:
            page_path.write_text(f"第 {index} 页\n\n（无文本，需人工补页码）\n", encoding="utf-8")
            if empty_run_start is None:
                empty_run_start = index
            continue
        lines = body.splitlines()
        headings = [line.strip() for line in lines if CHAPTER_RE.match(line.strip())]
        leader_count = sum(1 for line in lines if _is_toc_leader(line.strip()))
        if leader_count >= 3 or len({CHAPTER_RE.match(h).group(1) for h in headings}) >= 2:
            # 目录页（点线密集）或章目汇总页（同页多个不同章号）：
            # 本页的章标题全是目录条目，不当章首页；正文照常归入当前章。
            if current_title:
                current_lines.extend(lines)
                current_lines.append("")
            continue
        for line in lines:
            heading = CHAPTER_RE.match(line.strip())
            if not heading:
                if current_title:
                    current_lines.append(line)
                continue
            stripped = line.strip()
            if "..." in stripped or "．．" in stripped:
                continue
            if re.search(r"章\s*第", stripped):
                continue
            numeral = heading.group(1)
            if current_numeral == numeral:
                continue
            value = cn_to_int(numeral)
            previous = cn_to_int(current_numeral)
            if previous and value != previous + 1:
                toc.append(f"第 {index} 页\t（跳过，疑似页眉或引文）{stripped}")
                continue
            if current_title:
                chapters.append((current_title, current_start, current_lines))
            current_numeral = numeral
            current_title = stripped
            current_start = index
            current_lines = [line]
            toc.append(f"第 {index} 页\t{current_title}")
        if current_title and not headings:
            current_lines.append("")
    if empty_run_start is not None:
        toc.append(_empty_run_note(empty_run_start, len(pages)))
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



def render_pages(pdf: Path, out: Path, spec: str) -> int:
    """把 PDF 页渲染成 PNG，供人工和读图核对图表数据。页码是 PDF 页码。"""
    try:
        import fitz
    except ImportError:
        print("渲染需要 PyMuPDF：pip install pymupdf", file=sys.stderr)
        return 2
    wanted = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            wanted.extend(range(int(lo), int(hi) + 1))
        elif part:
            wanted.append(int(part))
    img_dir = Path(out) / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf)
    saved = 0
    for n in wanted:
        if not 1 <= n <= len(document):
            print(f"跳过越界页 {n}", file=sys.stderr)
            continue
        pix = document[n - 1].get_pixmap(dpi=150)
        pix.save(img_dir / f"p{n:03d}.png")
        saved += 1
    print(f"已渲染 {saved} 页到 {img_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

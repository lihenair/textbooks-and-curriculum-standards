#!/usr/bin/env python3
"""对无文本层的扫描书做全书 OCR，填充 pages/*.txt 并按 toc.txt 切 chapters/*.txt。

    .venv/bin/python scripts/ocr_fill.py work/raw/生物/extensions/陈阅增普通生物学-第3版

前置：该书目录已人工核对并写入 toc.txt（每行"第 N 页\\t标题"，PDF 页码；【篇】行忽略）。
PDF 原件、img/ 渲染图、toc.txt 一律不动；只重写 pages/*.txt 的占位内容。
OCR 文本仅供检索定位，引用以渲染图为准（macOS Vision，中文识别有少量错字、双栏偶有粘连）。
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz
from PIL import Image
from ocrmac import ocrmac

_local = threading.local()

TOC_LINE_RE = re.compile(r"^第 (\d+) 页\t(.+)$")


def parse_toc(book: Path) -> list[tuple[int, str]]:
    """读人工核对的 toc.txt，返回 (PDF 起始页, 标题)；注释与【篇】行忽略。"""
    toc_path = book / "toc.txt"
    if not toc_path.is_file():
        raise SystemExit(f"缺 {toc_path}：扫描书必须先人工核对目录再 OCR")
    entries = []
    for line in toc_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.startswith("【"):
            continue
        matched = TOC_LINE_RE.match(line)
        if matched:
            title = re.sub(r"（印刷页 \d+）$", "", matched.group(2)).strip()
            entries.append((int(matched.group(1)), title))
    if not entries:
        raise SystemExit(f"{toc_path} 里没有可用的章条目")
    return entries


def ocr_page(pdf_path: Path, n: int) -> str:
    """渲染第 n 页（1 基）并 OCR，按坐标重排为行。线程各自持有 fitz 文档。

    双栏页（左右各半页都有足够条目）先左栏后右栏，避免逐行交错。
    """
    doc = getattr(_local, "doc", None)
    if doc is None:
        doc = _local.doc = fitz.open(pdf_path)
    pix = doc[n - 1].get_pixmap(dpi=150)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    results = ocrmac.OCR(image, language_preference=["zh-Hans"]).recognize()
    items = [((r[2][0] + r[2][2] / 2), r[2][1], r[0]) for r in results]
    left = [t for t in items if t[0] < 0.5]
    right = [t for t in items if t[0] >= 0.5]
    if len(items) >= 15 and len(left) >= 5 and len(right) >= 5:
        columns = [sorted(left, key=lambda t: -t[1]), sorted(right, key=lambda t: -t[1])]
    else:
        columns = [sorted(items, key=lambda t: (-t[1], t[0]))]
    out: list[str] = []
    for column in columns:
        lines: list[list] = []
        for _, y, text in column:
            if lines and abs(lines[-1][0] - y) < 0.012:
                lines[-1][1].append(text)
            else:
                lines.append([y, [text]])
        out.extend("".join(parts) for _, parts in lines)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描书全书 OCR 填充 pages/ 并切 chapters/")
    parser.add_argument("book_dir", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)

    book = args.book_dir
    pdfs = sorted(book.glob("*.pdf"))
    if len(pdfs) != 1:
        print(f"目录里应恰有一个 PDF，找到 {[p.name for p in pdfs]}", file=sys.stderr)
        return 2
    pdf_path = pdfs[0]
    pages_dir = book / "pages"
    total = len(fitz.open(pdf_path))
    entries = parse_toc(book)
    failed: list[int] = []

    def work(n: int) -> int:
        try:
            text = ocr_page(pdf_path, n)
        except Exception as exc:  # noqa: BLE001 —— 单页失败不拖垮全书
            print(f"p{n:03d} OCR 失败：{exc}", file=sys.stderr)
            failed.append(n)
            text = ""
        content = text.strip() or "（无文本，需人工补页码）"
        (pages_dir / f"p{n:03d}.txt").write_text(f"第 {n} 页\n\n{content}\n", encoding="utf-8")
        return n

    done = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(work, n) for n in range(1, total + 1)]
        for fut in as_completed(futures):
            done += 1
            if done % 25 == 0 or done == total:
                print(f"[{done}/{total}]", flush=True)

    # 按 toc.txt 的章起始页切章；第一章之前的前言/目录单独成 00 文件
    boundaries = [(1, entries[0][0] - 1, "00-前言与目录")]
    for i, (start, title) in enumerate(entries, 1):
        end = entries[i][0] - 1 if i < len(entries) else total
        boundaries.append((start, end, f"{i:02d}-{title}"))
    for start, end, name in boundaries:
        if end < start:
            continue
        parts = []
        for n in range(start, end + 1):
            body = (pages_dir / f"p{n:03d}.txt").read_text(encoding="utf-8").split("\n\n", 1)[1].strip()
            if body and "需人工补页码" not in body:
                parts.append(body)
        safe = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name).strip("-")
        (book / "chapters" / f"{safe}.txt").write_text("\n\n".join(parts) + "\n", encoding="utf-8")

    print(f"完成：{total} 页，失败 {len(failed)} 页 {failed[:20]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

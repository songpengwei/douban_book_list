"""
Convert a Douban wish JSON file into a styled Markdown table and download cover images.

Example:
    python build_markdown_from_json.py qtmuniao_wish.json --output books.md --columns 3

The generated Markdown uses an HTML <table> for better styling in Hexo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional

import hashlib
import random
import time

import requests

DEFAULT_PRIMARY = "#1f6feb"
DEFAULT_BG = "#0d1117"
DEFAULT_CARD_BG = "#161b22"
DEFAULT_TEXT = "#e6edf3"
DEFAULT_MUTED = "#8b949e"


@dataclass
class Book:
    title: str
    douban_url: str
    cover_image: Optional[str]
    authors: List[str]
    publisher: Optional[str]
    publish_date: Optional[str]
    rating: Optional[float]
    rating_count: Optional[int]
    summary: Optional[str]
    raw_pub: Optional[str]
    book_id: Optional[str]
    added_at: Optional[str]


def load_books(json_path: Path) -> List[Book]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    books: List[Book] = []
    for item in data:
        books.append(
            Book(
                title=item.get("title", ""),
                douban_url=item.get("douban_url", ""),
                cover_image=item.get("cover_image"),
                authors=item.get("authors") or [],
                publisher=item.get("publisher"),
                publish_date=item.get("publish_date"),
                rating=item.get("rating"),
                rating_count=item.get("rating_count"),
                summary=item.get("summary"),
                raw_pub=item.get("raw_pub"),
                book_id=item.get("book_id"),
                added_at=item.get("added_at"),
            )
        )
    return books


def safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return name or "cover"


def expected_cover_path(book: Book, img_dir: Path) -> Path:
    ext = os.path.splitext((book.cover_image or "").split("?")[0])[1] or ".jpg"
    identifier = (
        book.book_id
        or (hashlib.md5(book.douban_url.encode("utf-8")).hexdigest()[:10] if book.douban_url else None)
        or book.title
    )
    filename = safe_filename(identifier or "cover") + ext
    return img_dir / filename


def attach_existing_images(books: List[Book], img_dir: Path) -> int:
    """Attach existing local covers if present; returns how many matched."""
    if not img_dir.exists():
        return 0
    matched = 0
    for book in books:
        dest = expected_cover_path(book, img_dir)
        if dest.exists():
            book.cover_image = str(dest)
            matched += 1
    return matched


def download_images(books: List[Book], img_dir: Path, timeout: int = 15, max_retries: int = 3) -> List[Book]:
    """Download cover images; returns list of books that failed to download."""
    img_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }
    )

    failures: List[Book] = []

    for book in books:
        if not book.cover_image:
            book.cover_image = None
            failures.append(book)
            continue

        dest = expected_cover_path(book, img_dir)

        if dest.exists():
            book.cover_image = str(dest)
            continue

        success = False
        last_err = None
        for _ in range(max_retries):
            headers = {}
            if book.douban_url:
                headers["Referer"] = book.douban_url
            time.sleep(random.uniform(0.8, 1.6))  # slow down to mimic human requests
            try:
                resp = session.get(book.cover_image, timeout=timeout, stream=True, headers=headers)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                book.cover_image = str(dest)
                success = True
                break
            except Exception as exc:  # pragma: no cover - network dependent
                last_err = exc
                continue
        if not success:
            print(f"Failed to download {book.cover_image}: {last_err}")  # type: ignore[name-defined]
            book.cover_image = None
            failures.append(book)

    return failures


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def render_cell(book: Book, palette: dict) -> str:
    meta = book.raw_pub or ""
    meta = truncate(meta, 160) if meta else "暂无信息"

    cover_src = book.cover_image or ""
    if cover_src.startswith(("http://", "https://")):
        cover_src = ""  # enforce local images only
    if cover_src and not cover_src.startswith(("/", "http://", "https://")):
        cover_src = cover_src.replace("\\", "/")

    return textwrap.dedent(
        f"""
        <div style="background:{palette['card_bg']}; border:1px solid {palette['primary']}30; border-radius:12px; padding:12px; color:{palette['text']}; font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; box-shadow:0 8px 24px -12px #000; text-align:center;">
          <div style="margin-bottom:10px;">
            {'<a href="' + book.douban_url + '" target="_blank" rel="noopener noreferrer"><img src="' + cover_src + '" alt="cover" style="width:160px; height:220px; object-fit:cover; border-radius:10px; border:1px solid '+palette['primary']+'20;" /></a>' if cover_src else '<div style="width:160px; height:220px; margin:0 auto; background:'+palette['primary']+'20; border-radius:10px;"></div>'}
          </div>
          <div style="font-size:13px; color:{palette['muted']}; line-height:1.5;">{meta}</div>
        </div>
        """
    ).strip()


def build_table(books: List[Book], columns: int, palette: dict) -> str:
    rows = []
    for i in range(0, len(books), columns):
        chunk = books[i : i + columns]
        cells = "".join(f"<td style='padding:10px; vertical-align:top;'>{render_cell(book, palette)}</td>" for book in chunk)
        rows.append(f"<tr>{cells}</tr>")
    col_width = f"{100/columns:.2f}%"
    return textwrap.dedent(
        f"""
        <table style="width:100%; border-collapse:separate; border-spacing:0 10px; background:{palette['bg']};">
          <colgroup>
            {''.join(f"<col style='width:{col_width};' />" for _ in range(columns))}
          </colgroup>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        """
    ).strip()


def prepare_page_books(books: List[Book], page_dir: Path) -> List[Book]:
    """Return copies of books with cover paths relativized to the page directory."""
    prepared = []
    for b in books:
        cover = b.cover_image
        rel_cover = None
        if cover and not str(cover).startswith(("http://", "https://")):
            p = Path(cover)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.exists():
                rel_cover = os.path.relpath(p, page_dir).replace(os.sep, "/")
        prepared.append(replace(b, cover_image=rel_cover))
    return prepared


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Markdown table and download covers from Douban wish JSON.")
    parser.add_argument("json_path", help="Path to JSON generated by fetch_douban_wish.py")
    parser.add_argument("--output", "-o", default=None, help="Output Markdown path, default <json_basename>.md")
    parser.add_argument("--img-dir", default="img", help="Directory to store downloaded covers")
    parser.add_argument("--columns", type=int, default=3, help="Number of columns in the table")
    parser.add_argument("--rows-per-page", type=int, default=10, help="Rows per Markdown page before splitting")
    parser.add_argument("--primary-color", default=DEFAULT_PRIMARY, help="Primary accent color")
    parser.add_argument("--bg-color", default=DEFAULT_BG, help="Page background color")
    parser.add_argument("--card-bg", default=DEFAULT_CARD_BG, help="Card background color")
    parser.add_argument("--text-color", default=DEFAULT_TEXT, help="Text color")
    parser.add_argument("--muted-color", default=DEFAULT_MUTED, help="Muted text color")
    parser.add_argument("--skip-download", action="store_true", help="Skip downloading images (uses original URLs)")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    output_path = Path(args.output or (json_path.stem + ".md"))
    img_dir = Path(args.img_dir)

    books = load_books(json_path)

    # Reuse existing covers when directory already has images.
    reused = attach_existing_images(books, img_dir)
    if reused:
        file_count = sum(1 for p in img_dir.iterdir() if p.is_file())
        print(f"Reused {reused} existing cover(s) from {img_dir}")
        if reused > file_count:
            print(f"Note: reuse count ({reused}) exceeds actual files in dir ({file_count}); some filenames may map to the same file.")

    if not args.skip_download:
        missing_local = [
            b
            for b in books
            if not (b.cover_image and not str(b.cover_image).startswith(("http://", "https://")) and Path(b.cover_image).exists())
        ]
        need_download = [b for b in missing_local if b.cover_image]
        failures = []
        if need_download:
            failures = download_images(need_download, img_dir)
        if failures:
            print(f"WARNING: {len(failures)} covers failed to download.")
            for b in failures:
                print(f" - {b.title} ({b.douban_url})")
        else:
            print(f"Downloaded covers for {len(need_download)} book(s).")
    else:
        missing_local = []
        if any(not (b.cover_image and not str(b.cover_image).startswith(("http://", "https://")) and Path(b.cover_image).exists()) for b in books):
            print("Skipped download; some covers missing locally and will render as placeholder.")

    palette = {
        "primary": args.primary_color,
        "bg": args.bg_color,
        "card_bg": args.card_bg,
        "text": args.text_color,
        "muted": args.muted_color,
    }
    columns = max(1, args.columns)
    rows_per_page = max(1, args.rows_per_page)

    page_size = columns * rows_per_page
    pages = []
    for i in range(0, len(books), page_size):
        subset = books[i : i + page_size]
        pages.append(subset)

    base_output = output_path
    saved_paths = []
    stem = base_output.stem
    suffix = base_output.suffix or ".md"
    for idx, subset in enumerate(pages, start=1):
        if idx == 1:
            out_path = base_output
        else:
            out_dir = base_output.with_name(f"{stem}_{idx}")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / ("index" + suffix)
        page_books = prepare_page_books(subset, out_path.parent)
        content = build_table(page_books, columns, palette)
        out_path.write_text(content, encoding="utf-8")
        saved_paths.append(out_path)

    print("Saved Markdown to:")
    for p in saved_paths:
        print(f" - {p}")

    local_count = sum(
        1 for b in books if b.cover_image and not str(b.cover_image).startswith(("http://", "https://")) and Path(b.cover_image).exists()
    )
    print(f"Local covers available: {local_count} / {len(books)}")
    if not args.skip_download:
        print(f"Images saved to {img_dir}")


if __name__ == "__main__":
    main()

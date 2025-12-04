"""
Fetch the "wish to read" list for a Douban user and save the book metadata.

Example:
    python fetch_douban_wish.py qtmuniao --output qtmuniao_wish.json

Requirements:
    pip install requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


PAGINATION_SIZE = 15  # Douban paginates wish lists 15 items per page.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
)


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


def fetch_page_html(session: requests.Session, user_id: str, start: int) -> Tuple[str, str]:
    url = f"https://book.douban.com/people/{user_id}/wish?start={start}"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text, url


def extract_book_id(url: str) -> Optional[str]:
    match = re.search(r"/subject/(\\d+)/", url)
    return match.group(1) if match else None


def parse_pub_info(pub_text: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    parts = [part.strip() for part in pub_text.split("/") if part.strip()]
    if not parts:
        return [], None, None

    # Heuristic: everything except the last two entries are authors.
    if len(parts) >= 3:
        authors = parts[:-2]
        publisher = parts[-2]
        publish_date = parts[-1]
        return authors, publisher, publish_date

    if len(parts) == 2:
        return [parts[0]], parts[1], None

    return [], parts[0], None


def parse_books(html: str) -> Tuple[List[Book], bool]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.subject-item")
    books: List[Book] = []

    for li in items:
        title_tag = li.select_one("h2 a")
        title = title_tag.get_text(strip=True) if title_tag else "未知标题"
        link = title_tag["href"].split("?")[0] if title_tag and title_tag.has_attr("href") else None

        cover_tag = li.select_one(".pic img")
        cover = cover_tag["src"] if cover_tag and cover_tag.has_attr("src") else None

        pub_tag = li.select_one(".pub")
        pub_text = pub_tag.get_text(" ", strip=True) if pub_tag else ""
        authors, publisher, publish_date = parse_pub_info(pub_text)

        rating_tag = li.select_one(".rating-info .rating_nums, .rating_nums")
        rating = float(rating_tag.get_text(strip=True)) if rating_tag else None

        rating_count_tag = li.select_one(".rating-info .pl, .rating_people .pl")
        rating_count = None
        if rating_count_tag:
            match = re.search(r"(\\d+)", rating_count_tag.get_text())
            rating_count = int(match.group(1)) if match else None

        summary = None
        for p in li.select("p"):
            classes = p.get("class") or []
            if "rating-info" in classes or "pub" in classes or "subject-abstract" in classes:
                continue
            text = p.get_text(" ", strip=True)
            if text:
                summary = text
                break

        added_at_tag = li.select_one(".short-note .date, .ft .date, .oper-date, span.date")
        added_at = added_at_tag.get_text(strip=True) if added_at_tag else None

        books.append(
            Book(
                title=title,
                douban_url=link or "",
                cover_image=cover,
                authors=authors,
                publisher=publisher,
                publish_date=publish_date,
                rating=rating,
                rating_count=rating_count,
                summary=summary,
                raw_pub=pub_text or None,
                book_id=extract_book_id(link or "") if link else None,
                added_at=added_at,
            )
        )

    has_next = bool(soup.select_one("span.next a"))
    return books, has_next


def fetch_wish_list(user_id: str, max_pages: Optional[int] = None) -> Iterable[Book]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    start = 0
    page = 0
    while True:
        html, url = fetch_page_html(session, user_id, start)
        page += 1
        page_books, has_next = parse_books(html)

        if not page_books:
            break

        for book in page_books:
            yield book

        if max_pages and page >= max_pages:
            break
        if not has_next:
            break

        start += PAGINATION_SIZE


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Douban wish-to-read list for a user.")
    parser.add_argument("user_id", help="Douban account id, e.g. qtmuniao")
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to save JSON data. Defaults to douban_wish_<user_id>.json",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to fetch (15 books per page).",
    )
    args = parser.parse_args()

    output_path = args.output or f"douban_wish_{args.user_id}.json"
    books = list(fetch_wish_list(args.user_id, max_pages=args.max_pages))

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([asdict(book) for book in books], f, ensure_ascii=False, indent=2)

    print(f"Saved {len(books)} books to {output_path}")


if __name__ == "__main__":
    main()

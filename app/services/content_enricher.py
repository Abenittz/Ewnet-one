import re
from typing import Any
from bs4 import BeautifulSoup, NavigableString

# Recognized English and Amharic Bible books and abbreviations (lowercase)
KNOWN_BIBLE_BOOKS = {
    # English Old Testament
    "genesis", "gen", "exodus", "ex", "exod", "leviticus", "lev", "numbers", "num",
    "deuteronomy", "deut", "joshua", "josh", "judges", "judg", "ruth", "samuel", "sam",
    "kings", "kgs", "chronicles", "chron", "ezra", "nehemiah", "neh", "esther", "est",
    "job", "psalms", "psalm", "ps", "proverbs", "prov", "pr", "ecclesiastes", "eccl",
    "song of solomon", "song of songs", "song", "isaiah", "isa", "jeremiah", "jer",
    "lamentations", "lam", "ezekiel", "ezek", "daniel", "dan", "hosea", "hos", "joel",
    "amos", "obadiah", "obad", "jonah", "jon", "micah", "mic", "nahum", "nah",
    "habakkuk", "hab", "zephaniah", "zeph", "haggai", "hag", "zechariah", "zech",
    "malachi", "mal",
    # English New Testament
    "matthew", "matt", "mat", "mark", "mk", "luke", "lk", "luk", "john", "jn", "joh",
    "acts", "act", "romans", "rom", "corinthians", "cor", "galatians", "gal",
    "ephesians", "eph", "philippians", "phil", "colossians", "col", "thessalonians",
    "thess", "timothy", "tim", "titus", "tit", "philemon", "phlm", "hebrews", "heb",
    "james", "jas", "peter", "pet", "jude", "jud", "revelation", "rev",
    # Amharic Old Testament
    "ዘፍጥረት", "ዘፍ", "ዘጸአት", "ዘጸ", "ዘሌዋውያን", "ዘሌ", "ዘኍልቍ", "ዘኍ", "ዘዳግም", "ዘዳ",
    "ኢያሱ", "መሳፍንት", "ሩት", "ሳሙኤል", "ሳሙ", "ነገሥት", "ነገ", "ዜና መዋዕል", "ዜና",
    "ዕዝራ", "ዕዝ", "ነህምያ", "ነህ", "አስቴር", "አስ", "ኢዮብ", "ኢዮ", "መዝሙር", "መዝ",
    "ምሳሌ", "ምሳ", "መክብብ", "መክ", "ማሕልየ", "ማሕልይ", "ኢሳይያስ", "ኢሳ", "ኤርምያስ", "ኤር",
    "ሰቆቃወ", "ሕዝቅኤል", "ሕዝ", "ዳንኤል", "ዳን", "ሆሴዕ", "ሆሴ", "ኢዩኤል", "ኢዩ",
    "አሞጽ", "አሞ", "አብድዩ", "አብ", "ዮናስ", "ዮና", "ሚክያስ", "ሚክ", "ናሆም", "ናሆ",
    "ዕንባቆም", "ዕን", "ሶፎንያስ", "ሶፎ", "ሐጌ", "ዘካርያስ", "ዘካ", "ሚልክያስ", "ሚል",
    # Amharic New Testament
    "ማቴዎስ", "ማቴ", "ማርቆስ", "ማር", "ሉቃስ", "ሉቃ", "ዮሐንስ", "ዮሐ", "የሐዋርያት",
    "ሐዋርያት", "ሐዋ", "ሮሜ", "ቆሮንቶስ", "ቆሮ", "ገላትያ", "ገላ", "ኤፌሶን", "ኤፌ",
    "ፊልጵስዩስ", "ፊል", "ቆላስይስ", "ቆላ", "ተሰሎንቄ", "ተሰ", "ጢሞቴዎስ", "ጢሞ",
    "ቲቶ", "ፊልሞና", "ዕብራውያን", "ዕብ", "ያዕቆብ", "ያዕ", "ጴጥሮስ", "ጴጥ",
    "ይሁዳ", "ይሁ", "ራእይ", "ራእ",
}

# Regex for detecting scripture patterns like "john 4:21-24", "2john3:6", "1 John 3:16", "2ዮሐ3:6", "ማቴ 5:3-12"
SCRIPTURE_REGEX = re.compile(
    r"\b(?:([1-3]|፩|፪|፫)\s*)?"
    r"([A-Za-z\u1200-\u137F]+)\s*"
    r"(\d+|[፩-፼]+)\s*[:፡]\s*(\d+|[፩-፼]+)(?:\s*[-–—]\s*(\d+|[፩-፼]+))?\b",
    re.IGNORECASE | re.UNICODE,
)

ETHIOPIC_NUMERALS = {
    "፩": 1, "፪": 2, "፫": 3, "፬": 4, "፭": 5, "፮": 6, "፯": 7, "፰": 8, "፱": 9,
    "፲": 10, "፳": 20, "፴": 30, "፵": 40, "፶": 50, "፷": 60, "፸": 70, "፹": 80, "፺": 90,
    "፻": 100, "፼": 10000,
}

TOC_MARKERS = re.compile(
    r"^\s*(?:table\s+of\s+contents|contents|content\s+menu|ማውጫ|ይዘት|የይዘት\s+ማውጫ|table\s+des\s+matières)\s*$",
    re.IGNORECASE | re.UNICODE,
)

READER_CSS_STYLES = """
<style class="ewnet-reader-styles">
.ewnet-chapter-container {
  max-width: 100%;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans Ethiopic', sans-serif;
  color: #1f2937;
}
.book-main-title {
  font-size: 2.5rem !important;
  font-weight: 800 !important;
  line-height: 1.2 !important;
  color: #111827 !important;
  margin-top: 2rem !important;
  margin-bottom: 1.5rem !important;
  letter-spacing: -0.025em !important;
  text-align: center !important;
}
.book-subtitle, .book-author {
  font-size: 1.25rem !important;
  font-weight: 500 !important;
  color: #4b5563 !important;
  text-align: center !important;
  margin-bottom: 2rem !important;
}
.chapter-title {
  font-size: 1.75rem !important;
  font-weight: 700 !important;
  line-height: 1.3 !important;
  color: #1f2937 !important;
  margin-top: 1.5rem !important;
  margin-bottom: 1rem !important;
  border-bottom: 1px solid #e5e7eb !important;
  padding-bottom: 0.5rem !important;
}
.chapter-subtitle, h3 {
  font-size: 1.35rem !important;
  font-weight: 600 !important;
  color: #374151 !important;
  margin-top: 1.25rem !important;
  margin-bottom: 0.75rem !important;
}
.book-paragraph, p {
  font-size: 1.05rem !important;
  line-height: 1.8 !important;
  margin-bottom: 1.15rem !important;
  color: #1f2937 !important;
}
.toc-container {
  background-color: #f9fafb !important;
  border: 1px solid #e5e7eb !important;
  border-radius: 8px !important;
  padding: 1.5rem !important;
  margin-bottom: 2rem !important;
}
.toc-title {
  font-size: 1.4rem !important;
  font-weight: 700 !important;
  margin-bottom: 1rem !important;
  color: #111827 !important;
}
.toc-link {
  color: #2563eb !important;
  text-decoration: none !important;
  font-weight: 500 !important;
  display: inline-block !important;
  margin-bottom: 0.4rem !important;
  transition: color 0.15s ease !important;
}
.toc-link:hover {
  color: #1d4ed8 !important;
  text-decoration: underline !important;
}
.scripture-ref {
  color: #2563eb !important;
  font-weight: 600 !important;
  text-decoration: underline !important;
  text-underline-offset: 3px !important;
  cursor: pointer !important;
  padding: 1px 3px !important;
  border-radius: 3px !important;
  background-color: rgba(37, 99, 235, 0.08) !important;
  transition: all 0.15s ease !important;
}
.scripture-ref:hover {
  color: #1d4ed8 !important;
  background-color: rgba(37, 99, 235, 0.16) !important;
}
</style>
"""


def parse_int_or_ethiopic(s: str | None) -> int | None:
    """Parse integer from ASCII digits or Ethiopic numerals (e.g. ፬ -> 4, ፳፩ -> 21)."""
    if not s:
        return None
    s = s.strip()
    if s.isascii() and s.isdigit():
        return int(s)

    val = 0
    sub = 0
    for ch in s:
        n = ETHIOPIC_NUMERALS.get(ch, 0)
        if n >= 100:
            sub = max(sub, 1) * n
            val += sub
            sub = 0
        else:
            sub += n
    res = val + sub
    return res if res > 0 else None


class ContentEnricher:
    """
    Enriches book chapters with:
    1. Scripture reference detection & linking ("john 4:21-24") with distinctive styling and database persistence.
    2. Table of Contents / Content Menu auto-linking to corresponding chapters.
    3. Distinct visual typography hierarchy (significantly larger first page title, chapter headers, body text).
    """

    def enrich_chapter(
        self,
        raw_html: str,
        chapter_index: int,
        *,
        book_title: str | None = None,
        author: str | None = None,
        chapter_titles: list[str] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Enrich HTML content and return (enriched_html, extracted_scripture_references).
        """
        if not raw_html:
            return raw_html, []

        soup = BeautifulSoup(raw_html, "html.parser")
        chapter_titles = chapter_titles or []

        # 1. Detect and link scripture references
        references = self._detect_and_link_scriptures(soup, chapter_index)

        # 2. Enhance content menu / TOC entries
        self._enhance_content_menu(soup, chapter_titles)

        # 3. Apply significant typography hierarchy
        self._apply_typography_hierarchy(
            soup,
            chapter_index=chapter_index,
            book_title=book_title,
            author=author,
        )

        # Wrap in container with id anchor if not present
        container = soup.find("div", class_="ewnet-chapter-container")
        if not container:
            body = soup.body or soup
            children = list(body.contents)
            new_container = soup.new_tag(
                "div",
                attrs={
                    "class": "ewnet-chapter-container",
                    "id": f"chapter-{chapter_index}",
                },
            )
            for child in children:
                new_container.append(child.extract())
            body.append(new_container)
        else:
            container["id"] = f"chapter-{chapter_index}"

        # Inject stylesheet at top
        if not soup.find("style", class_="ewnet-reader-styles"):
            style_soup = BeautifulSoup(READER_CSS_STYLES, "html.parser")
            first_element = soup.find()
            if first_element:
                first_element.insert_before(style_soup)
            else:
                soup.append(style_soup)

        enriched_html = str(soup)
        return enriched_html, references

    def _normalize_book_name(self, name: str) -> str:
        name = name.strip()
        for pfx in ["እንደ", "ስለ", "በ", "ከ", "ለ", "የ"]:
            if name.startswith(pfx) and len(name) > len(pfx) + 1:
                return name[len(pfx):]
        return name

    def _detect_and_link_scriptures(
        self,
        soup: BeautifulSoup,
        chapter_index: int,
    ) -> list[dict[str, Any]]:
        """Find scripture patterns in text nodes and convert them into styled anchor links."""
        extracted: list[dict[str, Any]] = []
        counter = 0

        # Traverse text nodes, skipping existing anchor tags and script/style
        text_nodes = [
            node for node in soup.find_all(string=True)
            if node.parent and node.parent.name not in ["a", "script", "style", "title", "head"]
        ]

        for node in text_nodes:
            text = str(node)
            matches = list(SCRIPTURE_REGEX.finditer(text))
            if not matches:
                continue

            # Validate matches against known Bible books
            valid_matches: list[tuple[Any, str]] = []
            for m in matches:
                prefix, book_part, ch_str, v_start_str, v_end_str = m.groups()
                full_book = f"{prefix} {book_part}".strip() if prefix else book_part
                full_lower = full_book.lower()
                part_lower = book_part.lower()

                norm_full = self._normalize_book_name(full_lower)
                norm_part = self._normalize_book_name(part_lower)

                detected_name = None
                if full_lower in KNOWN_BIBLE_BOOKS:
                    detected_name = full_book
                elif part_lower in KNOWN_BIBLE_BOOKS:
                    detected_name = f"{prefix} {book_part}".strip() if prefix else book_part
                elif norm_full in KNOWN_BIBLE_BOOKS:
                    norm_base = self._normalize_book_name(book_part)
                    detected_name = f"{prefix} {norm_base}".strip() if prefix else norm_base
                elif norm_part in KNOWN_BIBLE_BOOKS:
                    norm_base = self._normalize_book_name(book_part)
                    detected_name = f"{prefix} {norm_base}".strip() if prefix else norm_base

                if detected_name:
                    valid_matches.append((m, detected_name))

            if not valid_matches:
                continue

            # Rebuild text node with replacement <a> elements
            new_elements = []
            last_idx = 0

            for m, detected_name in valid_matches:
                start, end = m.span()
                if start > last_idx:
                    new_elements.append(NavigableString(text[last_idx:start]))

                prefix, book_part, ch_str, v_start_str, v_end_str = m.groups()
                raw_ref = m.group(0).strip()
                counter += 1
                anchor_id = f"ref-ch{chapter_index}-{counter}"

                ch_num = parse_int_or_ethiopic(ch_str)
                v_start = parse_int_or_ethiopic(v_start_str)
                v_end = parse_int_or_ethiopic(v_end_str)

                # Create clickable scripture reference link
                a_tag = soup.new_tag("a")
                a_tag["href"] = f"#{anchor_id}"
                a_tag["id"] = anchor_id
                a_tag["class"] = "scripture-ref"
                a_tag["data-reference"] = raw_ref
                a_tag["data-book"] = detected_name
                if ch_num is not None:
                    a_tag["data-chapter"] = str(ch_num)
                if v_start is not None:
                    a_tag["data-verse-start"] = str(v_start)
                if v_end is not None:
                    a_tag["data-verse-end"] = str(v_end)

                a_tag["style"] = (
                    "color: #2563eb; font-weight: 600; text-decoration: underline; "
                    "text-underline-offset: 3px; cursor: pointer; padding: 1px 3px; "
                    "border-radius: 3px; background-color: rgba(37, 99, 235, 0.08);"
                )
                a_tag["title"] = f"Scripture Reference: {raw_ref}"
                a_tag.string = raw_ref

                new_elements.append(a_tag)

                extracted.append({
                    "chapter_index": chapter_index,
                    "reference_text": raw_ref,
                    "book_name": detected_name,
                    "chapter_num": ch_num,
                    "verse_start": v_start,
                    "verse_end": v_end,
                    "anchor_id": anchor_id,
                })

                last_idx = end

            if last_idx < len(text):
                new_elements.append(NavigableString(text[last_idx:]))

            for el in new_elements:
                node.insert_before(el)
            node.extract()

        return extracted

    def _enhance_content_menu(
        self,
        soup: BeautifulSoup,
        chapter_titles: list[str],
    ) -> None:
        """Identify Table of Contents / Content Menu sections and link entries to chapters."""
        if not chapter_titles:
            return

        # Look for headings or paragraphs marking a Content Menu
        for el in soup.find_all(["h1", "h2", "h3", "p", "div"]):
            el_text = el.get_text(strip=True)
            if TOC_MARKERS.match(el_text):
                parent = el.parent or el
                if parent.name not in ["body", "html"]:
                    parent["class"] = parent.get("class", []) + ["toc-container"]

                # Link following items to chapters
                siblings = el.find_next_siblings()
                for sib in siblings:
                    sib_text = sib.get_text(strip=True)
                    # Check which chapter title matches
                    for idx, title in enumerate(chapter_titles):
                        # Clean title for matching (remove leading/trailing symbols)
                        clean_target = re.sub(r"^\s*(?:chapter|ምዕራፍ)\s*\d+[:.\s-]*", "", title, flags=re.IGNORECASE).strip()
                        if (
                            title.lower() in sib_text.lower()
                            or (clean_target and len(clean_target) > 3 and clean_target.lower() in sib_text.lower())
                            or f"chapter {idx + 1}" in sib_text.lower()
                            or f"ምዕራፍ {idx + 1}" in sib_text.lower()
                        ):
                            # Turn into or tag existing link
                            existing_a = sib.find("a")
                            if existing_a:
                                existing_a["href"] = f"#chapter-{idx}"
                                existing_a["data-chapter-index"] = str(idx)
                                existing_a["class"] = existing_a.get("class", []) + ["toc-link"]
                            else:
                                new_a = soup.new_tag("a")
                                new_a["href"] = f"#chapter-{idx}"
                                new_a["data-chapter-index"] = str(idx)
                                new_a["class"] = "toc-link"
                                new_a["style"] = "color: #2563eb; text-decoration: none; font-weight: 500;"
                                new_a.string = sib_text
                                sib.clear()
                                sib.append(new_a)
                            break

    def _apply_typography_hierarchy(
        self,
        soup: BeautifulSoup,
        chapter_index: int,
        book_title: str | None = None,
        author: str | None = None,
    ) -> None:
        """
        Enforce a clear typography hierarchy:
        - Chapter 0 (first page): Significantly larger main page title (font-size: 2.5rem, bold, centered).
        - Regular chapters: Prominent chapter title (font-size: 1.75rem, bold).
        - Body pages / paragraphs: Standard reader text (font-size: 1.05rem, line-height: 1.8).
        """
        if chapter_index == 0:
            # First page: promote first heading or title to .book-main-title
            main_h = soup.find(["h1", "h2", "h3"])
            if main_h:
                main_h["class"] = ["book-main-title"]
                main_h["style"] = (
                    "font-size: 2.5rem; font-weight: 800; line-height: 1.2; "
                    "color: #111827; margin-top: 2rem; margin-bottom: 1.5rem; "
                    "letter-spacing: -0.025em; text-align: center;"
                )
            elif book_title:
                # If no heading exists on first page, prepend a prominent main title
                new_h1 = soup.new_tag("h1", attrs={"class": "book-main-title"})
                new_h1["style"] = (
                    "font-size: 2.5rem; font-weight: 800; line-height: 1.2; "
                    "color: #111827; margin-top: 2rem; margin-bottom: 1.5rem; "
                    "letter-spacing: -0.025em; text-align: center;"
                )
                new_h1.string = book_title
                first_child = soup.find()
                if first_child:
                    first_child.insert_before(new_h1)
                else:
                    soup.append(new_h1)

            # Subtitle / author
            if author:
                author_p = soup.find(lambda tag: tag.name == "p" and author.lower() in tag.get_text().lower())
                if author_p:
                    author_p["class"] = ["book-author"]
                    author_p["style"] = (
                        "font-size: 1.25rem; font-weight: 500; color: #4b5563; "
                        "text-align: center; margin-bottom: 2rem;"
                    )

        else:
            # Subsequent chapters: style chapter title
            ch_heading = soup.find(["h1", "h2"])
            if ch_heading:
                ch_heading["class"] = ["chapter-title"]
                ch_heading["style"] = (
                    "font-size: 1.75rem; font-weight: 700; line-height: 1.3; "
                    "color: #1f2937; margin-top: 1.5rem; margin-bottom: 1rem; "
                    "border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem;"
                )

        # Style general paragraphs
        for p in soup.find_all("p"):
            if "book-author" not in p.get("class", []):
                p["class"] = p.get("class", []) + ["book-paragraph"]
                p["style"] = "font-size: 1.05rem; line-height: 1.8; margin-bottom: 1.15rem; color: #1f2937;"


content_enricher = ContentEnricher()

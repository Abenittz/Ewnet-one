import io
import re
from pathlib import Path
from typing import TypedDict

import mammoth
from bs4 import BeautifulSoup, NavigableString, Tag


class ChapterSplitResult(TypedDict):
    chapter_index: int
    title: str
    content_html_path: str
    word_count: int


# Multi-language chapter title markers (Latin, Cyrillic, Arabic, Amharic, CJK, etc.).
_CHAPTER_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"chapter|chapitre|cap[ií]tulo|kapitel|kapitola|rozdzia[łl]|"
    r"fejezet|b[oö]l[uü]m|poglavlje|глава|раздел|"
    r"الفصل|باب|ምዕራፍ|章|第\s*[0-9一二三四五六七八九十百千]+"
    r")"
    r"(?:\s+[\dIVXLCDM]+|\s*[:.\-–—]\s*.+)?\s*$",
    re.IGNORECASE | re.UNICODE,
)


class DocxProcessor:
    """Convert DOCX bytes to HTML and split the document into chapter files."""

    def process_and_split(
        self,
        docx_bytes: bytes,
        output_dir: Path,
        *,
        path_prefix: str | None = None,
    ) -> list[ChapterSplitResult]:
        """
        Convert raw DOCX bytes to HTML, split into chapters, and write each
        chapter as a standalone ``.html`` file under ``output_dir``.

        Returns a list of dicts with ``chapter_index``, ``title``,
        ``content_html_path``, and ``word_count``.
        """
        if not docx_bytes:
            raise ValueError("DOCX content is empty")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Remove stale chapter files from a previous failed/partial ingest.
        for stale in output_dir.glob("chapter_*.html"):
            stale.unlink(missing_ok=True)

        html = self._docx_to_html(docx_bytes)
        if not html.strip():
            raise ValueError("DOCX conversion produced empty HTML")

        chapters = self._split_html_into_chapters(html)

        results: list[ChapterSplitResult] = []
        for index, (title, fragments) in enumerate(chapters):
            filename = f"chapter_{index:04d}.html"
            file_path = output_dir / filename
            content_html = "".join(fragments).strip() or f"<p>{title}</p>"
            file_path.write_text(content_html, encoding="utf-8")

            if path_prefix:
                stored_path = f"{path_prefix.rstrip('/')}/{filename}"
            else:
                stored_path = str(file_path)

            results.append(
                ChapterSplitResult(
                    chapter_index=index,
                    title=title[:512],
                    content_html_path=stored_path,
                    word_count=self._word_count(content_html),
                )
            )

        return results

    def _docx_to_html(self, docx_bytes: bytes) -> str:
        try:
            result = mammoth.convert_to_html(io.BytesIO(docx_bytes))
        except Exception as exc:  # noqa: BLE001 - mammoth raises varied errors
            raise ValueError(f"Invalid or corrupt DOCX file: {exc}") from exc
        return result.value or ""

    def _split_html_into_chapters(self, html: str) -> list[tuple[str, list[str]]]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.body if soup.body else soup

        chapters: list[tuple[str, list[str]]] = []
        current_title = "Introduction"
        current_fragments: list[str] = []
        started = False

        for element in container.children:
            if isinstance(element, NavigableString):
                text = str(element)
                if text.strip():
                    current_fragments.append(text)
                continue

            if not isinstance(element, Tag):
                continue

            if self._is_chapter_break(element):
                if started or current_fragments:
                    chapters.append((current_title, current_fragments))
                current_title = self._extract_title(element) or f"Chapter {len(chapters) + 1}"
                current_fragments = [str(element)]
                started = True
            else:
                current_fragments.append(str(element))

        if current_fragments or not chapters:
            chapters.append((current_title, current_fragments))

        if not chapters:
            chapters.append(("Introduction", ["<p></p>"]))

        return chapters

    def _is_chapter_break(self, element: Tag) -> bool:
        name = (element.name or "").lower()
        if name in {"h1", "h2"}:
            return bool(element.get_text(strip=True))

        if name == "p":
            text = element.get_text(" ", strip=True)
            return bool(text) and bool(_CHAPTER_TITLE_RE.match(text))

        return False

    def _extract_title(self, element: Tag) -> str:
        return element.get_text(" ", strip=True)

    def _word_count(self, html: str) -> int:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        if not text:
            return 0
        return len(re.findall(r"\S+", text, flags=re.UNICODE))


docx_processor = DocxProcessor()

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


_CHAPTER_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"chapter|chapitre|cap[ií]tulo|kapitel|kapitola|rozdzia[łl]|"
    r"fejezet|b[oö]l[uü]m|poglavlje|глава|раздел|"
    r"الفصل|باب|ምዕራፍ|ክፍል|መቅድም|መግቢያ|章|第\s*[0-9一二三四五六七八九十百千]+"
    r")"
    r"(?:\s+[\dIVXLCDMivxlcdm፩-፼]+)?"
    r"(?:\s*[:.\-–—፡]\s*.+)?\s*$",
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
        images_dir: Path | None = None,
        images_url_prefix: str | None = None,
        cover_image_path: Path | None = None,
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

        if images_dir is not None:
            images_dir = Path(images_dir)
            images_dir.mkdir(parents=True, exist_ok=True)
            for stale in images_dir.glob("img_*.*"):
                stale.unlink(missing_ok=True)

        html = self._docx_to_html(
            docx_bytes,
            images_dir=images_dir,
            images_url_prefix=images_url_prefix,
            cover_image_path=cover_image_path,
        )
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

    def _docx_to_html(
        self,
        docx_bytes: bytes,
        *,
        images_dir: Path | None = None,
        images_url_prefix: str | None = None,
        cover_image_path: Path | None = None,
    ) -> str:
        convert_image = None
        if images_dir is not None and images_url_prefix is not None:
            images_dir.mkdir(parents=True, exist_ok=True)
            image_counter = 0

            def _convert_img(image):
                nonlocal image_counter
                image_counter += 1
                ext = mammoth.images.image_filename_extension(image) or "png"
                if ext.lower() == "jpeg":
                    ext = "jpg"
                filename = f"img_{image_counter:03d}.{ext}"
                target_path = images_dir / filename

                with image.open() as stream:
                    data = stream.read()
                target_path.write_bytes(data)

                if (
                    image_counter == 1
                    and cover_image_path is not None
                    and not cover_image_path.exists()
                ):
                    try:
                        cover_image_path.write_bytes(data)
                    except Exception:
                        pass

                return {"src": f"{images_url_prefix.rstrip('/')}/{filename}"}

            convert_image = mammoth.images.img_element(_convert_img)

        try:
            kwargs = {}
            if convert_image is not None:
                kwargs["convert_image"] = convert_image
            result = mammoth.convert_to_html(io.BytesIO(docx_bytes), **kwargs)
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

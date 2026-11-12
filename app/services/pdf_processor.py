import html
import io
import re
from pathlib import Path
from typing import Any, TypedDict

_CHAPTER_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"chapter|chapitre|cap[ií]tulo|kapitel|kapitola|rozdzia[łl]|"
    r"fejezet|b[oö]l[uü]m|poglavlje|глава|раздел|"
    r"الفصل|باب|ምዕራፍ|ክፍል|መቅድም|መግቢያ|章|第\s*[0-9一二三四五六七八九十百千]+"
    r")"
    r"(?:\s+[\dIVXLCDMivxlcdm፩-፼]+)?"
    r"(?:\s*[:.\-–—]\s*.+)?\s*$",
    re.IGNORECASE | re.UNICODE,
)


class ChapterSplitResult(TypedDict):
    chapter_index: int
    title: str
    content_html_path: str
    word_count: int


class ExtractedPage(TypedDict):
    page_number: int
    text: str
    heading: str | None
    image_paths: list[str]
    is_scanned: bool


class PdfProcessor:
    """Extract and split PDF documents (both digital text and scanned OCR) into HTML chapters."""

    def process_and_split(
        self,
        pdf_bytes: bytes,
        output_dir: Path,
        *,
        path_prefix: str | None = None,
        images_dir: Path | None = None,
        images_url_prefix: str | None = None,
        cover_image_path: Path | None = None,
        language_code: str = "en",
    ) -> list[ChapterSplitResult]:
        if not pdf_bytes:
            raise ValueError("PDF content is empty")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for stale in output_dir.glob("chapter_*.html"):
            stale.unlink(missing_ok=True)

        if images_dir is not None:
            images_dir = Path(images_dir)
            images_dir.mkdir(parents=True, exist_ok=True)
            for stale in images_dir.glob("img_*.*"):
                stale.unlink(missing_ok=True)
            for stale in images_dir.glob("page_*.*"):
                stale.unlink(missing_ok=True)

        # 1. Try PyMuPDF if available, otherwise pypdf
        pages, toc_chapters = self._extract_pages(
            pdf_bytes,
            images_dir=images_dir,
            images_url_prefix=images_url_prefix,
            cover_image_path=cover_image_path,
            language_code=language_code,
        )

        if not pages:
            raise ValueError("PDF contains no pages")

        # 2. Split pages into chapters
        chapters_data = self._split_into_chapters(pages, toc_chapters)

        # 3. Write HTML files
        results: list[ChapterSplitResult] = []
        for index, (title, page_elements) in enumerate(chapters_data):
            filename = f"chapter_{index:04d}.html"
            file_path = output_dir / filename
            content_html = "\n".join(page_elements).strip() or f"<p>{html.escape(title)}</p>"
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

    def _extract_pages(
        self,
        pdf_bytes: bytes,
        *,
        images_dir: Path | None,
        images_url_prefix: str | None,
        cover_image_path: Path | None,
        language_code: str,
    ) -> tuple[list[ExtractedPage], list[tuple[str, int]]]:
        """Extract pages and bookmarks from PDF."""
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            return self._extract_with_pymupdf(
                pdf_bytes,
                images_dir=images_dir,
                images_url_prefix=images_url_prefix,
                cover_image_path=cover_image_path,
                language_code=language_code,
            )
        except ImportError:
            import pypdf

            return self._extract_with_pypdf(
                pdf_bytes,
                images_dir=images_dir,
                images_url_prefix=images_url_prefix,
                cover_image_path=cover_image_path,
                language_code=language_code,
            )

    def _extract_with_pymupdf(
        self,
        pdf_bytes: bytes,
        *,
        images_dir: Path | None,
        images_url_prefix: str | None,
        cover_image_path: Path | None,
        language_code: str,
    ) -> tuple[list[ExtractedPage], list[tuple[str, int]]]:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            return [], []

        # Extract cover from first page
        if cover_image_path is not None and not cover_image_path.exists():
            try:
                first_pix = doc[0].get_pixmap(dpi=150)
                first_pix.save(str(cover_image_path))
            except Exception:
                pass

        # Check outline/bookmarks TOC
        toc_chapters: list[tuple[str, int]] = []
        try:
            for item in doc.get_toc():
                level, title, page_num = item[0], item[1], item[2]
                if level == 1 and title.strip():
                    toc_chapters.append((title.strip(), max(1, page_num)))
        except Exception:
            pass

        pages: list[ExtractedPage] = []
        for p_idx, page in enumerate(doc):
            page_num = p_idx + 1
            text = page.get_text("text").strip()
            heading = self._detect_page_heading(text)
            img_paths: list[str] = []
            is_scanned = False

            # Check if page is scanned (< 40 characters of text)
            if len(text) < 40:
                ocr_text = self._try_ocr_pymupdf_page(page, language_code)
                if ocr_text:
                    text = ocr_text
                    heading = self._detect_page_heading(text)
                elif images_dir is not None and images_url_prefix is not None:
                    # Save rendered page as scanned page view
                    is_scanned = True
                    img_name = f"page_{page_num:04d}.png"
                    target = images_dir / img_name
                    pix = page.get_pixmap(dpi=150)
                    pix.save(str(target))
                    img_paths.append(f"{images_url_prefix.rstrip('/')}/{img_name}")

            pages.append(
                ExtractedPage(
                    page_number=page_num,
                    text=text,
                    heading=heading,
                    image_paths=img_paths,
                    is_scanned=is_scanned,
                )
            )

        return pages, toc_chapters

    def _extract_with_pypdf(
        self,
        pdf_bytes: bytes,
        *,
        images_dir: Path | None,
        images_url_prefix: str | None,
        cover_image_path: Path | None,
        language_code: str,
    ) -> tuple[list[ExtractedPage], list[tuple[str, int]]]:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) == 0:
            return [], []

        # Extract cover from first page images if available
        if cover_image_path is not None and not cover_image_path.exists():
            try:
                first_page = reader.pages[0]
                if first_page.images:
                    cover_img = list(first_page.images)[0]
                    cover_image_path.write_bytes(cover_img.data)
            except Exception:
                pass

        # Check bookmarks
        toc_chapters: list[tuple[str, int]] = []
        try:
            outline = reader.outline
            if outline:
                for item in outline:
                    if hasattr(item, "title") and hasattr(item, "page"):
                        p_num = reader.get_destination_page_number(item) + 1
                        toc_chapters.append((str(item.title).strip(), p_num))
        except Exception:
            pass

        pages: list[ExtractedPage] = []
        for p_idx, page in enumerate(reader.pages):
            page_num = p_idx + 1
            text = (page.extract_text() or "").strip()
            heading = self._detect_page_heading(text)
            img_paths: list[str] = []
            is_scanned = False

            if len(text) < 40 and page.images:
                # Scanned image page - attempt OCR on embedded image
                for img_idx, img_obj in enumerate(page.images):
                    ocr_text = self._try_ocr_bytes(img_obj.data, language_code)
                    if ocr_text:
                        text = f"{text}\n\n{ocr_text}".strip()
                        heading = heading or self._detect_page_heading(text)
                    elif images_dir is not None and images_url_prefix is not None:
                        is_scanned = True
                        img_name = f"page_{page_num:04d}_img_{img_idx}.png"
                        (images_dir / img_name).write_bytes(img_obj.data)
                        img_paths.append(f"{images_url_prefix.rstrip('/')}/{img_name}")

            pages.append(
                ExtractedPage(
                    page_number=page_num,
                    text=text,
                    heading=heading,
                    image_paths=img_paths,
                    is_scanned=is_scanned,
                )
            )

        return pages, toc_chapters

    def _try_ocr_pymupdf_page(self, page: Any, language_code: str) -> str:
        try:
            import pytesseract
            from PIL import Image

            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_lang = "amh+eng" if language_code.lower() in {"am", "amh"} else "eng"
            return pytesseract.image_to_string(img, lang=ocr_lang).strip()
        except Exception:
            return ""

    def _try_ocr_bytes(self, image_bytes: bytes, language_code: str) -> str:
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            ocr_lang = "amh+eng" if language_code.lower() in {"am", "amh"} else "eng"
            return pytesseract.image_to_string(img, lang=ocr_lang).strip()
        except Exception:
            return ""

    def _detect_page_heading(self, text: str) -> str | None:
        if not text:
            return None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[:3]:  # Check first 3 lines
            if _CHAPTER_TITLE_RE.match(line):
                return line
        return None

    def _split_into_chapters(
        self,
        pages: list[ExtractedPage],
        toc_chapters: list[tuple[str, int]],
    ) -> list[tuple[str, list[str]]]:
        """Group pages into chapters based on TOC, headings, or chunking."""
        # Case 1: PDF has structured bookmarks TOC
        if toc_chapters:
            return self._split_by_toc(pages, toc_chapters)

        # Case 2: Detect chapter headings in page text
        chapters: list[tuple[str, list[str]]] = []
        current_title = "Introduction"
        current_fragments: list[str] = []

        for page in pages:
            if page["heading"]:
                if current_fragments or chapters:
                    chapters.append((current_title, current_fragments))
                current_title = page["heading"]
                current_fragments = [self._page_to_html(page)]
            else:
                current_fragments.append(self._page_to_html(page))

        if current_fragments:
            chapters.append((current_title, current_fragments))

        # Case 3: If no headings found across whole PDF, chunk pages
        if len(chapters) == 1 and len(pages) > 15:
            return self._chunk_pages(pages, chunk_size=10)

        return chapters or [("Introduction", ["<p>No text available.</p>"])]

    def _split_by_toc(
        self,
        pages: list[ExtractedPage],
        toc_chapters: list[tuple[str, int]],
    ) -> list[tuple[str, list[str]]]:
        chapters: list[tuple[str, list[str]]] = []
        page_map = {p["page_number"]: p for p in pages}

        sorted_toc = sorted(toc_chapters, key=lambda x: x[1])
        for i, (title, start_page) in enumerate(sorted_toc):
            end_page = sorted_toc[i + 1][1] if i + 1 < len(sorted_toc) else len(pages) + 1
            chapter_frags: list[str] = []
            for p_num in range(start_page, end_page):
                if p_num in page_map:
                    chapter_frags.append(self._page_to_html(page_map[p_num]))
            if chapter_frags:
                chapters.append((title, chapter_frags))

        return chapters or [("Introduction", [self._page_to_html(p) for p in pages])]

    def _chunk_pages(
        self,
        pages: list[ExtractedPage],
        chunk_size: int = 10,
    ) -> list[tuple[str, list[str]]]:
        chapters: list[tuple[str, list[str]]] = []
        for idx in range(0, len(pages), chunk_size):
            chunk = pages[idx : idx + chunk_size]
            title = f"Chapter {len(chapters) + 1}"
            frags = [self._page_to_html(p) for p in chunk]
            chapters.append((title, frags))
        return chapters

    def _page_to_html(self, page: ExtractedPage) -> str:
        parts: list[str] = []
        if page["heading"]:
            parts.append(f"<h2>{html.escape(page['heading'])}</h2>")

        # Scanned page images
        for img_url in page["image_paths"]:
            parts.append(
                f'<div class="scanned-page"><img src="{img_url}" alt="Page {page["page_number"]}" /></div>'
            )

        # Text paragraphs
        if page["text"]:
            paragraphs = page["text"].split("\n\n")
            for p in paragraphs:
                clean_p = p.strip()
                if clean_p and clean_p != page["heading"]:
                    # Escape HTML and preserve line breaks within paragraphs
                    escaped_lines = [html.escape(line) for line in clean_p.splitlines() if line.strip()]
                    parts.append(f"<p>{'<br/>'.join(escaped_lines)}</p>")

        return "\n".join(parts)

    def _word_count(self, html_text: str) -> int:
        clean = re.sub(r"<[^>]+>", " ", html_text)
        return len(re.findall(r"\S+", clean, flags=re.UNICODE))


pdf_processor = PdfProcessor()

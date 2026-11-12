import html
import io
import os
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote

from bs4 import BeautifulSoup

from app.services.docx_processor import _CHAPTER_TITLE_RE, ChapterSplitResult


class EpubProcessor:
    """Extract and split EPUB documents into standalone HTML chapters."""

    def extract_metadata(self, epub_bytes: bytes) -> dict[str, str]:
        """Extract title, creator/author, and language from EPUB package metadata."""
        if not epub_bytes:
            return {}

        metadata: dict[str, str] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(epub_bytes)) as z:
                opf_path = self._find_opf_path(z)
                if not opf_path:
                    return {}

                opf_content = z.read(opf_path)
                root = ET.fromstring(opf_content)

                # XML namespaces
                ns = {
                    "opf": "http://www.idpf.org/2007/opf",
                    "dc": "http://purl.org/dc/elements/1.1/",
                }

                # Try with and without namespace
                title_elem = root.find(".//dc:title", ns)
                if title_elem is None:
                    title_elem = root.find(".//{http://purl.org/dc/elements/1.1/}title")
                if title_elem is not None and title_elem.text:
                    metadata["title"] = title_elem.text.strip()

                # Authors / Creators (support multiple dc:creator elements)
                creators = root.findall(".//dc:creator", ns) or root.findall(".//{http://purl.org/dc/elements/1.1/}creator")
                if creators:
                    author_names = [c.text.strip() for c in creators if c.text and c.text.strip()]
                    if author_names:
                        metadata["author"] = ", ".join(author_names)

                desc_elem = root.find(".//dc:description", ns)
                if desc_elem is None:
                    desc_elem = root.find(".//{http://purl.org/dc/elements/1.1/}description")
                if desc_elem is not None and desc_elem.text:
                    metadata["description"] = desc_elem.text.strip()

                lang_elem = root.find(".//dc:language", ns)
                if lang_elem is None:
                    lang_elem = root.find(".//{http://purl.org/dc/elements/1.1/}language")
                if lang_elem is not None and lang_elem.text:
                    metadata["language"] = lang_elem.text.strip().lower()

        except Exception:
            pass

        return metadata

    def process_and_split(
        self,
        epub_bytes: bytes,
        output_dir: Path,
        *,
        path_prefix: str | None = None,
        images_dir: Path | None = None,
        images_url_prefix: str | None = None,
        cover_image_path: Path | None = None,
        language_code: str = "en",
    ) -> list[ChapterSplitResult]:
        """
        Extract chapters and assets from an EPUB archive and write standalone
        HTML files to ``output_dir``.
        """
        if not epub_bytes:
            raise ValueError("EPUB content is empty")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for stale in output_dir.glob("chapter_*.html"):
            stale.unlink(missing_ok=True)

        if images_dir is not None:
            images_dir = Path(images_dir)
            images_dir.mkdir(parents=True, exist_ok=True)
            for stale in images_dir.glob("img_*.*"):
                stale.unlink(missing_ok=True)

        try:
            with zipfile.ZipFile(io.BytesIO(epub_bytes)) as z:
                opf_path = self._find_opf_path(z)
                if not opf_path:
                    raise ValueError("Invalid EPUB: META-INF/container.xml or rootfile not found")

                opf_dir = posixpath.dirname(opf_path)
                opf_content = z.read(opf_path)
                root = ET.fromstring(opf_content)

                # Parse manifest items
                manifest_items: dict[str, dict[str, str]] = {}
                for item in root.findall(".//{http://www.idpf.org/2007/opf}item") or root.findall(".//item"):
                    item_id = item.get("id")
                    href = item.get("href")
                    media_type = item.get("media-type", "")
                    properties = item.get("properties", "")
                    if item_id and href:
                        manifest_items[item_id] = {
                            "href": href,
                            "media_type": media_type,
                            "properties": properties,
                        }

                # Extract cover image if present
                self._extract_cover_image(z, root, opf_dir, manifest_items, cover_image_path)

                # Parse TOC navigation (EPUB 2 NCX or EPUB 3 Nav)
                toc_titles = self._parse_toc(z, root, opf_dir, manifest_items)

                # Parse spine items
                spine_items = []
                for itemref in root.findall(".//{http://www.idpf.org/2007/opf}itemref") or root.findall(".//itemref"):
                    idref = itemref.get("idref")
                    if idref and idref in manifest_items:
                        spine_items.append(manifest_items[idref])

                if not spine_items:
                    # Fallback: take all html/xhtml items from manifest
                    spine_items = [
                        it for it in manifest_items.values()
                        if "html" in it.get("media_type", "").lower()
                    ]

                if not spine_items:
                    raise ValueError("No readable XHTML/HTML content items found in EPUB")

                chapters: list[ChapterSplitResult] = []
                image_counter = 0

                for idx, spine_item in enumerate(spine_items):
                    href = spine_item["href"]
                    # Resolve full path inside zip
                    item_zip_path = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href

                    try:
                        raw_html = z.read(item_zip_path).decode("utf-8", errors="replace")
                    except KeyError:
                        # Sometimes href is URL-encoded
                        decoded_path = posixpath.normpath(posixpath.join(opf_dir, unquote(href))) if opf_dir else unquote(href)
                        try:
                            raw_html = z.read(decoded_path).decode("utf-8", errors="replace")
                            item_zip_path = decoded_path
                        except KeyError:
                            continue

                    soup = BeautifulSoup(raw_html, "html.parser")

                    # Remove unwanted tags
                    for tag in soup(["script", "style", "link"]):
                        tag.decompose()

                    # Extract / rewrite images (support both <img> and SVG <image>)
                    if images_dir is not None and images_url_prefix is not None:
                        current_item_dir = posixpath.dirname(item_zip_path)
                        for img_tag in soup.find_all(["img", "image"]):
                            src = img_tag.get("src") or img_tag.get("xlink:href") or img_tag.get("href")
                            if not src or src.startswith("data:") or "://" in src:
                                continue

                            # Resolve image path in zip
                            img_zip_path = posixpath.normpath(posixpath.join(current_item_dir, unquote(src)))
                            try:
                                img_data = z.read(img_zip_path)
                                image_counter += 1
                                ext = Path(img_zip_path).suffix.lstrip(".").lower() or "jpg"
                                img_filename = f"img_{image_counter:03d}.{ext}"
                                (images_dir / img_filename).write_bytes(img_data)
                                rewritten_url = f"{images_url_prefix.rstrip('/')}/{img_filename}"

                                if img_tag.has_attr("src") or img_tag.name == "img":
                                    img_tag["src"] = rewritten_url
                                if img_tag.has_attr("xlink:href"):
                                    img_tag["xlink:href"] = rewritten_url
                                if img_tag.has_attr("href"):
                                    img_tag["href"] = rewritten_url

                                # If no cover yet, set first image as cover
                                if (
                                    image_counter == 1
                                    and cover_image_path is not None
                                    and not cover_image_path.exists()
                                ):
                                    cover_image_path.write_bytes(img_data)
                            except KeyError:
                                pass

                    # Determine chapter title
                    clean_href = posixpath.basename(href).split("#")[0]
                    title = toc_titles.get(clean_href) or toc_titles.get(href)

                    if not title:
                        # Try heading tags
                        h_tag = soup.find(["h1", "h2", "h3"])
                        if h_tag and h_tag.get_text(strip=True):
                            title = h_tag.get_text(strip=True)
                        elif soup.title and soup.title.get_text(strip=True):
                            candidate = soup.title.get_text(strip=True)
                            if len(candidate) < 100:
                                title = candidate

                    if not title:
                        # Try first paragraph
                        first_p = soup.find("p")
                        if first_p and _CHAPTER_TITLE_RE.match(first_p.get_text(strip=True)):
                            title = first_p.get_text(strip=True)

                    if not title:
                        title = f"Chapter {len(chapters) + 1}"

                    # Extract body content
                    body = soup.body or soup
                    body_html = "".join(str(child) for child in body.children if str(child).strip())

                    # If body is empty, skip or wrap
                    if not body_html.strip():
                        continue

                    # Count words
                    text_content = soup.get_text(separator=" ", strip=True)
                    word_count = len(text_content.split())

                    chapter_idx = len(chapters)
                    filename = f"chapter_{chapter_idx:03d}.html"
                    out_path = output_dir / filename
                    out_path.write_text(body_html, encoding="utf-8")

                    stored_rel_path = (
                        f"{path_prefix.rstrip('/')}/{filename}"
                        if path_prefix
                        else filename
                    )

                    chapters.append(
                        ChapterSplitResult(
                            chapter_index=chapter_idx,
                            title=title,
                            content_html_path=stored_rel_path,
                            word_count=word_count,
                        )
                    )

                if not chapters:
                    raise ValueError("No chapters could be extracted from the EPUB document")

                return chapters

        except zipfile.BadZipFile as exc:
            raise ValueError(f"Invalid or corrupt EPUB file: {exc}") from exc

    def _find_opf_path(self, z: zipfile.ZipFile) -> str | None:
        """Find the package (.opf) file path inside the EPUB zip container."""
        try:
            container_xml = z.read("META-INF/container.xml")
            root = ET.fromstring(container_xml)
            for rootfile in root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile") or root.findall(".//rootfile"):
                full_path = rootfile.get("full-path")
                if full_path:
                    return full_path
        except Exception:
            pass

        # Fallback: search zip entries for any .opf file
        for name in z.namelist():
            if name.lower().endswith(".opf"):
                return name
        return None

    def _extract_cover_image(
        self,
        z: zipfile.ZipFile,
        root: ET.Element,
        opf_dir: str,
        manifest_items: dict[str, dict[str, str]],
        cover_image_path: Path | None,
    ) -> None:
        """Locate and save the EPUB cover image to cover_image_path."""
        if cover_image_path is None or cover_image_path.exists():
            return

        cover_item = None

        # Check <meta name="cover" content="item_id"/>
        for meta in root.findall(".//{http://www.idpf.org/2007/opf}meta") or root.findall(".//meta"):
            if meta.get("name") == "cover":
                cover_id = meta.get("content")
                if cover_id and cover_id in manifest_items:
                    cover_item = manifest_items[cover_id]
                    break

        # Check properties="cover-image"
        if not cover_item:
            for item in manifest_items.values():
                if "cover-image" in item.get("properties", ""):
                    cover_item = item
                    break

        # Check href matching cover and image media type
        if not cover_item:
            for item in manifest_items.values():
                if "cover" in item["href"].lower() and item.get("media_type", "").startswith("image/"):
                    cover_item = item
                    break

        # Check <guide><reference type="cover" .../>
        if not cover_item:
            guide = root.find(".//{http://www.idpf.org/2007/opf}guide")
            if guide is None:
                guide = root.find(".//guide")
            if guide is not None:
                for ref in guide.findall(".//{http://www.idpf.org/2007/opf}reference") or guide.findall(".//reference"):
                    if ref.get("type") == "cover" and ref.get("href"):
                        ref_href = ref.get("href")
                        clean_ref = ref_href.split("#")[0]
                        for item in manifest_items.values():
                            if item["href"] == clean_ref or posixpath.basename(item["href"]) == posixpath.basename(clean_ref):
                                cover_item = item
                                break
                        if cover_item:
                            break

        if cover_item:
            cover_href = cover_item["href"]
            cover_zip_path = posixpath.normpath(posixpath.join(opf_dir, unquote(cover_href))) if opf_dir else unquote(cover_href)
            media_type = cover_item.get("media_type", "").lower()
            try:
                # If cover_item is an image file, save directly
                if media_type.startswith("image/") or any(cover_zip_path.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                    data = z.read(cover_zip_path)
                    cover_image_path.write_bytes(data)
                elif "html" in media_type or cover_zip_path.lower().endswith((".xhtml", ".html")):
                    # Cover item is an XHTML wrapper page containing the actual image
                    cover_html = z.read(cover_zip_path).decode("utf-8", errors="replace")
                    soup = BeautifulSoup(cover_html, "html.parser")
                    img_tag = soup.find(["img", "image"])
                    if img_tag:
                        img_src = img_tag.get("src") or img_tag.get("xlink:href") or img_tag.get("href")
                        if img_src and not img_src.startswith("data:"):
                            cover_dir = posixpath.dirname(cover_zip_path)
                            img_zip = posixpath.normpath(posixpath.join(cover_dir, unquote(img_src)))
                            data = z.read(img_zip)
                            cover_image_path.write_bytes(data)
            except Exception:
                pass

    def _parse_toc(
        self,
        z: zipfile.ZipFile,
        root: ET.Element,
        opf_dir: str,
        manifest_items: dict[str, dict[str, str]],
    ) -> dict[str, str]:
        """Parse EPUB 2 NCX or EPUB 3 navigation doc to build an href -> title mapping."""
        titles: dict[str, str] = {}

        # 1. Try EPUB 2 NCX
        ncx_item = None
        for item in manifest_items.values():
            if "toc.ncx" in item["href"].lower() or item.get("media_type") == "application/x-dtbncx+xml":
                ncx_item = item
                break

        if ncx_item:
            ncx_href = ncx_item["href"]
            ncx_zip_path = posixpath.normpath(posixpath.join(opf_dir, unquote(ncx_href))) if opf_dir else unquote(ncx_href)
            try:
                ncx_xml = z.read(ncx_zip_path)
                ncx_root = ET.fromstring(ncx_xml)
                navpoints = ncx_root.findall(".//{http://www.daisy.org/z3986/2005/ncx/}navPoint")
                if not navpoints:
                    navpoints = ncx_root.findall(".//navPoint")
                for navpoint in navpoints:
                    text_elem = navpoint.find(".//{http://www.daisy.org/z3986/2005/ncx/}text")
                    if text_elem is None:
                        text_elem = navpoint.find(".//text")
                    content_elem = navpoint.find(".//{http://www.daisy.org/z3986/2005/ncx/}content")
                    if content_elem is None:
                        content_elem = navpoint.find(".//content")
                    if text_elem is not None and text_elem.text and content_elem is not None:
                        src = content_elem.get("src", "")
                        clean_src = posixpath.basename(src).split("#")[0]
                        if clean_src not in titles:
                            titles[clean_src] = text_elem.text.strip()
                        titles[src] = text_elem.text.strip()
            except Exception:
                pass

        # 2. Try EPUB 3 Navigation Document
        if not titles:
            nav_item = None
            for item in manifest_items.values():
                if "nav" in item.get("properties", "").split():
                    nav_item = item
                    break

            if nav_item:
                nav_href = nav_item["href"]
                nav_zip_path = posixpath.normpath(posixpath.join(opf_dir, unquote(nav_href))) if opf_dir else unquote(nav_href)
                try:
                    nav_html = z.read(nav_zip_path).decode("utf-8", errors="replace")
                    soup = BeautifulSoup(nav_html, "html.parser")
                    toc_nav = soup.find("nav", attrs={"epub:type": "toc"}) or soup.find("nav")
                    if toc_nav:
                        for a in toc_nav.find_all("a"):
                            href = a.get("href", "")
                            text = a.get_text(strip=True)
                            if href and text:
                                clean_src = posixpath.basename(href).split("#")[0]
                                if clean_src not in titles:
                                    titles[clean_src] = text
                                titles[href] = text
                except Exception:
                    pass

        return titles


epub_processor = EpubProcessor()

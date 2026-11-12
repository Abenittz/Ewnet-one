import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from app.services.docx_processor import DocxProcessor


def make_docx(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        p_xml = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
        zf.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{p_xml}</w:body>
</w:document>""",
        )
    return buf.getvalue()


def test_docx_multilingual_chapter_splitting():
    processor = DocxProcessor()
    paragraphs = [
        "Chapter 1: The Beginning",
        "This is the opening text of the book.",
        "ምዕራፍ 2: ሁለተኛ ክፍል",
        "ይህ ሁለተኛው ምዕራፍ ነው። ደህና ሁኑ።",
    ]
    docx_bytes = make_docx(paragraphs)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        results = processor.process_and_split(docx_bytes, output_dir)

        assert len(results) == 2
        assert "Chapter 1" in results[0]["title"]
        assert results[0]["chapter_index"] == 0
        assert results[0]["word_count"] > 0

        assert "ምዕራፍ 2" in results[1]["title"]
        assert results[1]["chapter_index"] == 1
        assert results[1]["word_count"] > 0

        ch0_file = output_dir / "chapter_0000.html"
        ch1_file = output_dir / "chapter_0001.html"
        assert ch0_file.is_file()
        assert ch1_file.is_file()
        assert "The Beginning" in ch0_file.read_text(encoding="utf-8")
        assert "ሁለተኛው ምዕራፍ" in ch1_file.read_text(encoding="utf-8")


def test_docx_empty_bytes_raises_error():
    processor = DocxProcessor()
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="DOCX content is empty"):
            processor.process_and_split(b"", Path(tmpdir))


def test_docx_corrupt_data_raises_error():
    processor = DocxProcessor()
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="Invalid or corrupt DOCX"):
            processor.process_and_split(b"not-a-docx-file", Path(tmpdir))

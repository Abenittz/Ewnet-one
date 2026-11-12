import io
import fitz
import pytest
from httpx import AsyncClient

from app.services.content_enricher import content_enricher


def test_content_enricher_scripture_detection_and_linking():
    raw_html = """
    <div>
        <h1>Faith and Truth</h1>
        <p>As spoken in john 4:21-24, true worshipers will worship the Father in spirit and truth.</p>
        <p>In the beginning God created the heavens and the earth (Genesis 1:1-3).</p>
        <p>በተጨማሪም በ ዮሐንስ 4:21-24 እና በማቴዎስ 5:3-12 የተገለጸውን እንመልከት።</p>
        <p>እግዚአብሔር እረኛዬ ነው (መዝሙር 23:1)።</p>
    </div>
    """

    enriched_html, refs = content_enricher.enrich_chapter(
        raw_html,
        chapter_index=0,
        book_title="Faith and Truth",
    )

    assert len(refs) == 5

    # 1. English reference with range
    ref_john = next(r for r in refs if "john" in r["book_name"].lower())
    assert ref_john["chapter_num"] == 4
    assert ref_john["verse_start"] == 21
    assert ref_john["verse_end"] == 24
    assert 'class="scripture-ref"' in enriched_html
    assert 'data-reference="john 4:21-24"' in enriched_html

    # 2. Genesis reference
    ref_gen = next(r for r in refs if "genesis" in r["book_name"].lower())
    assert ref_gen["chapter_num"] == 1
    assert ref_gen["verse_start"] == 1
    assert ref_gen["verse_end"] == 3

    # 3. Amharic references
    ref_amharic_john = next(r for r in refs if r["book_name"] == "ዮሐንስ")
    assert ref_amharic_john["chapter_num"] == 4
    assert ref_amharic_john["verse_start"] == 21
    assert ref_amharic_john["verse_end"] == 24

    ref_matt = next(r for r in refs if r["book_name"] == "ማቴዎስ")
    assert ref_matt["chapter_num"] == 5
    assert ref_matt["verse_start"] == 3
    assert ref_matt["verse_end"] == 12

    ref_psalms = next(r for r in refs if r["book_name"] == "መዝሙር")
    assert ref_psalms["chapter_num"] == 23
    assert ref_psalms["verse_start"] == 1
    assert ref_psalms["verse_end"] is None


def test_content_enricher_compact_unspaced_scriptures():
    raw_html = """
    <div>
        <p>Refer to 2john3:6 and also 1cor13:4-8 for guidance.</p>
        <p>See john4:21-24 as well as 2ዮሐ3:6 and 1ጢሞ4:12.</p>
        <p>Do not match step2:3 or item5:1.</p>
    </div>
    """

    enriched_html, refs = content_enricher.enrich_chapter(
        raw_html,
        chapter_index=0,
    )

    # Exactly 5 valid scriptures should be matched, step2:3 and item5:1 ignored
    assert len(refs) == 5

    # 1. Test 2john3:6
    ref_2john = next(r for r in refs if r["reference_text"] == "2john3:6")
    assert "john" in ref_2john["book_name"].lower()
    assert ref_2john["chapter_num"] == 3
    assert ref_2john["verse_start"] == 6
    assert ref_2john["verse_end"] is None
    assert 'data-reference="2john3:6"' in enriched_html

    # 2. Test 1cor13:4-8
    ref_1cor = next(r for r in refs if r["reference_text"] == "1cor13:4-8")
    assert "cor" in ref_1cor["book_name"].lower()
    assert ref_1cor["chapter_num"] == 13
    assert ref_1cor["verse_start"] == 4
    assert ref_1cor["verse_end"] == 8

    # 3. Test john4:21-24
    ref_john = next(r for r in refs if r["reference_text"] == "john4:21-24")
    assert ref_john["chapter_num"] == 4
    assert ref_john["verse_start"] == 21
    assert ref_john["verse_end"] == 24

    # 4. Test 2ዮሐ3:6
    ref_2amharic = next(r for r in refs if r["reference_text"] == "2ዮሐ3:6")
    assert "ዮሐ" in ref_2amharic["book_name"]
    assert ref_2amharic["chapter_num"] == 3
    assert ref_2amharic["verse_start"] == 6

    # 5. Non-scriptures not tagged
    assert 'data-reference="step2:3"' not in enriched_html
    assert 'data-reference="item5:1"' not in enriched_html


def test_content_enricher_typography_and_content_menu():
    # Chapter 0 (first page)
    ch0_raw = """
    <div>
        <h1>Great Book of Truth</h1>
        <p class="author">By Author Name</p>
        <div class="toc">
            <h2>Table of Contents</h2>
            <p>Chapter 1: The Beginning</p>
            <p>Chapter 2: The Path</p>
        </div>
    </div>
    """
    ch_titles = ["Chapter 1: The Beginning", "Chapter 2: The Path"]

    ch0_enriched, _ = content_enricher.enrich_chapter(
        ch0_raw,
        chapter_index=0,
        book_title="Great Book of Truth",
        author="Author Name",
        chapter_titles=ch_titles,
    )

    # 1. Significant typography difference on first page title
    assert 'class="book-main-title"' in ch0_enriched
    assert "2.5rem" in ch0_enriched
    assert ".book-main-title" in ch0_enriched

    # 2. Content menu / TOC linking
    assert 'class="toc-link"' in ch0_enriched
    assert 'data-chapter-index="0"' in ch0_enriched
    assert 'href="#chapter-0"' in ch0_enriched

    # Chapter 1 (normal chapter)
    ch1_raw = """
    <div>
        <h1>Chapter 1: The Beginning</h1>
        <p>This is standard paragraph text of page one.</p>
    </div>
    """
    ch1_enriched, _ = content_enricher.enrich_chapter(
        ch1_raw,
        chapter_index=1,
        book_title="Great Book of Truth",
        chapter_titles=ch_titles,
    )

    # Normal chapter title has chapter-title class with 1.75rem
    assert 'class="chapter-title"' in ch1_enriched
    assert "1.75rem" in ch1_enriched


@pytest.mark.anyio
async def test_admin_upload_with_scripture_and_references_endpoint(async_client: AsyncClient):
    # Create sample PDF containing scripture text
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Book Title\n\nRefer to john 4:21-24 and Genesis 1:1 for guidance.")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Chapter 2\n\nAlso remember Romans 8:28.")
    doc.set_toc([
        [1, "Chapter 1", 1],
        [1, "Chapter 2", 2],
    ])
    pdf_bytes = doc.tobytes()
    doc.close()

    files = {"file": ("scripture_book.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "title": "Scripture Study Book",
        "language_code": "en",
        "author": "Theologian",
    }
    response = await async_client.post("/api/v1/admin/books/upload", files=files, data=data)
    assert response.status_code == 201
    admin_data = response.json()
    book_id = admin_data["book_id"]

    # Verify detected references returned in admin upload response
    assert len(admin_data["references"]) >= 2
    ref_texts = [r["reference_text"].lower() for r in admin_data["references"]]
    assert any("john 4:21-24" in rt for rt in ref_texts)
    assert any("genesis 1:1" in rt for rt in ref_texts)
    assert any("romans 8:28" in rt for rt in ref_texts)

    # Verify references endpoint
    refs_resp = await async_client.get(f"/api/v1/reader/{book_id}/references")
    assert refs_resp.status_code == 200
    refs_list = refs_resp.json()
    assert len(refs_list) >= 2

    # Verify manifest reflects total_references
    manifest_resp = await async_client.get(f"/api/v1/reader/{book_id}/manifest")
    assert manifest_resp.status_code == 200
    assert manifest_resp.json()["total_references"] >= 2

    # Verify chapter HTML content contains styled scripture link
    html_resp = await async_client.get(f"/api/v1/reader/{book_id}/chapters/0/html")
    assert html_resp.status_code == 200
    assert 'class="scripture-ref"' in html_resp.text
    assert "john 4:21-24" in html_resp.text
    assert 'color: #2563eb' in html_resp.text
    assert 'class="book-main-title"' in html_resp.text

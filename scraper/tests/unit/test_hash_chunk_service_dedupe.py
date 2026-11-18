from src.chunking.chunker import chunk_page
from src.deduplication.deduper import dedupe_pages
from src.extractors.service_extractor import extract_service_record
from src.utils.hashing import sha256_text


def test_hash_is_stable_for_whitespace():
    assert sha256_text("A  B") == sha256_text("a b")


def test_chunking_adds_metadata():
    page = {"id": "p1", "url": "https://x.test", "title": "Title", "page_type": "service", "service_name": "SEO", "service_category": "SEO", "source_priority": 1, "clean_text": "Overview\n" + "word " * 300}
    chunks = chunk_page(page, "now")
    assert chunks and chunks[0]["url"] == "https://x.test"


def test_service_extraction_shape():
    page = {"page_type": "service", "service_name": "SEO", "title": "SEO", "clean_text": "Benefits\nBetter visibility for local business websites.", "summary": "SEO summary", "canonical_url": "https://x.test/seo", "url": "https://x.test/seo", "service_category": "SEO", "cta": []}
    service = extract_service_record(page, [], [], [])
    assert service["service_name"] == "SEO"


def test_dedupe_pages_exact_hash():
    pages = [
        {"url": "a", "content_hash": "x", "clean_text": "same text " * 100},
        {"url": "b", "content_hash": "x", "clean_text": "same text " * 100},
    ]
    kept, dupes = dedupe_pages(pages)
    assert len(kept) == 1
    assert dupes

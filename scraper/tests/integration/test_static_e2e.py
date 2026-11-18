from src.classifiers.page_classifier import classify_page
from src.extractors.html_extractor import extract_page


def test_static_e2e_extraction_and_classification():
    html = "<html><body><main><h1>Shopify Development</h1><p>We build Shopify stores for e-commerce businesses.</p></main></body></html>"
    page = extract_page(html, "https://example.com/shopify-development", "example.com", "now")
    page_type, category, service = classify_page("https://example.com/shopify-development", page["title"], page["clean_text"])
    assert page_type == "service"
    assert category == "Development"
    assert service == "Shopify Development"

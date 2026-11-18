from src.utils.url import classify_url, normalize_url


def test_normalize_url_removes_tracking_and_fragment():
    url = normalize_url("https://www.example.com/a/?utm_source=x&b=2#top")
    assert url == "https://example.com/a?b=2"


def test_classify_service_url():
    assert classify_url("https://example.com/shopify-seo") == "service"

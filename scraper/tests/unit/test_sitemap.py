from src.crawler.discovery import parse_sitemap_xml


def test_parse_sitemap_index_and_urls():
    xml = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://x.test/a.xml</loc></sitemap></sitemapindex>"""
    sitemaps, urls = parse_sitemap_xml(xml)
    assert sitemaps == ["https://x.test/a.xml"]
    assert urls == []

    xml2 = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://x.test/</loc><lastmod>2026-01-01</lastmod></url></urlset>"""
    sitemaps, urls = parse_sitemap_xml(xml2)
    assert urls == [("https://x.test/", "2026-01-01")]

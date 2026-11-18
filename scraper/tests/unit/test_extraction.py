from src.extractors.html_extractor import extract_faqs, extract_page, extract_pricing, soup_from_html


HTML = """
<html lang="en"><head><title>SEO Service</title><meta name="description" content="SEO help"><link rel="canonical" href="https://example.com/seo"></head>
<body><header>Menu</header><main><h1>SEO Service</h1><p>We provide technical SEO audits and local SEO services.</p>
<section class="faq"><h3>How long does SEO take?</h3><p>SEO timelines vary by competition.</p></section>
<div class="price"><h3>Starter</h3><p>Starting from $500 / month</p><ul><li>Audit</li></ul><a href="/contact">Contact</a></div>
</main><footer>Footer</footer></body></html>
"""


def test_extract_page_removes_header_footer():
    page = extract_page(HTML, "https://example.com/seo", "example.com", "2026-01-01T00:00:00Z")
    assert "Menu" not in page["clean_text"]
    assert "technical SEO" in page["clean_text"]
    assert page["canonical_url"] == "https://example.com/seo"


def test_extract_faqs():
    faqs = extract_faqs(soup_from_html(HTML), "https://example.com/seo", "SEO Service", "SEO", "SEO Service", "now")
    assert faqs and faqs[0]["question"] == "How long does SEO take?"


def test_extract_pricing():
    pricing = extract_pricing(soup_from_html(HTML), "https://example.com/seo", "SEO Service", "now")
    assert pricing and pricing[0]["price"] == "500"


def test_extract_elementor_pricing_with_spaced_currency_and_monthly_period():
    html = """
    <main>
      <section>
        <h2>Our Plans</h2>
        <div class="elementor-price-table">
          <div class="elementor-price-table__header">
            <h3 class="elementor-price-table__heading">Basic</h3>
          </div>
          <div class="elementor-price-table__price">
            <span class="elementor-price-table__currency">&#036;</span>
            <span class="elementor-price-table__integer-part">500</span>
            <span class="elementor-price-table__period">Monthly</span>
          </div>
          <ul class="elementor-price-table__features-list">
            <li>Basic SEO</li>
            <li>Google My Business Optimization</li>
          </ul>
          <a class="elementor-price-table__button" href="/contact">Get Started</a>
        </div>
      </section>
    </main>
    """
    pricing = extract_pricing(soup_from_html(html), "https://example.com/", "", "now")
    assert len(pricing) == 1
    assert pricing[0]["plan_name"] == "Basic"
    assert pricing[0]["currency"] == "$"
    assert pricing[0]["price"] == "500"
    assert pricing[0]["billing_period"] == "monthly"
    assert pricing[0]["price_text_original"].startswith("Basic $ 500 Monthly")
    assert pricing[0]["features"] == ["Basic SEO", "Google My Business Optimization"]

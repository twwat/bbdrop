from src.network.forum.link_extractor import extract_link_map


def test_extracts_imx_image_links():
    body = "[url=https://imx.to/i/abc]thumb[/url] [url=https://imx.to/i/def]thumb[/url]"
    lm = extract_link_map(body)
    urls = {l["url"] for l in lm["image_hosts"]}
    assert "https://imx.to/i/abc" in urls
    assert "https://imx.to/i/def" in urls


def test_extracts_file_host_links():
    body = "https://k2s.cc/file/abc Download: [url]https://rapidgator.net/file/xyz[/url]"
    lm = extract_link_map(body)
    urls = {l["url"] for l in lm["file_hosts"]}
    assert "https://k2s.cc/file/abc" in urls
    assert "https://rapidgator.net/file/xyz" in urls


def test_categorises_unknown_as_other():
    body = "Visit https://example.com/page"
    lm = extract_link_map(body)
    urls = {l["url"] for l in lm["others"]}
    assert "https://example.com/page" in urls


def test_dedupes_within_same_category():
    body = "https://imx.to/i/abc and again https://imx.to/i/abc"
    lm = extract_link_map(body)
    assert sum(1 for l in lm["image_hosts"] if l["url"] == "https://imx.to/i/abc") == 1


def test_strips_trailing_punctuation():
    body = "see https://imx.to/i/abc, and https://k2s.cc/file/xyz."
    lm = extract_link_map(body)
    image_urls = {l["url"] for l in lm["image_hosts"]}
    file_urls = {l["url"] for l in lm["file_hosts"]}
    assert "https://imx.to/i/abc" in image_urls
    assert "https://k2s.cc/file/xyz" in file_urls


def test_categorises_known_image_subdomains():
    body = "[url=https://t.pixhost.to/thumbs/1/2.jpg]img[/url] " \
           "[url=https://www.turboimagehost.com/p/123/foo.html]img[/url]"
    lm = extract_link_map(body)
    kinds = {l["host_kind"] for l in lm["image_hosts"]}
    assert "pixhost" in kinds
    assert "turbo" in kinds


def test_includes_host_kind_for_known_hosts():
    body = "https://imx.to/i/abc https://k2s.cc/file/xyz"
    lm = extract_link_map(body)
    assert lm["image_hosts"][0]["host_kind"] == "imx"
    assert lm["file_hosts"][0]["host_kind"] == "k2s"


def test_others_have_no_host_kind():
    body = "https://example.com/page"
    lm = extract_link_map(body)
    assert "host_kind" not in lm["others"][0]


def test_empty_body_returns_empty_buckets():
    lm = extract_link_map("")
    assert lm == {"image_hosts": [], "file_hosts": [], "others": []}


def test_url_inside_bbcode_brackets_stops_at_bracket():
    body = "[url=https://imx.to/i/abc]label[/url]"
    lm = extract_link_map(body)
    urls = {l["url"] for l in lm["image_hosts"]}
    assert "https://imx.to/i/abc" in urls
    assert not any("]" in u for u in urls)

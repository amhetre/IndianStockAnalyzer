"""Offline tests for RSS parsing and de-duplication."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import news  # noqa: E402

RSS = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>Sensex jumps 500 pts &amp; Nifty ends higher</title><link>https://example.in/a</link>
<pubDate>Fri, 27 Nov 2026 15:40:00 +0530</pubDate><description>&lt;p&gt;Markets &lt;b&gt;rallied&lt;/b&gt; today.&lt;/p&gt;</description>
<media:content url="https://img.example.in/a.jpg"/></item>
<item><title>No link item</title></item>
<item><title>Sensex jumps 500 pts &amp; Nifty ends higher</title><link>https://other.in/a</link>
<pubDate>Fri, 27 Nov 2026 15:00:00 +0530</pubDate></item>
</channel></rss>"""

GOOGLE = b"""<rss><channel><item><title>Infosys shares rise 2% - Mint</title><link>https://news.google.com/x</link>
<source url="https://livemint.com">Mint</source><pubDate>Fri, 27 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


def test_parse_feed():
    items = news._parse(RSS, "Example")
    assert len(items) == 2
    a = items[0]
    assert a["title"] == "Sensex jumps 500 pts & Nifty ends higher"
    assert a["summary"] == "Markets rallied today."
    assert a["image"] == "https://img.example.in/a.jpg" and a["source"] == "Example"
    assert a["published"] > 0


def test_merge_dedupes_and_sorts():
    items = news._merge([news._parse(RSS, "Example")], 10)
    assert len(items) == 1 and items[0]["link"] == "https://example.in/a"


def test_google_source_split():
    it = news._parse(GOOGLE, None, google=True)[0]
    assert it["title"] == "Infosys shares rise 2%" and it["source"] == "Mint"


def test_unknown_category():
    import pytest
    with pytest.raises(KeyError):
        news.get_news("crypto")

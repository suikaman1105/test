import urllib.request
import urllib.parse
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as res:
        return res.read().decode("utf-8", errors="replace")

# 複数のパラメータ名を試す
tests = [
    ("fw2",     "THE TOWER 湘南辻堂"),
    ("fw2",     "湘南辻堂"),
    ("bknname", "湘南辻堂"),
    ("kb",      "湘南辻堂"),
]

base = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=021&ta=14&"

for param, word in tests:
    url = base + urllib.parse.urlencode({param: word})
    html = fetch(url)
    blocks = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
    prices = re.findall(r'\d+万円', html)
    print(f"{param}={word!r:20s} → ブロック:{len(blocks)-1}件 / 価格:{len(prices)}件")

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

def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).strip()

def extract_field(block, label):
    m = re.search(re.escape(label) + r"</dt>\s*<dd[^>]*>(.*?)</dd>", block, re.DOTALL)
    return strip_tags(m.group(1)) if m else ""

# 新築マンション（bs=010）で検索
for bs, label in [("010", "新築マンション"), ("011", "新築分譲"), ("021", "中古マンション")]:
    url = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?" + urllib.parse.urlencode({
        "ar": "030", "bs": bs, "ta": "14", "fw2": "湘南辻堂"
    })
    html = fetch(url)
    blocks = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
    names = []
    for b in blocks[1:]:
        name = extract_field(b, "物件名")
        if name:
            names.append(name)
    print(f"bs={bs} ({label}): {len(names)}件")
    for n in names:
        print(f"  {n}")
    print()

import urllib.request
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

URL = "https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=030&bs=011&fw=%E3%82%B6%E3%83%BB%E3%82%BF%E3%83%AF%E3%83%BC%E6%A8%AA%E6%B5%9C%E5%8C%97%E4%BB%B2"

req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=15) as res:
    html = res.read().decode("utf-8", errors="replace")

with open("debug.html", "w", encoding="utf-8") as f:
    f.write(html)

# 各ブロック区切りパターンを試す
patterns = {
    "cassette property_unit": r'(?=<[^>]+class="[^"]*cassette property_unit[^"]*")',
    "dottable--cassette":     r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")',
}
for name, pat in patterns.items():
    blocks = re.split(pat, html)
    print(f"{name}: {len(blocks)-1}件")

prices = re.findall(r'[\d,]+万円', html)
print(f"\n価格パターン: {len(prices)}件  例: {prices[:5]}")

# 最初の価格周辺のHTML
if prices:
    pos = html.find(prices[0])
    print("\n--- 最初の価格周辺 ---")
    print(html[max(0,pos-600):pos+200])

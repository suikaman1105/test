import urllib.request
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

URL = "https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=030&bs=010&fw=%EF%BC%B4%EF%BC%A8%EF%BC%A5%E3%80%80%EF%BC%B4%EF%BC%AF%EF%BC%B7%EF%BC%A5%EF%BC%B2%E3%80%80%E6%B9%98%E5%8D%97%E8%BE%BB%E5%A0%82"

req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=15) as res:
    html = res.read().decode("utf-8", errors="replace")

with open("debug.html", "w", encoding="utf-8") as f:
    f.write(html)

# 物件ブロックのクラス名を探す
classes = re.findall(r'class="([^"]*(?:cassette|item|property|bukken|list)[^"]*)"', html)
unique = sorted(set(classes))
print("検出クラス名:")
for c in unique[:30]:
    print(f"  {c}")

# 価格確認
prices = re.findall(r'[\d,]+万円', html)
print(f"\n価格パターン: {len(prices)}件")
if prices:
    print("例:", prices[:5])

# dottable--cassette で試す
blocks = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
print(f"\ndottable--cassetteブロック: {len(blocks)-1}件")

"""
SUUMOのHTMLを1ページだけ取得してdebug.htmlに保存する診断スクリプト
"""
import urllib.request
import re

URL = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=021&ta=13&sc=13103&pn=1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

req = urllib.request.Request(URL, headers=HEADERS)
with urllib.request.urlopen(req, timeout=15) as res:
    html = res.read().decode("utf-8", errors="replace")

with open("debug.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"debug.html に保存しました（{len(html)}文字）")

# 物件ブロックに使われているクラス名を探す
classes = re.findall(r'class="([^"]*(?:cassette|property|item|bukken|list)[^"]*)"', html)
unique = sorted(set(classes))
print("\n検出されたクラス名（物件関連）:")
for c in unique[:30]:
    print(f"  {c}")

# 価格パターン確認
prices = re.findall(r'[\d,]+万円', html)
print(f"\n価格パターン検出数: {len(prices)}")
if prices:
    print("例:", prices[:5])

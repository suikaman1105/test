import re

with open("debug.html", "r", encoding="utf-8") as f:
    html = f.read()

# ブロック分割
parts = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
print(f"物件ブロック数: {len(parts)-1}")

if len(parts) > 1:
    block = parts[1]
    # ブロック内の全hrefを表示
    hrefs = re.findall(r'href="([^"]+)"', block)
    print("\n最初のブロック内のhref一覧:")
    for h in hrefs:
        print(f"  {h}")

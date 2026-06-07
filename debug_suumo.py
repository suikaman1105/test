import re

with open("debug.html", "r", encoding="utf-8") as f:
    html = f.read()

blocks = re.split(r'(?=<[^>]+class="[^"]*cassette property_unit[^"]*")', html)
print(f"cassette property_unit ブロック数: {len(blocks)-1}")

if len(blocks) > 1:
    block = blocks[1]
    # 価格周辺
    prices = [m.start() for m in re.finditer(r'\d+万円', block)]
    if prices:
        print("\n--- 最初の価格周辺 ---")
        pos = prices[0]
        print(block[max(0, pos-400):pos+200])

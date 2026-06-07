import re

with open("debug.html", "r", encoding="utf-8") as f:
    html = f.read()

# 最初の価格出現箇所の前後500文字を表示
prices = [m.start() for m in re.finditer(r'\d+万円', html)]
print(f"価格出現箇所数: {len(prices)}")
if prices:
    for i, pos in enumerate(prices[:3]):
        print(f"\n=== 価格{i+1}周辺 ===")
        print(html[max(0,pos-300):pos+200])
        print("...")

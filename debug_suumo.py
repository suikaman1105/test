import re

with open("debug.html", "r", encoding="utf-8") as f:
    html = f.read()

blocks = re.split(r'(?=<[^>]+class="[^"]*cassette property_unit[^"]*")', html)
print(f"ブロック数: {len(blocks)-1}")

if len(blocks) > 1:
    print("\n--- 最初のブロック先頭2000文字 ---")
    print(blocks[1][:2000])

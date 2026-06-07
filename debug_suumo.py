"""
SUUMOのHTML構造を詳しく確認する
"""
import re

with open("debug.html", "r", encoding="utf-8") as f:
    html = f.read()

# itemlinebox item ブロックを抽出して構造確認
blocks = re.split(r'(?=<li[^>]*class="[^"]*itemlinebox[^"]*")', html)
print(f"itemlinebox ブロック数: {len(blocks)-1}")

if len(blocks) > 1:
    sample = blocks[1][:3000]
    print("\n--- 最初のブロック（先頭3000文字）---")
    print(sample)
else:
    # designateitem で試す
    blocks2 = re.split(r'(?=<div[^>]*class="[^"]*designateitem[^"]*")', html)
    print(f"\ndesignateitem ブロック数: {len(blocks2)-1}")
    if len(blocks2) > 1:
        print("\n--- 最初のブロック（先頭3000文字）---")
        print(blocks2[1][:3000])

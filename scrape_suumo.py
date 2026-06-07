"""
SUUMO 中古マンション スクレイパー
個人モニタリング用途のみ / 過度なアクセス禁止
"""

import urllib.request
import re
import json
import time
import os
import sys
import datetime

WARDS = {
    "千代田区": "13101",
    "中央区":   "13102",
    "港区":     "13103",
    "新宿区":   "13104",
    "文京区":   "13105",
    "品川区":   "13109",
    "目黒区":   "13110",
    "世田谷区": "13112",
    "渋谷区":   "13113",
    "豊島区":   "13116",
}

MAX_PAGES   = 3
SLEEP_SEC   = 2.0
DATA_FILE   = "mansion_realdata.json"
DASH_SRC    = "mansion_dashboard.html"
DASH_DST    = "mansion_dashboard_real.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    fetch error: {e}")
        return ""


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def parse_price(s):
    """'1億4980万円' や '4980万円' → float(万円)"""
    s = re.sub(r"[,\s]", "", s)
    oku = re.search(r"(\d+)億", s)
    man = re.search(r"(\d+)万円", s)
    total = 0
    if oku:
        total += int(oku.group(1)) * 10000
    if man:
        total += int(man.group(1))
    return float(total) if total > 0 else None


def parse_size(s):
    m = re.search(r"([\d.]+)\s*m", s or "")
    return float(m.group(1)) if m else None


def parse_floor(s):
    m = re.search(r"(\d+)階", s or "")
    return int(m.group(1)) if m else 1


def extract_field(block, label):
    """<dt>label</dt> の直後の <dd> テキストを返す"""
    pattern = re.escape(label) + r"</dt>\s*<dd[^>]*>(.*?)</dd>"
    m = re.search(pattern, block, re.DOTALL)
    return strip_tags(m.group(1)) if m else ""


def parse_block(block, ward_name, today):
    """1物件ブロックからレコードを生成"""
    # 物件名
    name = extract_field(block, "物件名")
    if not name:
        return None

    # 販売価格
    price_raw = extract_field(block, "販売価格")
    # dottable-value span からも試みる
    if not price_raw:
        m = re.search(r'class="dottable-value"[^>]*>(.*?)</span>', block, re.DOTALL)
        if m:
            price_raw = strip_tags(m.group(1))
    total = parse_price(price_raw)
    if not total:
        return None

    # 専有面積
    size_raw = extract_field(block, "専有面積")
    if not size_raw:
        size_raw = extract_field(block, "建物面積")
    size = parse_size(size_raw)
    if not size or size <= 0:
        return None

    # 階数
    floor_raw = extract_field(block, "階建")
    if not floor_raw:
        floor_raw = extract_field(block, "所在階")
    floor = parse_floor(floor_raw) if floor_raw else 1

    # 所在地
    addr = extract_field(block, "所在地")

    price_sqm = round(total * 10000 / size)

    return {
        "area":          ward_name,
        "building":      name,
        "address":       addr,
        "date":          today,
        "price_per_sqm": price_sqm,
        "total_price":   total,
        "size":          round(size, 1),
        "floor":         floor,
        "status":        "販売中",
    }


def scrape_ward(ward_name, city_code, today):
    records = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://suumo.jp/jj/bukken/ichiran/JJ012FC001/"
            f"?ar=030&bs=021&ta=13&sc={city_code}&pn={page}"
        )
        print(f"    p{page} ...", end=" ", flush=True)
        html = fetch(url)
        if not html:
            break
        time.sleep(SLEEP_SEC)

        # dottable--cassette を区切りとして物件ブロックに分割
        parts = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
        before = len(records)
        for part in parts[1:]:
            rec = parse_block(part, ward_name, today)
            if rec:
                records.append(rec)
        print(f"{len(records)-before}件")

        # 次ページ確認
        if f"pn={page+1}" not in html:
            break

    return records


def main():
    print("=" * 50)
    print("SUUMO 中古マンション スクレイパー")
    print("個人モニタリング用途 / 過度なアクセス禁止")
    print("=" * 50)

    today = datetime.date.today().isoformat()
    all_records = []

    for ward_name, city_code in WARDS.items():
        print(f"\n【{ward_name}】")
        recs = scrape_ward(ward_name, city_code, today)
        print(f"  合計: {len(recs)}件")
        all_records.extend(recs)
        time.sleep(SLEEP_SEC)

    if not all_records:
        print("\nデータが取得できませんでした。")
        sys.exit(1)

    # 既存データとマージ（今日分は上書き）
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    merged = [r for r in existing if r.get("date") != today] + all_records
    for i, r in enumerate(merged, 1):
        r["id"] = i

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n本日取得: {len(all_records)}件 / 累計: {len(merged)}件")
    print(f"{DATA_FILE} 保存完了")

    embed_into_html(merged)


def embed_into_html(records):
    if not os.path.exists(DASH_SRC):
        print(f"{DASH_SRC} が見つかりません")
        return

    with open(DASH_SRC, "r", encoding="utf-8") as f:
        html = f.read()

    data_js = json.dumps(records, ensure_ascii=False)

    new_load = (
        f"var REAL_DATA = {data_js};\n"
        "function loadData(){\n"
        "  try{\n"
        "    var saved=localStorage.getItem(\"mansion_v2\");\n"
        "    var savedArr=saved?JSON.parse(saved):[];\n"
        "    data=savedArr.length>REAL_DATA.length?savedArr:REAL_DATA.slice();\n"
        "  }catch(e){data=REAL_DATA.slice();}\n"
        "}"
    )
    old_load = (
        "function loadData(){\n"
        "  try{\n"
        "    var raw=localStorage.getItem(\"mansion_v2\");\n"
        "    data=raw?JSON.parse(raw):genData();\n"
        "  }catch(e){data=genData();}\n"
        "}"
    )

    html = html.replace(old_load, new_load) if old_load in html else html.replace(
        "// 初期化", f"var REAL_DATA={data_js};\n// 初期化", 1)

    with open(DASH_DST, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{DASH_DST} 生成完了")
    print(f"\n→ open {DASH_DST}")


if __name__ == "__main__":
    main()

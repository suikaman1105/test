"""
SUUMO 中古マンション スクレイパー
- 個人モニタリング用途のみ / サーバー負荷を最小限に抑える設計
- 取得データを mansion_realdata.json に保存
- mansion_dashboard_real.html を生成
"""

import urllib.request
import urllib.parse
import re
import json
import time
import os
import sys
from html.parser import HTMLParser

# 対象エリア（SUUMOの区コード）
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

MAX_PAGES = 3          # 1区あたり最大ページ数（1ページ約30件）
SLEEP_SEC = 2.0        # リクエスト間隔（サーバー負荷軽減）
DATA_FILE = "mansion_realdata.json"
DASHBOARD_SRC = "mansion_dashboard.html"
DASHBOARD_DST = "mansion_dashboard_real.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


# ---------- HTML パーサー ----------

class SuumoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self._cur = {}
        self._in_cassette = False
        self._in_name = False
        self._in_price = False
        self._in_detail = False
        self._detail_buf = []
        self._depth = 0
        self._cassette_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")

        # 物件カード開始
        if tag == "div" and "cassette_item" in cls:
            self._in_cassette = True
            self._cur = {}
            self._cassette_depth = self._depth
        if self._in_cassette:
            # 物件名
            if tag == "dd" and "cassette_item-title" in cls:
                self._in_name = True
            # 価格
            if tag == "span" and "price" in cls:
                self._in_price = True
            # 詳細テーブル
            if tag == "td" and "cassette_item-detail" in cls:
                self._in_detail = True
                self._detail_buf = []
        self._depth += 1

    def handle_endtag(self, tag):
        self._depth -= 1
        if self._in_cassette and self._depth <= self._cassette_depth and tag == "div":
            if self._cur:
                self.items.append(dict(self._cur))
            self._in_cassette = False
            self._cur = {}
        if tag == "dd":
            self._in_name = False
        if tag == "span":
            self._in_price = False
        if tag == "td":
            if self._in_detail:
                self._cur.setdefault("details", []).append("".join(self._detail_buf).strip())
            self._in_detail = False

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
        if self._in_name:
            self._cur["name"] = data
        if self._in_price:
            self._cur.setdefault("price_raw", "")
            self._cur["price_raw"] += data
        if self._in_detail:
            self._detail_buf.append(data)


# ---------- ユーティリティ ----------

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    fetch error: {e}")
        return ""


def parse_price(s):
    """'4980万円' → 4980.0"""
    if not s:
        return None
    s = re.sub(r"[,\s]", "", s)
    m = re.search(r"([\d.]+)万円", s)
    if m:
        return float(m.group(1))
    return None


def parse_size(s):
    """'72.5m²' → 72.5"""
    m = re.search(r"([\d.]+)\s*m", s or "")
    return float(m.group(1)) if m else None


def parse_floor(s):
    """'15階' → 15"""
    m = re.search(r"(\d+)階", s or "")
    return int(m.group(1)) if m else 1


def scrape_ward(ward_name, city_code):
    records = []
    today = __import__("datetime").date.today().isoformat()

    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://suumo.jp/jj/bukken/ichiran/JJ012FC001/"
            f"?ar=030&bs=021&ta=13&sc={city_code}&pn={page}"
        )
        print(f"    p{page} {url}")
        html = fetch(url)
        if not html:
            break
        time.sleep(SLEEP_SEC)

        # --- 正規表現で物件ブロックを抽出 ---
        # SUUMOの構造に合わせてパターンマッチング
        blocks = re.findall(
            r'class="cassette_item.*?(?=class="cassette_item|<div class="pagination)',
            html, re.DOTALL
        )
        if not blocks:
            # ページが存在しない
            break

        for block in blocks:
            # 物件名
            name_m = re.search(
                r'class="[^"]*cassette_item-title[^"]*"[^>]*>\s*<[^>]+>\s*([^<]+)', block
            )
            name = name_m.group(1).strip() if name_m else f"{ward_name}のマンション"

            # 価格
            price_m = re.search(r'([\d,]+)万円', block)
            price_raw = price_m.group(0) if price_m else ""
            total = parse_price(price_raw)
            if total is None:
                continue

            # 面積
            size_m = re.search(r'([\d.]+)m<sup>2</sup>', block)
            if not size_m:
                size_m = re.search(r'([\d.]+)\s*㎡', block)
            size = float(size_m.group(1)) if size_m else None
            if size is None or size <= 0:
                continue

            # 階
            floor_m = re.search(r'(\d+)階', block)
            floor = int(floor_m.group(1)) if floor_m else 1

            price_sqm = round(total / size * 10000, 0) / 10000 * 10000
            price_sqm = round(total * 10000 / size) / 10000 * 10000

            records.append({
                "area":          ward_name,
                "building":      name,
                "date":          today,
                "price_per_sqm": round(total * 10000 / size),
                "total_price":   total,
                "size":          round(size, 1),
                "floor":         floor,
                "status":        "販売中",
            })

        print(f"    → {len(records)}件累計")

        # 次ページが存在するか確認
        if f"pn={page+1}" not in html:
            break

    return records


# ---------- メイン ----------

def main():
    print("=" * 50)
    print("SUUMO 中古マンション スクレイパー")
    print("個人モニタリング用途 / 過度なアクセス禁止")
    print("=" * 50)

    all_records = []

    for ward_name, city_code in WARDS.items():
        print(f"\n【{ward_name}】取得中...")
        records = scrape_ward(ward_name, city_code)
        print(f"  完了: {len(records)}件")
        all_records.extend(records)
        time.sleep(SLEEP_SEC)

    if not all_records:
        print("\nデータが取得できませんでした。")
        sys.exit(1)

    # 既存データとマージ（日付が異なるものは保持）
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    today = __import__("datetime").date.today().isoformat()
    # 今日以外の既存データを残す
    merged = [r for r in existing if r.get("date") != today] + all_records
    # IDを振り直す
    for i, r in enumerate(merged, 1):
        r["id"] = i

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n合計 {len(all_records)}件 取得（累計 {len(merged)}件）")
    print(f"{DATA_FILE} を保存しました")

    embed_into_html(merged)


def embed_into_html(records):
    if not os.path.exists(DASHBOARD_SRC):
        print(f"{DASHBOARD_SRC} が見つかりません")
        return

    with open(DASHBOARD_SRC, "r", encoding="utf-8") as f:
        html = f.read()

    data_js = json.dumps(records, ensure_ascii=False)
    inject = f"var REAL_DATA = {data_js};\n"

    # loadData を差し替え
    new_load = (
        inject +
        "function loadData(){\n"
        "  try{\n"
        "    var saved=localStorage.getItem(\"mansion_v2\");\n"
        "    var savedArr=saved?JSON.parse(saved):[];\n"
        "    // スクレイプデータより多い場合はlocalStorage優先\n"
        "    data = savedArr.length > REAL_DATA.length ? savedArr : REAL_DATA.slice();\n"
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

    if old_load in html:
        html = html.replace(old_load, new_load)
    else:
        html = html.replace("function loadData(){", "function loadData_orig(){", 1)
        html = html.replace("// 初期化", inject + "// 初期化", 1)

    with open(DASHBOARD_DST, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{DASHBOARD_DST} を生成しました")
    print(f"\n→ open {DASHBOARD_DST}")


if __name__ == "__main__":
    main()

"""
SUUMO 中古マンション スクレイパー
個人モニタリング用途のみ / 過度なアクセス禁止
"""

import urllib.request
import urllib.parse
import re
import json
import time
import os
import sys
import datetime

CONFIG_FILE = "config.json"
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


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"[ERROR] {CONFIG_FILE} が見つかりません")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    targets = cfg.get("targets", [])
    if not targets:
        print("[ERROR] config.json の targets が空です")
        sys.exit(1)
    return targets, cfg.get("max_pages", 3), cfg.get("sleep_sec", 2.0)


def build_page_url(base_url, page):
    """ベースURLにページ番号パラメータを付与する"""
    parsed = urllib.parse.urlparse(base_url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params["pn"] = [str(page)]
    new_query = urllib.parse.urlencode({k: v[0] for k, v in params.items()})
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def build_search_url(building_name, prefecture="13"):
    """建物名からSUUMO検索URLを自動生成する
    SUUMOのfw2は日本語キーワードで検索し、英字混じりだと0件になるため
    日本語部分だけを抽出して検索URLを組み立てる
    """
    # 日本語（ひらがな・カタカナ・漢字）部分だけ抽出してスペース結合
    ja_words = re.findall(r'[ぁ-んァ-ン一-龥ー]+', building_name)
    search_word = " ".join(ja_words) if ja_words else building_name
    params = {
        "ar":  "030",
        "bs":  "021",
        "ta":  prefecture,
        "fw2": search_word,
    }
    base = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?"
    return base + urllib.parse.urlencode(params)


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
    pattern = re.escape(label) + r"</dt>\s*<dd[^>]*>(.*?)</dd>"
    m = re.search(pattern, block, re.DOTALL)
    return strip_tags(m.group(1)) if m else ""


def parse_block(block, label, today):
    name = extract_field(block, "物件名")
    if not name:
        return None

    price_raw = extract_field(block, "販売価格")
    if not price_raw:
        m = re.search(r'class="dottable-value"[^>]*>(.*?)</span>', block, re.DOTALL)
        if m:
            price_raw = strip_tags(m.group(1))
    total = parse_price(price_raw)
    if not total:
        return None

    size_raw = extract_field(block, "専有面積") or extract_field(block, "建物面積")
    size = parse_size(size_raw)
    if not size or size <= 0:
        return None

    floor_raw = extract_field(block, "所在階") or extract_field(block, "階建")
    floor = parse_floor(floor_raw)

    addr = extract_field(block, "所在地")

    # 物件詳細ページURL（/nc_XXXXX/ を含むhrefを取得）
    url_m = re.search(r'href="(/[^"]*nc_\d+[^"]*)"', block)
    suumo_url = ("https://suumo.jp" + url_m.group(1)) if url_m else ""

    return {
        "area":          label,
        "building":      name,
        "address":       addr,
        "date":          today,
        "price_per_sqm": round(total * 10000 / size),
        "total_price":   total,
        "size":          round(size, 1),
        "floor":         floor,
        "status":        "販売中",
        "suumo_url":     suumo_url,
    }


def scrape_target(label, base_url, max_pages, sleep_sec, today, building_filter=None):
    records = []
    for page in range(1, max_pages + 1):
        url = build_page_url(base_url, page)
        print(f"    p{page} ...", end=" ", flush=True)
        html = fetch(url)
        if not html:
            break
        time.sleep(sleep_sec)

        parts = re.split(r'(?=<[^>]+class="[^"]*dottable[^"]*--cassette[^"]*")', html)
        before = len(records)
        for part in parts[1:]:
            rec = parse_block(part, label, today)
            if not rec:
                continue
            # building_filter が指定されていれば物件名で絞り込む
            if building_filter:
                name = rec["building"]
                # 全角→半角に正規化して比較
                name_norm = name.translate(str.maketrans(
                    'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
                    'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
                    '０１２３４５６７８９　',
                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    'abcdefghijklmnopqrstuvwxyz'
                    '0123456789 '
                ))
                kw_norm_list = [
                    kw.translate(str.maketrans(
                        'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
                        'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
                        '０１２３４５６７８９　',
                        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                        'abcdefghijklmnopqrstuvwxyz'
                        '0123456789 '
                    )) for kw in building_filter
                ]
                if not any(kw in name_norm for kw in kw_norm_list):
                    continue
            records.append(rec)
        print(f"{len(records) - before}件")

        if f"pn={page + 1}" not in html:
            break

    return records


def main():
    print("=" * 50)
    print("SUUMO 中古マンション スクレイパー")
    print("個人モニタリング用途 / 過度なアクセス禁止")
    print("=" * 50)

    targets, max_pages, sleep_sec = load_config()
    print(f"対象: {len(targets)}件のURL")
    print(f"設定: 最大{max_pages}ページ / {sleep_sec}秒間隔\n")

    today = datetime.date.today().isoformat()
    all_records = []

    for t in targets:
        label           = t.get("label", "")
        building_name   = t.get("building_name")
        prefecture      = t.get("prefecture", "13")
        building_filter = t.get("building_filter")

        if building_name:
            # 建物名から自動でURL生成
            url = build_search_url(building_name, prefecture)
            # 建物名フィルタが未指定なら自動設定
            if not building_filter:
                building_filter = [building_name]
            if not label:
                label = building_name
        elif "url" in t:
            url = t["url"]
            if not label:
                label = url
        else:
            print(f"  [SKIP] url または building_name が必要です")
            continue

        print(f"\n【{label}】")
        print(f"  URL: {url}")
        recs = scrape_target(label, url, max_pages, sleep_sec, today, building_filter)
        print(f"  合計: {len(recs)}件")
        all_records.extend(recs)
        time.sleep(sleep_sec)

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

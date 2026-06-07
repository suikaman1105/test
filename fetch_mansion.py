"""
国土交通省 不動産取引価格情報API からマンションデータを取得し
mansion_dashboard.html に埋め込んで mansion_dashboard_real.html を生成する
"""

import urllib.request
import urllib.parse
import json
import os
import sys
import time

API_URL = "https://www.land.mlit.go.jp/webland/api/TradeListSearch"

# 東京都主要区の市区町村コード
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

PREF_CODE = "13"   # 東京都
TRADE_TYPE = "3"   # 中古マンション等


def fetch_ward(ward_name, city_code, from_q, to_q):
    params = urllib.parse.urlencode({
        "type": TRADE_TYPE,
        "area": PREF_CODE,
        "city": city_code,
        "from": from_q,
        "to":   to_q,
    })
    url = API_URL + "?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            body = res.read().decode("utf-8")
            obj = json.loads(body)
            return obj.get("data", [])
    except Exception as e:
        print(f"  [ERROR] {ward_name}: {e}")
        return []


def parse_price(s):
    if not s:
        return None
    s = s.replace(",", "").replace("円", "").strip()
    # 「2,500万円」→ 2500
    if "万" in s:
        s = s.replace("万", "")
        try:
            return float(s)
        except Exception:
            return None
    try:
        return float(s) / 10000
    except Exception:
        return None


def parse_area(s):
    if not s:
        return None
    s = s.replace("㎡", "").replace("m2", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def convert(raw, ward_name):
    records = []
    for r in raw:
        price_total = parse_price(r.get("TradePrice", ""))
        area = parse_area(r.get("Area", ""))
        if price_total is None or area is None or area <= 0:
            continue
        price_sqm = round(price_total / area, 1)

        # 取引時期: "2023年第４四半期" → "2023-10"
        period = r.get("Period", "")
        date_str = period_to_date(period)

        floor_val = r.get("FloorPlan", "") or ""
        try:
            floor_num = int(r.get("BuildingYear", "0") or 0)
        except Exception:
            floor_num = 1
        floor_num = floor_num if floor_num > 0 else 1

        records.append({
            "area":          ward_name,
            "building":      r.get("MunicipalityCode", ward_name) and (r.get("DistrictName") or ward_name + "内"),
            "date":          date_str,
            "price_per_sqm": price_sqm,
            "total_price":   round(price_total, 1),
            "size":          round(area, 1),
            "floor":         floor_num,
            "status":        "成約済",
            "floor_plan":    floor_val,
        })
    return records


def period_to_date(period):
    # "2023年第４四半期" → "2023-10"
    quarter_map = {"１": "01", "２": "04", "３": "07", "４": "10",
                   "1": "01", "2": "04", "3": "07", "4": "10"}
    try:
        year = period[:4]
        for k, v in quarter_map.items():
            if k in period[4:]:
                return f"{year}-{v}-01"
        return f"{year}-01-01"
    except Exception:
        return "2024-01-01"


def main():
    # 直近2年分（8四半期）
    quarters = ["20231", "20232", "20233", "20234",
                "20241", "20242", "20243", "20244"]
    from_q = quarters[0]
    to_q   = quarters[-1]

    print(f"取得期間: {from_q} 〜 {to_q}")
    print(f"対象区: {', '.join(WARDS.keys())}\n")

    all_records = []
    for ward_name, city_code in WARDS.items():
        print(f"取得中: {ward_name} ...", end=" ", flush=True)
        raw = fetch_ward(ward_name, city_code, from_q, to_q)
        records = convert(raw, ward_name)
        print(f"{len(records)}件")
        all_records.extend(records)
        time.sleep(0.5)   # APIへの負荷軽減

    if not all_records:
        print("\nデータが取得できませんでした。ネットワーク接続を確認してください。")
        sys.exit(1)

    # IDを振る
    for i, r in enumerate(all_records, 1):
        r["id"] = i

    print(f"\n合計 {len(all_records)} 件取得")

    # JSONとして保存
    with open("mansion_realdata.json", "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print("mansion_realdata.json を保存しました")

    # ダッシュボードHTMLに埋め込む
    embed_into_html(all_records)


def embed_into_html(records):
    src = "mansion_dashboard.html"
    dst = "mansion_dashboard_real.html"

    if not os.path.exists(src):
        print(f"{src} が見つかりません")
        return

    with open(src, "r", encoding="utf-8") as f:
        html = f.read()

    data_js = json.dumps(records, ensure_ascii=False)

    # loadData() をリアルデータで上書き
    inject = f"""
// ---- 国土交通省APIから取得したリアルデータ ----
var REAL_DATA = {data_js};
"""
    old_load = "function loadData(){\n  try{\n    var raw=localStorage.getItem(\"mansion_v2\");\n    data=raw?JSON.parse(raw):genData();\n  }catch(e){data=genData();}\n}"
    new_load = inject + """function loadData(){
  try{
    var raw=localStorage.getItem("mansion_v2");
    // localStorageに保存済みがあればそちらを優先
    var saved=raw?JSON.parse(raw):null;
    // リアルデータをベースにしてlocalStorageの追加分をマージ
    if(saved && saved.length > REAL_DATA.length){
      data=saved;
    } else {
      data=REAL_DATA.slice();
      localStorage.setItem("mansion_v2",JSON.stringify(data));
    }
  }catch(e){data=REAL_DATA.slice();}
}"""

    if old_load in html:
        html = html.replace(old_load, new_load)
    else:
        # フォールバック: loadData関数の直前に挿入
        html = html.replace("function loadData(){", inject + "function loadData(){", 1)

    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{dst} を生成しました → これをブラウザで開いてください")


if __name__ == "__main__":
    main()

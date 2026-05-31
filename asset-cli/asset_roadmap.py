#!/usr/bin/env python3
"""
資産管理 × 40歳1億円ロードマップ CLI ツール

楽天証券・マネーフォワードからコピーしたデータを読み込み、
40歳までに1億円を達成するためのロードマップとアドバイスを表示します。

標準ライブラリのみで動作（追加インストール不要）。

使い方:
    # 対話モード（プロンプトに従って入力）
    python3 asset_roadmap.py

    # データファイルを指定
    python3 asset_roadmap.py --mf moneyforward.txt --rakuten rakuten.txt \\
        --age 32 --monthly 100000 --return 5

    # 総資産を直接指定（万円単位）
    python3 asset_roadmap.py --assets 500 --age 32 --monthly 100000
"""

import argparse
import re
import sys

TARGET = 100_000_000  # 1億円

# ---- ANSI カラー ----
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[38;5;75m"
    PURPLE = "\033[38;5;141m"
    GREEN = "\033[38;5;48m"
    YELLOW = "\033[38;5;220m"
    RED = "\033[38;5;203m"
    GRAY = "\033[38;5;245m"
    CYAN = "\033[38;5;87m"


def supports_color() -> bool:
    return sys.stdout.isatty()


def color(text: str, c: str) -> str:
    if supports_color():
        return f"{c}{text}{C.RESET}"
    return text


# ---- フォーマット ----
def fmt_yen(n: float) -> str:
    n = round(n)
    if abs(n) >= 100_000_000:
        return f"{n / 100_000_000:.2f}億円"
    if abs(n) >= 10_000:
        return f"{round(n / 10_000):,}万円"
    return f"{n:,}円"


def parse_num(s: str) -> int:
    return int(re.sub(r"[,円+\s]", "", s) or 0)


# ---- パーサー ----
def parse_moneyforward(text: str) -> dict:
    res = {"total": 0, "income": 0, "expense": 0, "categories": []}
    # 資産内訳カテゴリ名（これらの行は「名称 金額円 割合%」形式）
    cat_names = ["預金・現金・暗号資産", "株式（現物）", "株式（信用）",
                 "投資信託", "年金", "ポイント・マイル", "債券", "FX", "不動産"]
    for raw in text.splitlines():
        line = raw.strip()
        # 総資産 / 資産総額
        m = re.search(r"(?:資産総額|総資産)[：:\s]*([\d,]+)\s*円", line)
        if m:
            res["total"] = parse_num(m.group(1))
        m = re.search(r"収入[^\d]*([\d,]+)", line)
        if m:
            res["income"] = parse_num(m.group(1))
        m = re.search(r"支出[^\d]*([\d,]+)", line)
        if m:
            res["expense"] = parse_num(m.group(1))
        # 資産内訳カテゴリ（割合%付きの行のみ）
        for cat in cat_names:
            cm = re.match(rf"^{re.escape(cat)}\s+([\d,]+)\s*円\s+[\d.]+\s*%", line)
            if cm:
                amt = parse_num(cm.group(1))
                if not any(c["name"] == cat for c in res["categories"]):
                    res["categories"].append({"name": cat, "amount": amt})
    if not res["total"]:
        nums = [parse_num(x) for x in re.findall(r"([\d,]+)円", text)]
        nums = [n for n in nums if n > 10_000]
        if nums:
            res["total"] = max(nums)
    return res


def parse_rakuten(text: str) -> dict:
    res = {"total": 0, "gain": 0, "holdings": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 損益（合計）を先に判定（"合計" が総資産側にマッチするのを防ぐ）
        m = re.search(r"(?:損益合計|評価損益|損益)[^\d+-]*([+-]?[\d,]+)", line)
        if m:
            res["gain"] = int(re.sub(r"[,円\s]", "", m.group(1)) or 0)
            continue
        m = re.search(r"(?:評価額合計|保有資産合計|資産合計|合計)[^\d]*([\d,]+)", line)
        if m:
            res["total"] = parse_num(m.group(1))
            continue
        m = re.match(r"^(.+?)\s+([\d,]+)\s*円", line)
        if m:
            amt = parse_num(m.group(2))
            if amt > 1000 and len(res["holdings"]) < 12:
                res["holdings"].append({"name": m.group(1).strip()[:34], "amount": amt})
    return res


# ---- シミュレーション ----
def simulate(age: int, assets: float, monthly: float, ret_pct: float) -> list:
    r = ret_pct / 100 / 12
    rows = []
    a = assets
    end = max(40 - age + 5, 10)
    for yr in range(end + 1):
        cur = age + yr
        rows.append({"age": cur, "assets": round(a)})
        if a >= TARGET and cur >= 40:
            break
        for _ in range(12):
            a = a * (1 + r) + monthly
    return rows


def reach_age(age: int, assets: float, monthly: float, ret_pct: float):
    r = ret_pct / 100 / 12
    a = assets
    for m in range(360):
        a = a * (1 + r) + monthly
        if a >= TARGET:
            return age + m / 12
    return None


def needed_monthly(assets, ret_pct, years_left):
    if years_left <= 0:
        return 0
    r_m = ret_pct / 100 / 12
    grown = assets * (1 + ret_pct / 100) ** years_left
    denom = (((1 + r_m) ** (years_left * 12)) - 1) / r_m
    return max(0, round((TARGET - grown) / denom))


# ---- 描画ヘルパー ----
def hr(char="─", n=64):
    return color(char * n, C.GRAY)


def header(title):
    print()
    print(color(f"  {title}", C.BOLD + C.BLUE))
    print(hr())


def ascii_chart(rows, reach):
    """ターミナル内に資産推移の縦棒グラフを描画"""
    height = 12
    max_val = max(TARGET * 1.05, max(r["assets"] for r in rows))
    target_line = round(height * TARGET / max_val)

    print()
    for level in range(height, 0, -1):
        # Y軸ラベル
        val_at_level = max_val * level / height
        label = f"{round(val_at_level/10_000):>6,}万"
        line = color(label + " │", C.GRAY)
        is_target_row = (level == target_line)
        for r in rows:
            bar_h = round(height * r["assets"] / max_val)
            if bar_h >= level:
                filled = color("█", C.GREEN if r["assets"] >= TARGET else C.BLUE)
                line += " " + filled + " "
            elif is_target_row:
                line += color(" ╌ ", C.YELLOW)
            else:
                line += "   "
        if is_target_row:
            line += color("  ← 1億円", C.YELLOW)
        print(line)

    # X軸
    axis = "       └" + "───" * len(rows)
    print(color(axis, C.GRAY))
    age_line = "        "
    for r in rows:
        marker = r["age"]
        age_line += f"{marker:>2} "
    print(color(age_line, C.GRAY))
    print(color("        " + "（歳）", C.DIM + C.GRAY))
    if reach:
        yrs, mos = int(reach), round((reach % 1) * 12)
        print()
        print(color(f"  ▲ 達成予測: {yrs}歳{mos}ヶ月頃", C.GREEN))


def progress_bar(cur, total, width=40):
    pct = min(cur / total, 1.0)
    filled = round(width * pct)
    bar = color("█" * filled, C.PURPLE) + color("░" * (width - filled), C.GRAY)
    return f"{bar} {pct*100:5.1f}%"


# ---- アドバイス生成 ----
def generate_advice(assets, monthly, ret, age, reach, on_track):
    advice = []
    years_left = 40 - age

    if not on_track:
        need = needed_monthly(assets, ret, years_left)
        advice.append(("優先", C.RED, "💰 月間貯蓄額を増やす",
            f"現在の月{fmt_yen(monthly)}から増額が必要です。目安は月{fmt_yen(need)}程度。"
            "固定費（保険・サブスク・通信費）の見直しから始めましょう。"))

    if ret < 5:
        advice.append(("重要", C.YELLOW, "📈 運用利回りを高める",
            f"想定利回り{ret}%は保守的です。全世界株式インデックス"
            "（eMAXIS Slim全世界株式・VT等）の長期投資で歴史的に年5〜7%の実績があります。"))

    advice.append(("優先", C.RED, "🏦 NISA・iDeCoを最大活用",
        "新NISAは年360万円（成長240万+つみたて120万）が非課税。"
        "iDeCoは掛金全額が所得控除。この2つを先に埋めてから課税口座を使いましょう。"))

    if assets < 10_000_000:
        advice.append(("重要", C.YELLOW, "🛡️ 生活防衛資金を確保",
            "投資の前に生活費6ヶ月分を現金で確保。暴落時も投資を継続できるセーフティネットになります。"))

    advice.append(("重要", C.YELLOW, "📊 ポートフォリオを分散",
        "国内株・米国株・先進国株等に分散。30代はリスク資産80〜90%でも許容範囲。"
        "年1〜2回のリバランスを忘れずに。"))

    advice.append(("任意", C.CYAN, "💼 収入源を複数持つ",
        "副業・フリーランス・投資収益など複数の収入源を持つと貯蓄率が上がります。"
        "本業スキルを活かした副業が最も効率的です。"))

    return advice


# ---- メイン表示 ----
def run_report(total_assets, monthly, ret, age, rakuten, mf=None):
    reach = reach_age(age, total_assets, monthly, ret)
    on_track = reach is not None and reach <= 40
    years_left = 40 - age
    rows = simulate(age, total_assets, monthly, ret)

    # タイトル
    print()
    print(color("  資産管理 × 40歳1億円ロードマップ", C.BOLD + C.PURPLE))
    print(hr("━"))

    # サマリー判定
    if on_track:
        yrs, mos = int(reach), round((reach % 1) * 12)
        print(color(f"  ✅ 現在のペースで {yrs}歳{mos}ヶ月頃に1億円達成見込みです！", C.GREEN))
    else:
        print(color("  ⚠️  現在のペースでは40歳までの1億円達成が難しい計算です。", C.YELLOW))

    # 基本指標
    header("📊 現状サマリー")
    print(f"  現在の総資産     : {color(fmt_yen(total_assets), C.BOLD)}")
    print(f"  目標までの差額   : {fmt_yen(max(0, TARGET - total_assets))}")
    print(f"  月間投資額       : {fmt_yen(monthly)}  （年間 {fmt_yen(monthly*12)}）")
    print(f"  想定利回り       : {ret}% / 年（複利）")
    print(f"  現在の年齢       : {age}歳  （目標まで残り{years_left}年）")
    if reach:
        yrs, mos = int(reach), round((reach % 1) * 12)
        print(f"  達成予測年齢     : {color(f'{yrs}歳{mos}ヶ月', C.GREEN if on_track else C.RED)}")
    else:
        print(f"  達成予測年齢     : {color('40歳までに到達せず', C.RED)}")
    if rakuten["gain"]:
        gc = C.GREEN if rakuten["gain"] >= 0 else C.RED
        sign = "+" if rakuten["gain"] >= 0 else ""
        print(f"  含み損益(楽天)   : {color(sign + fmt_yen(rakuten['gain']), gc)}")

    print()
    print("  1億円達成進捗")
    print("  " + progress_bar(total_assets, TARGET))

    # チャート
    header("📈 資産推移シミュレーション")
    ascii_chart(rows, reach)
    print()
    print(color(f"  ※ 利回り{ret}%・月{fmt_yen(monthly)}投資を継続した場合。実際の市場は変動します。", C.DIM + C.GRAY))

    # マイルストーン
    header("🗓  マイルストーン")
    ms = [
        (age + -(-years_left * 25 // 100), "第1チェックポイント",
         f"目標 {fmt_yen(round(TARGET*0.15))}以上。NISAを開設し積立スタート"),
        (age + -(-years_left * 50 // 100), "折り返し地点",
         f"目標 {fmt_yen(round(TARGET*0.35))}以上。NISA満額・iDeCo上限拠出中"),
        (age + -(-years_left * 75 // 100), "最終加速フェーズ",
         f"目標 {fmt_yen(round(TARGET*0.65))}以上。複利効果が本格化"),
        (40, "🎯 目標達成",
         "1億円達成見込み！" if on_track else "投資額増額または利回り改善が必要"),
    ]
    for yr, label, desc in ms:
        if yr < age:
            continue
        print(f"  {color(f'{yr:>2}歳', C.BLUE + C.BOLD)}  {color(label, C.BOLD)}")
        print(f"        {color(desc, C.GRAY)}")

    # アドバイス
    header("💡 個別アドバイス")
    for tag, tag_c, title, body in generate_advice(total_assets, monthly, ret, age, reach, on_track):
        print(f"  {color(f'[{tag}]', tag_c)} {color(title, C.BOLD)}")
        # 本文を折り返し
        line = "      "
        for word in re.findall(r"[^、。]+[、。]?", body):
            if len(line) + len(word) > 70:
                print(color(line, C.GRAY))
                line = "      "
            line += word
        if line.strip():
            print(color(line, C.GRAY))
        print()

    # 資産内訳（マネーフォワード）
    if mf and mf.get("categories"):
        header("🧩 資産内訳（マネーフォワード）")
        cats = mf["categories"]
        cat_total = sum(c["amount"] for c in cats) or 1
        for c in cats:
            pct = c["amount"] / cat_total * 100
            barlen = round(pct / 100 * 24)
            bar = color("█" * barlen, C.PURPLE) + color("░" * (24 - barlen), C.GRAY)
            print(f"  {c['name']:<14} {bar} {pct:5.1f}%  {color(fmt_yen(c['amount']), C.BLUE)}")

    # 保有資産
    if rakuten["holdings"]:
        header("💼 保有資産（楽天証券）")
        for h in rakuten["holdings"]:
            name = h["name"][:30]
            print(f"  {name:<32} {color(fmt_yen(h['amount']), C.BLUE):>}")
        if rakuten["total"]:
            print("  " + color("─" * 44, C.GRAY))
            print(f"  {'評価額合計':<32} {color(fmt_yen(rakuten['total']), C.BOLD + C.BLUE)}")

    print()
    print(hr("━"))
    print()


# ---- 入力取得 ----
def read_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(color(f"ファイルを読めません: {path} ({e})", C.RED))
        return ""


def interactive_input():
    print(color("\n対話モード — 各項目を入力してください（Enterでスキップ可）\n", C.CYAN))
    try:
        age = input("現在の年齢 [32]: ").strip() or "32"
        monthly = input("月間貯蓄・投資額（円） [100000]: ").strip() or "100000"
        ret = input("想定年間利回り（%） [5]: ").strip() or "5"
        assets = input("現在の総資産（万円、データ貼付時は空欄でOK）: ").strip()
        print(color("\nマネーフォワードのデータを貼り付け（終わったら空行でEnter）:", C.CYAN))
        mf_lines = []
        while True:
            try:
                ln = input()
            except EOFError:
                break
            if ln == "":
                break
            mf_lines.append(ln)
        print(color("楽天証券のデータを貼り付け（終わったら空行でEnter）:", C.CYAN))
        rk_lines = []
        while True:
            try:
                ln = input()
            except EOFError:
                break
            if ln == "":
                break
            rk_lines.append(ln)
    except (KeyboardInterrupt, EOFError):
        print("\n中断しました。")
        sys.exit(0)
    return {
        "age": int(age), "monthly": int(monthly), "ret": float(ret),
        "assets": assets, "mf": "\n".join(mf_lines), "rakuten": "\n".join(rk_lines),
    }


def main():
    p = argparse.ArgumentParser(description="40歳1億円ロードマップ CLI")
    p.add_argument("--mf", help="マネーフォワードのデータファイル")
    p.add_argument("--rakuten", help="楽天証券のデータファイル")
    p.add_argument("--age", type=int, help="現在の年齢")
    p.add_argument("--monthly", type=int, help="月間投資額（円）")
    p.add_argument("--return", dest="ret", type=float, help="想定年間利回り（%%）")
    p.add_argument("--assets", type=float, help="現在の総資産（万円）")
    args = p.parse_args()

    # 引数が何もなければ対話モード
    no_args = not any([args.mf, args.rakuten, args.age, args.monthly, args.ret, args.assets])
    if no_args:
        data = interactive_input()
        age, monthly, ret = data["age"], data["monthly"], data["ret"]
        mf_text, rk_text = data["mf"], data["rakuten"]
        manual_assets = data["assets"]
    else:
        age = args.age or 32
        monthly = args.monthly or 100000
        ret = args.ret if args.ret is not None else 5.0
        mf_text = read_file(args.mf) if args.mf else ""
        rk_text = read_file(args.rakuten) if args.rakuten else ""
        manual_assets = str(args.assets) if args.assets else ""

    mf = parse_moneyforward(mf_text)
    rakuten = parse_rakuten(rk_text)

    if manual_assets:
        total_assets = float(manual_assets.replace(",", "")) * 10_000
    else:
        total_assets = max(mf["total"], rakuten["total"])
        if not total_assets:
            total_assets = mf["total"] or rakuten["total"] or 0

    if total_assets <= 0:
        print(color("\n⚠️  総資産が取得できませんでした。--assets で万円単位の総資産を指定するか、"
                     "データを貼り付けてください。\n", C.YELLOW))
        sys.exit(1)

    run_report(total_assets, monthly, ret, age, rakuten, mf)


if __name__ == "__main__":
    main()

"""
マンション価格モニタリングダッシュボード
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import csv
import os
import random
from datetime import datetime, timedelta
import threading


DATA_FILE = "mansion_data.json"

SAMPLE_AREAS = ["港区", "渋谷区", "新宿区", "目黒区", "品川区", "中央区", "千代田区", "豊島区", "世田谷区", "文京区"]
SAMPLE_BUILDINGS = {
    "港区": ["パークタワー芝浦", "ザ・ベイリーフ", "グランドパーク白金"],
    "渋谷区": ["パークコート渋谷", "代官山アドレス", "恵比寿ガーデンテラス"],
    "新宿区": ["新宿パークタワー", "野村不動産西新宿", "ワールドシティタワー"],
    "目黒区": ["目黒雅叙園", "MID GARDEN目黒", "パークハウス中目黒"],
    "品川区": ["大崎ウィズタワー", "品川シーサイド", "ザ・タワー大崎"],
    "中央区": ["勝どきザタワー", "晴海トリトン", "月島タワー"],
    "千代田区": ["ザ・パークハウス千代田", "麹町パークマンション", "九段北の杜"],
    "豊島区": ["ルーセントタワー池袋", "グランエミオ目白", "Brillia Tower池袋"],
    "世田谷区": ["ライオンズ三軒茶屋", "パークシティ武蔵野", "クレッセント自由が丘"],
    "文京区": ["文京ガーデン", "本郷パークハウス", "ブリリア文京後楽園"],
}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return generate_sample_data()


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_sample_data():
    data = []
    base_prices = {
        "港区": 18000, "渋谷区": 16000, "新宿区": 13000, "目黒区": 14000,
        "品川区": 12000, "中央区": 13500, "千代田区": 17000, "豊島区": 11000,
        "世田谷区": 10000, "文京区": 12500,
    }
    record_id = 1
    today = datetime.now()
    for area, buildings in SAMPLE_BUILDINGS.items():
        for building in buildings:
            base = base_prices[area]
            for i in range(6):
                date = (today - timedelta(days=30 * i)).strftime("%Y-%m-%d")
                price = base * random.uniform(0.9, 1.1)
                size = random.uniform(40, 120)
                floor = random.randint(1, 30)
                data.append({
                    "id": record_id,
                    "area": area,
                    "building": building,
                    "date": date,
                    "price_per_sqm": round(price, 0),
                    "total_price": round(price * size / 10000, 0),
                    "size": round(size, 1),
                    "floor": floor,
                    "status": random.choice(["販売中", "販売中", "成約済", "販売中"]),
                })
                record_id += 1
    return data


class MansionDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("マンション価格モニタリングダッシュボード")
        self.geometry("1200x750")
        self.configure(bg="#1e1e2e")
        self.resizable(True, True)

        self.data = load_data()
        self.filtered_data = list(self.data)
        self.sort_col = "date"
        self.sort_asc = False

        self._build_ui()
        self._refresh_stats()
        self._populate_table()

    def _build_ui(self):
        self._apply_styles()

        # Header
        header = tk.Frame(self, bg="#181825", pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="🏢 マンション価格モニタリング", font=("Helvetica", 18, "bold"),
                 bg="#181825", fg="#cdd6f4").pack(side=tk.LEFT, padx=20)
        self.last_updated = tk.Label(header, text="", font=("Helvetica", 10),
                                     bg="#181825", fg="#6c7086")
        self.last_updated.pack(side=tk.RIGHT, padx=20)
        self._update_timestamp()

        # Stats bar
        self.stats_frame = tk.Frame(self, bg="#1e1e2e", pady=10)
        self.stats_frame.pack(fill=tk.X, padx=20)

        # Filter bar
        filter_frame = tk.Frame(self, bg="#1e1e2e", pady=5)
        filter_frame.pack(fill=tk.X, padx=20)

        tk.Label(filter_frame, text="エリア:", bg="#1e1e2e", fg="#cdd6f4").pack(side=tk.LEFT)
        self.area_var = tk.StringVar(value="すべて")
        areas = ["すべて"] + SAMPLE_AREAS
        self.area_combo = ttk.Combobox(filter_frame, textvariable=self.area_var,
                                       values=areas, width=12, state="readonly")
        self.area_combo.pack(side=tk.LEFT, padx=(4, 16))
        self.area_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        tk.Label(filter_frame, text="ステータス:", bg="#1e1e2e", fg="#cdd6f4").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="すべて")
        self.status_combo = ttk.Combobox(filter_frame, textvariable=self.status_var,
                                         values=["すべて", "販売中", "成約済"], width=8, state="readonly")
        self.status_combo.pack(side=tk.LEFT, padx=(4, 16))
        self.status_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        tk.Label(filter_frame, text="キーワード:", bg="#1e1e2e", fg="#cdd6f4").pack(side=tk.LEFT)
        self.kw_var = tk.StringVar()
        kw_entry = tk.Entry(filter_frame, textvariable=self.kw_var, width=18,
                            bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4",
                            relief=tk.FLAT, bd=4)
        kw_entry.pack(side=tk.LEFT, padx=(4, 16))
        self.kw_var.trace_add("write", lambda *_: self._apply_filter())

        btn_frame = tk.Frame(filter_frame, bg="#1e1e2e")
        btn_frame.pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="+ 追加", command=self._open_add_dialog,
                  bg="#89b4fa", fg="#1e1e2e", relief=tk.FLAT, padx=10, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="CSV出力", command=self._export_csv,
                  bg="#a6e3a1", fg="#1e1e2e", relief=tk.FLAT, padx=10, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="グラフ表示", command=self._show_chart,
                  bg="#fab387", fg="#1e1e2e", relief=tk.FLAT, padx=10, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=4)

        # Table
        table_frame = tk.Frame(self, bg="#1e1e2e")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        cols = ("id", "area", "building", "date", "price_per_sqm", "total_price", "size", "floor", "status")
        headers = ("ID", "エリア", "物件名", "日付", "単価(万円/㎡)", "総額(万円)", "面積(㎡)", "階", "ステータス")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=22)
        widths = [40, 80, 180, 90, 110, 90, 80, 50, 80]
        for col, hdr, w in zip(cols, headers, widths):
            self.tree.heading(col, text=hdr, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._on_row_double_click)

        # Status bar
        self.status_label = tk.Label(self, text="", bg="#181825", fg="#6c7086",
                                     anchor=tk.W, padx=10)
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#313244", foreground="#cdd6f4",
                        fieldbackground="#313244", rowheight=26, font=("Helvetica", 10))
        style.configure("Treeview.Heading", background="#45475a", foreground="#cdd6f4",
                        font=("Helvetica", 10, "bold"), relief=tk.FLAT)
        style.map("Treeview", background=[("selected", "#89b4fa")], foreground=[("selected", "#1e1e2e")])
        style.configure("TCombobox", fieldbackground="#313244", background="#313244",
                        foreground="#cdd6f4", selectbackground="#45475a")
        style.configure("TScrollbar", background="#45475a", troughcolor="#1e1e2e")

    def _update_timestamp(self):
        self.last_updated.config(text=f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()

        active = [r for r in self.filtered_data if r["status"] == "販売中"]
        prices = [r["price_per_sqm"] for r in self.filtered_data]
        avg_price = sum(prices) / len(prices) if prices else 0
        max_price = max(prices) if prices else 0
        min_price = min(prices) if prices else 0

        stats = [
            ("総件数", f"{len(self.filtered_data):,}件", "#89b4fa"),
            ("販売中", f"{len(active):,}件", "#a6e3a1"),
            ("平均単価", f"{avg_price:,.0f}万円/㎡", "#f9e2af"),
            ("最高単価", f"{max_price:,.0f}万円/㎡", "#f38ba8"),
            ("最低単価", f"{min_price:,.0f}万円/㎡", "#94e2d5"),
        ]
        for label, value, color in stats:
            card = tk.Frame(self.stats_frame, bg="#313244", padx=16, pady=8, relief=tk.FLAT)
            card.pack(side=tk.LEFT, padx=8)
            tk.Label(card, text=label, bg="#313244", fg="#6c7086", font=("Helvetica", 9)).pack()
            tk.Label(card, text=value, bg="#313244", fg=color, font=("Helvetica", 14, "bold")).pack()

    def _apply_filter(self):
        area = self.area_var.get()
        status = self.status_var.get()
        kw = self.kw_var.get().strip()
        self.filtered_data = [
            r for r in self.data
            if (area == "すべて" or r["area"] == area)
            and (status == "すべて" or r["status"] == status)
            and (not kw or kw in r["building"] or kw in r["area"])
        ]
        self._refresh_stats()
        self._populate_table()

    def _sort_by(self, col):
        if self.sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col
            self.sort_asc = True
        self.filtered_data.sort(key=lambda r: r.get(col, ""), reverse=not self.sort_asc)
        self._populate_table()

    def _populate_table(self):
        self.tree.delete(*self.tree.get_children())
        tag_map = {"販売中": "active", "成約済": "sold"}
        self.tree.tag_configure("active", foreground="#a6e3a1")
        self.tree.tag_configure("sold", foreground="#6c7086")
        for r in self.filtered_data:
            tag = tag_map.get(r["status"], "")
            self.tree.insert("", tk.END, iid=str(r["id"]), values=(
                r["id"], r["area"], r["building"], r["date"],
                f"{r['price_per_sqm']:,.0f}", f"{r['total_price']:,.0f}",
                f"{r['size']:.1f}", r["floor"], r["status"],
            ), tags=(tag,))
        self.status_label.config(text=f"{len(self.filtered_data)}件表示中  （ダブルクリックで詳細）")

    def _on_row_double_click(self, event):
        item = self.tree.focus()
        if not item:
            return
        record = next((r for r in self.data if str(r["id"]) == item), None)
        if record:
            self._open_detail_dialog(record)

    def _open_detail_dialog(self, record):
        win = tk.Toplevel(self)
        win.title("物件詳細")
        win.geometry("360x320")
        win.configure(bg="#1e1e2e")
        win.grab_set()

        fields = [
            ("エリア", record["area"]),
            ("物件名", record["building"]),
            ("日付", record["date"]),
            ("単価", f"{record['price_per_sqm']:,.0f} 万円/㎡"),
            ("総額", f"{record['total_price']:,.0f} 万円"),
            ("面積", f"{record['size']:.1f} ㎡"),
            ("階", f"{record['floor']} 階"),
            ("ステータス", record["status"]),
        ]
        for label, value in fields:
            row = tk.Frame(win, bg="#1e1e2e")
            row.pack(fill=tk.X, padx=20, pady=4)
            tk.Label(row, text=label + ":", bg="#1e1e2e", fg="#6c7086",
                     width=10, anchor=tk.E).pack(side=tk.LEFT)
            tk.Label(row, text=value, bg="#1e1e2e", fg="#cdd6f4",
                     font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=8)

        tk.Button(win, text="削除", bg="#f38ba8", fg="#1e1e2e", relief=tk.FLAT,
                  padx=12, command=lambda: self._delete_record(record["id"], win)).pack(pady=12)

    def _delete_record(self, record_id, win):
        if messagebox.askyesno("確認", "この物件データを削除しますか？"):
            self.data = [r for r in self.data if r["id"] != record_id]
            save_data(self.data)
            self._apply_filter()
            win.destroy()

    def _open_add_dialog(self):
        win = tk.Toplevel(self)
        win.title("物件データ追加")
        win.geometry("380x420")
        win.configure(bg="#1e1e2e")
        win.grab_set()

        fields_def = [
            ("エリア", "combo", SAMPLE_AREAS),
            ("物件名", "entry", None),
            ("日付 (YYYY-MM-DD)", "entry", None),
            ("単価 (万円/㎡)", "entry", None),
            ("総額 (万円)", "entry", None),
            ("面積 (㎡)", "entry", None),
            ("階", "entry", None),
            ("ステータス", "combo", ["販売中", "成約済"]),
        ]
        vars_ = []
        for label, ftype, options in fields_def:
            row = tk.Frame(win, bg="#1e1e2e")
            row.pack(fill=tk.X, padx=20, pady=4)
            tk.Label(row, text=label + ":", bg="#1e1e2e", fg="#cdd6f4",
                     width=18, anchor=tk.W).pack(side=tk.LEFT)
            v = tk.StringVar()
            if ftype == "combo":
                w = ttk.Combobox(row, textvariable=v, values=options, width=14, state="readonly")
                w.current(0)
            else:
                w = tk.Entry(row, textvariable=v, width=16, bg="#313244", fg="#cdd6f4",
                             insertbackground="#cdd6f4", relief=tk.FLAT, bd=4)
                if label.startswith("日付"):
                    v.set(datetime.now().strftime("%Y-%m-%d"))
            w.pack(side=tk.LEFT)
            vars_.append(v)

        def submit():
            try:
                area, building, date, price_sqm, total, size, floor, status = [v.get() for v in vars_]
                new_id = max((r["id"] for r in self.data), default=0) + 1
                self.data.append({
                    "id": new_id, "area": area, "building": building, "date": date,
                    "price_per_sqm": float(price_sqm), "total_price": float(total),
                    "size": float(size), "floor": int(floor), "status": status,
                })
                save_data(self.data)
                self._apply_filter()
                win.destroy()
            except Exception as e:
                messagebox.showerror("入力エラー", f"正しく入力してください。\n{e}", parent=win)

        tk.Button(win, text="追加", bg="#89b4fa", fg="#1e1e2e", relief=tk.FLAT,
                  padx=16, font=("Helvetica", 11, "bold"), command=submit).pack(pady=14)

    def _export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="mansion_data.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.filtered_data[0].keys() if self.filtered_data else [])
            writer.writeheader()
            writer.writerows(self.filtered_data)
        messagebox.showinfo("完了", f"CSVを出力しました:\n{path}")

    def _show_chart(self):
        win = tk.Toplevel(self)
        win.title("エリア別平均単価グラフ")
        win.geometry("700x420")
        win.configure(bg="#1e1e2e")

        area_prices = {}
        for r in self.filtered_data:
            area_prices.setdefault(r["area"], []).append(r["price_per_sqm"])
        if not area_prices:
            messagebox.showinfo("情報", "データがありません")
            win.destroy()
            return

        averages = {a: sum(p) / len(p) for a, p in area_prices.items()}
        max_val = max(averages.values())

        canvas = tk.Canvas(win, bg="#1e1e2e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        colors = ["#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#94e2d5",
                  "#cba6f7", "#fab387", "#eba0ac", "#b4befe", "#74c7ec"]

        def draw(event=None):
            canvas.delete("all")
            W = canvas.winfo_width()
            H = canvas.winfo_height()
            margin_l, margin_r, margin_t, margin_b = 60, 20, 20, 80
            areas = list(averages.keys())
            n = len(areas)
            bar_w = max(10, (W - margin_l - margin_r) // n - 10)
            chart_h = H - margin_t - margin_b

            for i, (area, avg) in enumerate(averages.items()):
                x = margin_l + i * ((W - margin_l - margin_r) // n) + 5
                bar_h = int(avg / max_val * chart_h * 0.9)
                y0 = H - margin_b - bar_h
                y1 = H - margin_b
                color = colors[i % len(colors)]
                canvas.create_rectangle(x, y0, x + bar_w, y1, fill=color, outline="")
                canvas.create_text(x + bar_w // 2, y0 - 8,
                                   text=f"{avg:,.0f}", fill="#cdd6f4", font=("Helvetica", 8))
                canvas.create_text(x + bar_w // 2, H - margin_b + 12,
                                   text=area, fill="#cdd6f4", font=("Helvetica", 9), angle=30, anchor=tk.N)
            canvas.create_text(W // 2, 8, text="エリア別平均単価 (万円/㎡)",
                               fill="#cdd6f4", font=("Helvetica", 11, "bold"))

        canvas.bind("<Configure>", draw)
        win.after(100, draw)


if __name__ == "__main__":
    app = MansionDashboard()
    app.mainloop()

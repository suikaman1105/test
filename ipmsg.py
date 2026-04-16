"""LAN IP Messenger with supervisor approval workflow.

Features:
- UDP broadcast user discovery
- TCP messaging
- File transfer with supervisor approval (with comment)
- Drag & drop upload / download (requires tkinterdnd2)
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore


UDP_PORT = 2425
TCP_PORT = 2426
BROADCAST_INTERVAL = 5.0
USER_TIMEOUT = 15.0
BUFFER_SIZE = 65536
DOWNLOAD_DIR = Path.home() / "Downloads" / "ipmsg"


# ---------- Protocol ----------
# Each TCP message: 4-byte big-endian length + JSON header + optional binary body.
# Header types:
#   "msg"            -> chat message
#   "file_request"   -> sender -> supervisor: file pending approval (binary body = file)
#   "file_deliver"   -> supervisor -> recipient: approved file (binary body = file)
#   "approval_result"-> supervisor -> sender: approved/denied notification


@dataclass
class User:
    user_id: str
    name: str
    ip: str
    last_seen: float = field(default_factory=time.time)


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def send_framed(sock: socket.socket, header: dict, body: bytes = b"") -> None:
    header_bytes = json.dumps(header).encode("utf-8")
    sock.sendall(struct.pack(">II", len(header_bytes), len(body)))
    sock.sendall(header_bytes)
    if body:
        sock.sendall(body)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(min(BUFFER_SIZE, remaining))
        if not chunk:
            raise ConnectionError("socket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_framed(sock: socket.socket) -> tuple[dict, bytes]:
    head_len, body_len = struct.unpack(">II", recv_exact(sock, 8))
    header = json.loads(recv_exact(sock, head_len).decode("utf-8"))
    body = recv_exact(sock, body_len) if body_len else b""
    return header, body


# ---------- Network layer ----------
class Network:
    def __init__(self, user_id: str, name: str, on_event: Callable[[str, dict], None]):
        self.user_id = user_id
        self.name = name
        self.on_event = on_event
        self.local_ip = get_local_ip()
        self.users: dict[str, User] = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._udp_listener, daemon=True).start()
        threading.Thread(target=self._udp_broadcaster, daemon=True).start()
        threading.Thread(target=self._tcp_listener, daemon=True).start()
        threading.Thread(target=self._user_pruner, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    # ---- UDP discovery ----
    def _udp_broadcaster(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({"user_id": self.user_id, "name": self.name, "tcp_port": TCP_PORT}).encode()
        while not self._stop.is_set():
            try:
                sock.sendto(payload, ("<broadcast>", UDP_PORT))
            except Exception:
                pass
            self._stop.wait(BROADCAST_INTERVAL)

    def _udp_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", UDP_PORT))
        except OSError as e:
            self.on_event("error", {"message": f"UDP bind failed: {e}"})
            return
        sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                continue
            try:
                info = json.loads(data.decode())
            except Exception:
                continue
            uid = info.get("user_id")
            if not uid or uid == self.user_id:
                continue
            with self._lock:
                user = self.users.get(uid)
                if user is None:
                    user = User(user_id=uid, name=info.get("name", "?"), ip=addr[0])
                    self.users[uid] = user
                    self.on_event("user_added", {"user": user})
                else:
                    user.name = info.get("name", user.name)
                    user.ip = addr[0]
                    user.last_seen = time.time()

    def _user_pruner(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(5.0)
            now = time.time()
            removed = []
            with self._lock:
                for uid, u in list(self.users.items()):
                    if now - u.last_seen > USER_TIMEOUT:
                        removed.append(u)
                        del self.users[uid]
            for u in removed:
                self.on_event("user_removed", {"user": u})

    def get_users(self) -> list[User]:
        with self._lock:
            return list(self.users.values())

    def find_user(self, user_id: str) -> User | None:
        with self._lock:
            return self.users.get(user_id)

    # ---- TCP ----
    def _tcp_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", TCP_PORT))
        except OSError as e:
            self.on_event("error", {"message": f"TCP bind failed: {e}"})
            return
        sock.listen(8)
        sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except Exception:
                continue
            threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            header, body = recv_framed(conn)
            self.on_event("incoming", {"header": header, "body": body})
        except Exception as e:
            self.on_event("error", {"message": f"recv failed: {e}"})
        finally:
            conn.close()

    def send(self, target: User, header: dict, body: bytes = b"") -> bool:
        try:
            with socket.create_connection((target.ip, TCP_PORT), timeout=10) as s:
                send_framed(s, header, body)
            return True
        except Exception as e:
            self.on_event("error", {"message": f"send to {target.name} failed: {e}"})
            return False


# ---------- GUI ----------
class App:
    def __init__(self, name: str):
        self.user_id = uuid.uuid4().hex[:12]
        self.name = name
        self.net = Network(self.user_id, name, self._on_net_event)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # pending approvals: key = transfer_id, value = dict
        self.pending: dict[str, dict] = {}
        # received files awaiting drag-out: key = transfer_id, value = local path
        self.received_files: dict[str, Path] = {}

        self._build_ui()
        self.net.start()
        self.root.after(2000, self._refresh_users)

    def _build_ui(self) -> None:
        if DND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        self.root.title(f"IPMsg - {self.name} ({self.user_id})")
        self.root.geometry("900x600")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)

        # --- Tab 1: chat & send ---
        tab_chat = ttk.Frame(nb)
        nb.add(tab_chat, text="メッセージ / 送信")

        left = ttk.Frame(tab_chat)
        left.pack(side="left", fill="y", padx=4, pady=4)
        ttk.Label(left, text="ユーザー一覧").pack(anchor="w")
        self.user_list = tk.Listbox(left, width=28, height=20)
        self.user_list.pack(fill="y", expand=True)

        right = ttk.Frame(tab_chat)
        right.pack(side="right", fill="both", expand=True, padx=4, pady=4)

        ttk.Label(right, text="ログ").pack(anchor="w")
        self.log = tk.Text(right, height=18, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        send_frame = ttk.Frame(right)
        send_frame.pack(fill="x", pady=4)
        self.msg_entry = ttk.Entry(send_frame)
        self.msg_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(send_frame, text="メッセージ送信", command=self._send_message).pack(side="left", padx=4)

        drop_frame = ttk.LabelFrame(right, text="ファイル送信 (D&D または ボタン)")
        drop_frame.pack(fill="x", pady=4)
        self.drop_label = tk.Label(drop_frame, text="ここにファイルをドロップ", relief="ridge", height=3, bg="#eef")
        self.drop_label.pack(fill="x", padx=4, pady=4)
        if DND_AVAILABLE:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_file_drop)
        ttk.Button(drop_frame, text="ファイル選択...", command=self._pick_file).pack(pady=2)

        # --- Tab 2: approval queue ---
        tab_appr = ttk.Frame(nb)
        nb.add(tab_appr, text="承認待ち")
        self.approval_tree = ttk.Treeview(
            tab_appr, columns=("from", "to", "file", "size", "comment"), show="headings"
        )
        for col, w in [("from", 120), ("to", 120), ("file", 220), ("size", 80), ("comment", 260)]:
            self.approval_tree.heading(col, text=col)
            self.approval_tree.column(col, width=w)
        self.approval_tree.pack(fill="both", expand=True, padx=4, pady=4)

        btns = ttk.Frame(tab_appr)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="承認 (転送)", command=self._approve_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="否認", command=lambda: self._deny_selected()).pack(side="left", padx=4)
        ttk.Button(btns, text="プレビュー", command=self._preview_selected).pack(side="left", padx=4)

        # --- Tab 3: received files ---
        tab_recv = ttk.Frame(nb)
        nb.add(tab_recv, text="受信ファイル")
        ttk.Label(tab_recv, text=f"保存先: {DOWNLOAD_DIR}").pack(anchor="w", padx=4, pady=2)
        self.recv_tree = ttk.Treeview(tab_recv, columns=("from", "file", "path"), show="headings")
        for col, w in [("from", 140), ("file", 240), ("path", 460)]:
            self.recv_tree.heading(col, text=col)
            self.recv_tree.column(col, width=w)
        self.recv_tree.pack(fill="both", expand=True, padx=4, pady=4)
        ttk.Button(tab_recv, text="フォルダを開く", command=self._open_download_dir).pack(pady=4)

    # ---- helpers ----
    def _log(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_users(self) -> None:
        users = sorted(self.net.get_users(), key=lambda u: u.name)
        self.user_list.delete(0, "end")
        self._user_index: list[User] = []
        for u in users:
            self.user_list.insert("end", f"{u.name}  ({u.ip})")
            self._user_index.append(u)
        self.root.after(2000, self._refresh_users)

    def _selected_user(self) -> User | None:
        sel = self.user_list.curselection()
        if not sel:
            messagebox.showwarning("選択なし", "宛先ユーザーを選択してください")
            return None
        return self._user_index[sel[0]]

    def _pick_supervisor(self, exclude: set[str]) -> User | None:
        users = [u for u in self.net.get_users() if u.user_id not in exclude]
        if not users:
            messagebox.showwarning("上長なし", "他のユーザーが見つかりません")
            return None
        win = tk.Toplevel(self.root)
        win.title("上長を選択")
        win.geometry("300x300")
        ttk.Label(win, text="承認を依頼する上長を選択").pack(anchor="w", padx=8, pady=4)
        lb = tk.Listbox(win)
        for u in users:
            lb.insert("end", f"{u.name}  ({u.ip})")
        lb.pack(fill="both", expand=True, padx=8, pady=4)
        result: dict = {"user": None}

        def ok() -> None:
            sel = lb.curselection()
            if sel:
                result["user"] = users[sel[0]]
                win.destroy()

        ttk.Button(win, text="OK", command=ok).pack(pady=4)
        win.transient(self.root)
        win.grab_set()
        self.root.wait_window(win)
        return result["user"]

    # ---- send actions ----
    def _send_message(self) -> None:
        target = self._selected_user()
        if not target:
            return
        text = self.msg_entry.get().strip()
        if not text:
            return
        ok = self.net.send(target, {"type": "msg", "from_id": self.user_id, "from_name": self.name, "text": text})
        if ok:
            self._log(f"-> {target.name}: {text}")
            self.msg_entry.delete(0, "end")

    def _on_file_drop(self, event) -> None:
        paths = self._parse_drop(event.data)
        for p in paths:
            self._initiate_file_send(Path(p))

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename()
        if path:
            self._initiate_file_send(Path(path))

    @staticmethod
    def _parse_drop(data: str) -> list[str]:
        # tkinterdnd2 returns paths possibly wrapped in {} when they contain spaces
        out, buf, in_brace = [], "", False
        for ch in data:
            if ch == "{":
                in_brace = True
            elif ch == "}":
                in_brace = False
                out.append(buf)
                buf = ""
            elif ch == " " and not in_brace:
                if buf:
                    out.append(buf)
                    buf = ""
            else:
                buf += ch
        if buf:
            out.append(buf)
        return out

    def _initiate_file_send(self, path: Path) -> None:
        if not path.is_file():
            messagebox.showerror("エラー", f"ファイルではありません: {path}")
            return
        recipient = self._selected_user()
        if not recipient:
            return
        supervisor = self._pick_supervisor(exclude={self.user_id, recipient.user_id})
        if not supervisor:
            return
        comment = simpledialog.askstring("コメント", "上長への申請コメント:", parent=self.root) or ""
        try:
            data = path.read_bytes()
        except Exception as e:
            messagebox.showerror("読込失敗", str(e))
            return
        transfer_id = uuid.uuid4().hex
        header = {
            "type": "file_request",
            "transfer_id": transfer_id,
            "from_id": self.user_id,
            "from_name": self.name,
            "to_id": recipient.user_id,
            "to_name": recipient.name,
            "filename": path.name,
            "size": len(data),
            "comment": comment,
        }
        if self.net.send(supervisor, header, data):
            self._log(f"申請: {path.name} -> {recipient.name} (承認: {supervisor.name})")
        else:
            self._log(f"申請失敗: {path.name}")

    # ---- approval actions ----
    def _approve_selected(self) -> None:
        item = self._current_approval()
        if not item:
            return
        transfer_id, info = item
        recipient = self.net.find_user(info["to_id"])
        sender = self.net.find_user(info["from_id"])
        if not recipient:
            messagebox.showerror("エラー", "宛先ユーザーがオフラインです")
            return
        deliver_header = {
            "type": "file_deliver",
            "transfer_id": transfer_id,
            "from_id": info["from_id"],
            "from_name": info["from_name"],
            "approver_id": self.user_id,
            "approver_name": self.name,
            "filename": info["filename"],
            "comment": info.get("comment", ""),
        }
        if self.net.send(recipient, deliver_header, info["data"]):
            self._log(f"承認->転送: {info['filename']} -> {recipient.name}")
            if sender:
                self.net.send(sender, {
                    "type": "approval_result",
                    "transfer_id": transfer_id,
                    "approved": True,
                    "approver_name": self.name,
                    "filename": info["filename"],
                    "note": "",
                })
            self._remove_approval(transfer_id)

    def _deny_selected(self) -> None:
        item = self._current_approval()
        if not item:
            return
        transfer_id, info = item
        note = simpledialog.askstring("否認理由", "理由 (任意):", parent=self.root) or ""
        sender = self.net.find_user(info["from_id"])
        if sender:
            self.net.send(sender, {
                "type": "approval_result",
                "transfer_id": transfer_id,
                "approved": False,
                "approver_name": self.name,
                "filename": info["filename"],
                "note": note,
            })
        self._log(f"否認: {info['filename']} (送信者: {info['from_name']})")
        self._remove_approval(transfer_id)

    def _preview_selected(self) -> None:
        item = self._current_approval()
        if not item:
            return
        _, info = item
        data = info["data"]
        win = tk.Toplevel(self.root)
        win.title(f"プレビュー: {info['filename']}")
        win.geometry("600x500")
        ttk.Label(win, text=f"送信者: {info['from_name']} / 宛先: {info['to_name']}").pack(anchor="w", padx=4)
        ttk.Label(win, text=f"コメント: {info.get('comment', '')}").pack(anchor="w", padx=4)
        text = tk.Text(win, wrap="word")
        text.pack(fill="both", expand=True)
        try:
            preview = data[:8192].decode("utf-8")
        except UnicodeDecodeError:
            preview = f"<binary file, {len(data)} bytes>\n\n" + data[:512].hex()
        text.insert("1.0", preview)
        text.configure(state="disabled")

    def _current_approval(self) -> tuple[str, dict] | None:
        sel = self.approval_tree.selection()
        if not sel:
            messagebox.showwarning("選択なし", "承認待ち項目を選択してください")
            return None
        transfer_id = sel[0]
        return transfer_id, self.pending[transfer_id]

    def _remove_approval(self, transfer_id: str) -> None:
        self.pending.pop(transfer_id, None)
        if self.approval_tree.exists(transfer_id):
            self.approval_tree.delete(transfer_id)

    def _open_download_dir(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(DOWNLOAD_DIR)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{DOWNLOAD_DIR}"')
            else:
                os.system(f'xdg-open "{DOWNLOAD_DIR}" &')
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    # ---- network event dispatcher (runs on net thread; marshal to UI) ----
    def _on_net_event(self, kind: str, data: dict) -> None:
        self.root.after(0, lambda: self._handle_event(kind, data))

    def _handle_event(self, kind: str, data: dict) -> None:
        if kind == "user_added":
            self._log(f"ユーザー検出: {data['user'].name} ({data['user'].ip})")
        elif kind == "user_removed":
            self._log(f"ユーザー離脱: {data['user'].name}")
        elif kind == "error":
            self._log(f"[ERR] {data['message']}")
        elif kind == "incoming":
            self._handle_incoming(data["header"], data["body"])

    def _handle_incoming(self, header: dict, body: bytes) -> None:
        t = header.get("type")
        if t == "msg":
            self._log(f"<- {header.get('from_name', '?')}: {header.get('text', '')}")
        elif t == "file_request":
            transfer_id = header["transfer_id"]
            self.pending[transfer_id] = {
                "from_id": header["from_id"],
                "from_name": header["from_name"],
                "to_id": header["to_id"],
                "to_name": header["to_name"],
                "filename": header["filename"],
                "comment": header.get("comment", ""),
                "data": body,
            }
            self.approval_tree.insert(
                "", "end", iid=transfer_id,
                values=(header["from_name"], header["to_name"], header["filename"],
                        f"{header['size']}B", header.get("comment", "")),
            )
            self._log(f"承認依頼受信: {header['filename']} ({header['from_name']} -> {header['to_name']})")
        elif t == "file_deliver":
            transfer_id = header["transfer_id"]
            safe_name = Path(header["filename"]).name
            dest = DOWNLOAD_DIR / f"{transfer_id[:8]}_{safe_name}"
            try:
                dest.write_bytes(body)
            except Exception as e:
                self._log(f"[ERR] 保存失敗: {e}")
                return
            self.received_files[transfer_id] = dest
            self.recv_tree.insert("", "end", iid=transfer_id,
                                  values=(header.get("from_name", "?"), safe_name, str(dest)))
            self._log(f"ファイル受信: {safe_name} (承認: {header.get('approver_name', '?')}) -> {dest}")
        elif t == "approval_result":
            status = "承認" if header.get("approved") else "否認"
            note = header.get("note", "")
            extra = f" ({note})" if note else ""
            self._log(f"[{status}] {header.get('filename')} by {header.get('approver_name')}{extra}")

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.net.stop()


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("USER", "user")
    if not DND_AVAILABLE:
        print("warning: tkinterdnd2 not installed -- drag & drop disabled. Install with: pip install tkinterdnd2")
    app = App(name)
    app.run()


if __name__ == "__main__":
    main()

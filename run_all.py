#!/usr/bin/env python3
"""
Master launcher — chạy Turnstile + 3 vote scripts, hiển thị dashboard tổng hợp.
Usage: python3 run_all.py
"""
import subprocess
import threading
import time
import re
import os
import sys
import signal
from collections import deque, defaultdict

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.console import Console, Group
from rich.columns import Columns
from rich import box

CWD = os.path.dirname(os.path.abspath(__file__))

ALL_SCRIPTS = [
    {"key": "turnstile", "cmd": "Turnstile_MultiWorker.py", "title": "🔑 Turnstile", "env_key": "NUM_TABS",    "default": 5},
    {"key": "newway",    "cmd": "NewWay.py",                "title": "📧 NewWay",    "env_key": "NUM_WORKERS", "default": 7},
    {"key": "mmo",       "cmd": "Reg_Login_Vote_MMO.py",    "title": "📧 MMO",       "env_key": "NUM_WORKERS", "default": 0},
    {"key": "smv",       "cmd": "Reg_Login_Vote.py",        "title": "📧 SMV",       "env_key": "NUM_WORKERS", "default": 7},
]


def interactive_menu():
    """Menu tương tác cho phép chọn script và số luồng."""
    console = Console()
    console.print("\n[bold blue]═══════════════════════════════════════════[/bold blue]")
    console.print("[bold blue]       ELLE VOTE — CẤU HÌNH LAUNCHER       [/bold blue]")
    console.print("[bold blue]═══════════════════════════════════════════[/bold blue]\n")

    enabled = {}
    workers = {}

    for s in ALL_SCRIPTS:
        enabled[s["key"]] = True
        workers[s["key"]] = s["default"]

    while True:
        # Hiện bảng config
        tbl = Table(box=box.ROUNDED, title="Cấu hình hiện tại", border_style="cyan")
        tbl.add_column("#", width=3, justify="center")
        tbl.add_column("Script", width=16)
        tbl.add_column("ON/OFF", width=8, justify="center")
        tbl.add_column("Luồng", width=8, justify="center")

        for i, s in enumerate(ALL_SCRIPTS):
            on = "[bold green]✅ ON[/bold green]" if enabled[s["key"]] else "[dim red]❌ OFF[/dim red]"
            tbl.add_row(str(i + 1), s["title"], on, str(workers[s["key"]]))

        console.print(tbl)
        console.print()
        console.print("[dim]Lệnh:[/dim]  [bold]1-4[/bold] bật/tắt script  │  [bold]w1-w4 <số>[/bold] đặt luồng  │  [bold]y[/bold] chạy  │  [bold]q[/bold] thoát")
        console.print("[dim]Ví dụ:[/dim]  [cyan]w1 12[/cyan] → Turnstile 12 tabs  │  [cyan]3[/cyan] → tắt/bật MMO")

        cmd = input("\n> ").strip().lower()

        if cmd == "y":
            break
        elif cmd == "q":
            sys.exit(0)
        elif cmd in ["1", "2", "3", "4"]:
            idx = int(cmd) - 1
            key = ALL_SCRIPTS[idx]["key"]
            enabled[key] = not enabled[key]
            state = "BẬT" if enabled[key] else "TẮT"
            console.print(f"  → {ALL_SCRIPTS[idx]['title']} đã {state}")
        elif cmd.startswith("w") and len(cmd.split()) == 2:
            try:
                parts = cmd.split()
                idx = int(parts[0][1:]) - 1
                num = int(parts[1])
                if 0 <= idx < 4 and num > 0:
                    key = ALL_SCRIPTS[idx]["key"]
                    workers[key] = num
                    console.print(f"  → {ALL_SCRIPTS[idx]['title']} = {num} luồng")
                else:
                    console.print("[red]  Số không hợp lệ[/red]")
            except ValueError:
                console.print("[red]  Cú pháp: w<1-4> <số>  Ví dụ: w1 12[/red]")
        else:
            console.print("[red]  Lệnh không hợp lệ[/red]")

    # Build danh sách scripts được chọn
    selected = []
    for s in ALL_SCRIPTS:
        if enabled[s["key"]]:
            selected.append({**s, "num": workers[s["key"]]})

    if not selected:
        console.print("[red]Không có script nào được chọn![/red]")
        sys.exit(1)

    # Hiện tóm tắt
    console.print("\n[bold green]▶ KHỞI CHẠY:[/bold green]")
    for s in selected:
        console.print(f"  {s['title']}: {s['num']} luồng")
    console.print()

    return selected


class MasterDashboard:
    def __init__(self, scripts):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.processes = {}
        self.running = True
        self.scripts = scripts

        self.stats = {}
        for s in scripts:
            self.stats[s["key"]] = {
                "title": s["title"],
                "success": 0,
                "fail": 0,
                "tokens": 0,
                "workers": {},       # {wid: status_str}
                "w_success": {},     # {wid: count}
                "w_fail": {},        # {wid: count}
                "logs": deque(maxlen=3),
            }

        self.console = Console(force_terminal=True)
        self.live = Live(
            self._render(), console=self.console,
            refresh_per_second=2, screen=True,
        )

    def start(self):
        self.live.start()
        for s in self.scripts:
            env = os.environ.copy()
            env["NO_DASHBOARD"] = "1"
            env[s["env_key"]] = str(s["num"])
            p = subprocess.Popen(
                [sys.executable, "-u", s["cmd"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=CWD, env=env,
                bufsize=1, text=True,
            )
            self.processes[s["key"]] = p
            t = threading.Thread(target=self._reader, args=(s["key"], p), daemon=True)
            t.start()

    def _reader(self, key, proc):
        try:
            for line in proc.stdout:
                if not self.running:
                    break
                line = line.strip()
                if line:
                    self._parse(key, line)
        except:
            pass

    def _parse(self, key, line):
        with self._lock:
            st = self.stats[key]

            if key == "turnstile":
                # Parse pool count (thực tế trong DB)
                m = re.search(r"Pool:\s*(\d+)", line)
                if m:
                    st["pool"] = int(m.group(1))

                m = re.search(r"TOKEN #(\d+)", line)
                if m:
                    st["tokens"] = int(m.group(1))

                m = re.match(r"\[Tab (\d+)\]\s*(.*)", line)
                if m:
                    tid = m.group(1)
                    msg = m.group(2)[:35]
                    if "TOKEN" in msg:
                        st["workers"][tid] = "🟢 OK"
                    elif "Timeout" in msg:
                        st["workers"][tid] = "🟡 Retry"
                    elif "khởi động" in msg:
                        st["workers"][tid] = "🔄 Start"
                    elif "sẵn sàng" in msg:
                        st["workers"][tid] = "🟢 Ready"
                    elif "Lỗi" in msg or "lỗi" in msg:
                        st["workers"][tid] = "🔴 Error"
                    elif "Đóng" in msg:
                        st["workers"][tid] = "♻️ Restart"
                    else:
                        st["workers"][tid] = msg[:15]

                m = re.search(r"Đã xóa (\d+) token", line)
                if m:
                    st["tokens"] = 0
            else:
                # Parse worker status
                m = re.match(r"\[Worker-(\d+)\]\s*(.*)", line)
                if m:
                    wid = m.group(1)
                    msg = m.group(2)
                    if "VOTE THÀNH CÔNG" in msg:
                        st["workers"][wid] = "🎉 Vote OK"
                        st["w_success"][wid] = st["w_success"].get(wid, 0) + 1
                    elif "Đăng nhập thành công" in msg:
                        st["workers"][wid] = "✅ Login"
                    elif "Đăng ký thành công" in msg or "Đăng ký" in msg and "ĐK OK" not in st["workers"].get(wid, ""):
                        if "thành công" in msg:
                            st["workers"][wid] = "✅ ĐK OK"
                        elif "thất bại" in msg:
                            st["workers"][wid] = "❌ ĐK Fail"
                        else:
                            st["workers"][wid] = "📝 ĐK..."
                    elif "Kích hoạt" in msg and "thành công" in msg:
                        st["workers"][wid] = "✅ Active"
                    elif "Kích hoạt" in msg:
                        st["workers"][wid] = "🔓 Active..."
                    elif "Chờ token" in msg or "Chờ turnstile" in msg:
                        st["workers"][wid] = "🔵 Token"
                    elif "Chờ email" in msg or "Poll" in msg:
                        st["workers"][wid] = "📬 Email"
                    elif "Vote" in msg or "vote" in msg:
                        st["workers"][wid] = "🗳️ Vote..."
                    elif "Đăng nhập" in msg:
                        st["workers"][wid] = "🔑 Login..."
                    elif "Đã lưu" in msg:
                        st["workers"][wid] = "💾 Saved"
                    elif "Tạo email" in msg:
                        st["workers"][wid] = "📧 Email"
                    elif "Link" in msg or "link" in msg:
                        st["workers"][wid] = "🔗 Link"
                    elif "thất bại" in msg or "Lỗi" in msg:
                        st["workers"][wid] = "❌ Fail"
                        st["w_fail"][wid] = st["w_fail"].get(wid, 0) + 1

                # Parse success/fail stats
                m = re.search(r"[Tt]hành công:\s*(\d+)\s*\|\s*[Tt]hất bại:\s*(\d+)", line)
                if m:
                    st["success"] = int(m.group(1))
                    st["fail"] = int(m.group(2))

            # Add to recent logs (only important events)
            if any(kw in line for kw in ["VOTE THÀNH CÔNG", "TOKEN #", "thất bại", "Lỗi", "restart"]):
                ts = time.strftime("%H:%M:%S")
                short = line[:45]
                st["logs"].append(f"{ts} {short}")

            self._refresh()

    def _refresh(self):
        if self.live:
            self.live.update(self._render())

    def _elapsed(self):
        s = int(time.time() - self.start_time)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _render(self):
        total_success = sum(s["success"] for k, s in self.stats.items() if k != "turnstile")
        total_fail = sum(s["fail"] for k, s in self.stats.items() if k != "turnstile")
        ts_st = self.stats.get("turnstile")
        tokens = ts_st.get("pool", 0) if ts_st else 0
        produced = ts_st["tokens"] if ts_st else 0

        # ── Header ──
        h = Text()
        h.append(f"  ✅ {total_success}", style="bold green")
        h.append("  │  ", style="dim")
        h.append(f"❌ {total_fail}", style="bold red")
        h.append("  │  ", style="dim")
        h.append(f"🔑 Pool: {tokens}", style="bold yellow")
        h.append(f" (đã tạo: {produced})", style="dim")
        h.append("  │  ", style="dim")
        h.append(f"⏱️  {self._elapsed()}", style="bold")
        header = Panel(h, title="[bold]ELLE VOTE — MASTER[/bold]", border_style="blue")

        # ── Turnstile Panel (nếu được chọn) ──
        ts_panel = None
        if ts_st:
            pool = ts_st.get("pool", 0)
            produced_t = ts_st["tokens"]
            ts_table = Table(box=box.SIMPLE, expand=True, show_header=False)
            ts_table.add_column("Tab", width=5)
            ts_table.add_column("Status", width=12)
            for tid in sorted(ts_st["workers"], key=lambda x: int(x)):
                ts_table.add_row(f"Tab {tid}", ts_st["workers"][tid])
            ts_panel = Panel(
                Group(Text(f"Pool: {pool} sẵn sàng  │  Đã tạo: {produced_t}", style="bold yellow"), ts_table),
                title="🔑 Turnstile", border_style="yellow",
            )

        # ── Cột chi tiết từng luồng (chỉ scripts được chọn) ──
        vote_panels = []
        for key in [k for k in self.stats if k != "turnstile"]:
            st = self.stats[key]

            tbl = Table(
                box=box.MINIMAL, expand=True, show_edge=False,
                header_style="bold", padding=(0, 1),
            )
            tbl.add_column("W", width=3, justify="right")
            tbl.add_column("Trạng thái", width=14)
            tbl.add_column("✅", width=3, justify="right", style="green")
            tbl.add_column("❌", width=3, justify="right", style="red")

            for wid in sorted(st["workers"], key=lambda x: int(x)):
                status = st["workers"][wid]
                ws = str(st["w_success"].get(wid, 0))
                wf = str(st["w_fail"].get(wid, 0))
                tbl.add_row(wid, status, ws, wf)

            header_txt = Text()
            header_txt.append(f"✅ {st['success']}", style="bold green")
            header_txt.append(f"  ❌ {st['fail']}", style="bold red")
            header_txt.append(f"  👥 {len(st['workers'])}", style="dim")

            vote_panels.append(
                Panel(
                    Group(header_txt, tbl),
                    title=st["title"], border_style="cyan",
                )
            )

        # ── Logs ──
        all_logs = []
        for key, st in self.stats.items():
            for log_entry in st["logs"]:
                prefix = st["title"][:4]
                all_logs.append(f"[dim]{prefix}[/dim] {log_entry}")
        all_logs = all_logs[-6:]
        log_text = Text.from_markup("\n".join(all_logs)) if all_logs else Text("Đang khởi động...", style="dim")
        log_panel = Panel(log_text, title="📋 Nhật ký", border_style="dim", height=8)

        parts = [header]
        if ts_panel:
            parts.append(ts_panel)
        if vote_panels:
            parts.append(Columns(vote_panels, equal=True, expand=True))
        parts.append(log_panel)

        return Group(*parts)

    def stop(self):
        self.running = False
        for key, p in self.processes.items():
            try:
                p.terminate()
                p.wait(timeout=3)
            except:
                try:
                    p.kill()
                except:
                    pass
        if self.live:
            self.live.stop()


if __name__ == "__main__":
    selected = interactive_menu()
    dash = MasterDashboard(selected)
    try:
        dash.start()
        while dash.running:
            time.sleep(1)
    except KeyboardInterrupt:
        dash.stop()
        print(f"\n{'='*60}")
        print("  DỪNG TẤT CẢ SCRIPTS...")
        for key, st in dash.stats.items():
            if key == "turnstile":
                print(f"  🔑 Turnstile: {st['tokens']} tokens")
            else:
                print(f"  {st['title']}: ✅ {st['success']} ❌ {st['fail']}")
        total_s = sum(s["success"] for k, s in dash.stats.items() if k != "turnstile")
        total_f = sum(s["fail"] for k, s in dash.stats.items() if k != "turnstile")
        print(f"  ─────────────────────────────")
        print(f"  TỔNG: ✅ {total_s}  ❌ {total_f}")
        print(f"{'='*60}")

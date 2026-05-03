"""
Dashboard TUI cho các script vote automation.
- Standalone mode: hiển thị rich Live dashboard
- Subprocess mode (NO_DASHBOARD=1): print plain text để master parse
"""
import os
import threading
import time
import re
import logging
from collections import deque
from datetime import datetime

# Detect subprocess mode
_SUBPROCESS_MODE = os.environ.get("NO_DASHBOARD", "") == "1"

if not _SUBPROCESS_MODE:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.console import Console, Group
    from rich import box


class Dashboard:
    def __init__(self, title: str, num_workers: int):
        self.title = title
        self.num_workers = num_workers
        self.success = 0
        self.fail = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        self.workers = {}
        for i in range(1, num_workers + 1):
            self.workers[i] = {"icon": "⚪", "status": "Khởi tạo...", "email": "-"}
        self._logs = deque(maxlen=6)
        self._live = None

        # File logging
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        safe_title = re.sub(r'[^\w]', '_', title)[:30]
        log_file = os.path.join(log_dir, f"{safe_title}_{datetime.now():%Y%m%d_%H%M%S}.log")
        self._flogger = logging.getLogger(f"vote_{safe_title}")
        self._flogger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
        self._flogger.addHandler(fh)
        self._flogger.info(f"=== {title} — {num_workers} workers ===")

    # ── Public API ──────────────────────────────────────────

    def start(self):
        if _SUBPROCESS_MODE:
            return
        self._live = Live(
            self._render(),
            console=Console(force_terminal=True),
            refresh_per_second=4,
            screen=True,
        )
        self._live.start()

    def stop(self):
        if self._live:
            self._live.stop()

    def log(self, worker_id: int, msg: str):
        # Ghi file log (luôn luôn)
        is_error = any(kw in msg for kw in ["Lỗi", "thất bại", "Fail", "Error", "Timeout", "[-]", "❌"])
        if is_error:
            self._flogger.error(f"[W-{worker_id}] {msg}")
        else:
            self._flogger.info(f"[W-{worker_id}] {msg}")

        if _SUBPROCESS_MODE:
            print(f"[Worker-{worker_id}] {msg}", flush=True)
            return
        with self._lock:
            self._parse_status(worker_id, msg)
            ts = time.strftime("%H:%M:%S")
            short = msg[:60] + "..." if len(msg) > 60 else msg
            self._logs.append(f"[dim]{ts}[/dim] [cyan]W-{worker_id}[/cyan] {short}")
            self._refresh()

    def log_request(self, worker_id: int, method: str, url: str, status: int, body=None, resp_text=None):
        """Ghi log chi tiết HTTP request/response vào file."""
        line = f"[W-{worker_id}] {method} {url} → {status}"
        if body:
            line += f" | body={str(body)[:200]}"
        if resp_text:
            line += f" | resp={str(resp_text)[:300]}"
        if status >= 400:
            self._flogger.error(line)
        else:
            self._flogger.debug(line)

    def add_success(self):
        with self._lock:
            self.success += 1
            if _SUBPROCESS_MODE:
                print(f"  → Thành công: {self.success} | Thất bại: {self.fail}", flush=True)
                return
            self._refresh()

    def add_fail(self):
        with self._lock:
            self.fail += 1
            if _SUBPROCESS_MODE:
                print(f"  → Thành công: {self.success} | Thất bại: {self.fail}", flush=True)
                return
            self._refresh()

    # ── Auto-parse log messages ─────────────────────────────

    def _parse_status(self, wid, msg):
        w = self.workers.get(wid)
        if not w:
            return
        m = re.search(r"Email:\s*(\S+)", msg)
        if m:
            w["email"] = m.group(1)[:32]

        if "Chờ turnstile" in msg or "Chờ token" in msg:
            if "Đăng Ký" in msg:
                w["icon"], w["status"] = "🔵", "Chờ token ĐK"
            elif "Đăng Nhập" in msg:
                w["icon"], w["status"] = "🔵", "Chờ token ĐN"
            else:
                w["icon"], w["status"] = "🔵", "Chờ token..."
        elif "Turnstile" in msg and "OK" in msg:
            w["icon"], w["status"] = "✅", "Có token!"
        elif "Tạo email" in msg:
            w["icon"], w["status"] = "📧", "Tạo email..."
        elif "Đăng ký" in msg and "thành công" in msg:
            w["icon"], w["status"] = "✅", "ĐK thành công"
        elif "Đăng ký" in msg and "thất bại" in msg:
            w["icon"], w["status"] = "❌", "ĐK thất bại"
        elif "Đăng ký" in msg:
            w["icon"], w["status"] = "📝", "Đang đăng ký..."
        elif "Chờ email" in msg or "Poll" in msg:
            w["icon"], w["status"] = "📬", "Chờ email..."
        elif "Link xác thực" in msg or "link xác thực" in msg or "link kích hoạt" in msg:
            w["icon"], w["status"] = "🔗", "Có link xác thực"
        elif "Kích hoạt" in msg and "thành công" in msg:
            w["icon"], w["status"] = "✅", "Kích hoạt OK"
        elif "Kích hoạt" in msg:
            w["icon"], w["status"] = "🔓", "Kích hoạt..."
        elif "Đăng nhập" in msg and "thành công" in msg:
            w["icon"], w["status"] = "✅", "Đăng nhập OK"
        elif "Đăng nhập" in msg:
            w["icon"], w["status"] = "🔑", "Đăng nhập..."
        elif "VOTE THÀNH CÔNG" in msg:
            w["icon"], w["status"] = "🎉", "VOTE OK!"
        elif "Vote" in msg or "vote" in msg:
            w["icon"], w["status"] = "🗳️", "Đang vote..."
        elif "Đã lưu" in msg:
            w["icon"], w["status"] = "💾", "Đã lưu DB"
        elif "thất bại" in msg or "Lỗi" in msg or "Timeout" in msg:
            detail = msg[:20].replace("[", "").replace("]", "")
            w["icon"], w["status"] = "❌", detail

    # ── Rendering ───────────────────────────────────────────

    def _elapsed(self):
        s = int(time.time() - self.start_time)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _refresh(self):
        if self._live:
            self._live.update(self._render())

    def _render(self):
        stats = Text()
        stats.append(f"  ✅ Thành công: {self.success}", style="bold green")
        stats.append(f"  │  ", style="dim")
        stats.append(f"❌ Thất bại: {self.fail}", style="bold red")
        stats.append(f"  │  ", style="dim")
        stats.append(f"⏱️  {self._elapsed()}", style="bold yellow")
        header = Panel(stats, title=f"[bold]{self.title}[/bold]", border_style="blue")

        table = Table(
            box=box.SIMPLE_HEAVY, expand=True, show_edge=False,
            header_style="bold cyan", row_styles=["", "dim"],
        )
        table.add_column("W", width=3, justify="right", style="bold")
        table.add_column("", width=2)
        table.add_column("Trạng thái", width=20)
        table.add_column("Email", width=34, style="bright_white")
        for wid in sorted(self.workers):
            w = self.workers[wid]
            table.add_row(str(wid), w["icon"], w["status"], w["email"])

        if self._logs:
            log_text = Text.from_markup("\n".join(self._logs))
        else:
            log_text = Text("Chưa có hoạt động...", style="dim")
        log_panel = Panel(log_text, title="📋 Nhật ký", border_style="dim", height=8)

        return Group(header, table, log_panel)

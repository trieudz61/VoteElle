"""
Vote_SID_Reuse.py
─────────────────
Lấy tài khoản ĐỦ ĐIỀU KIỆN (>24h hoặc chưa vote) từ Supabase,
vote bằng cookie_sid có sẵn.
- Chỉ query account sẵn sàng vote (lọc ngay trên DB, không load cả bảng)
- Hỏi số vote mục tiêu, Enter = vote tất cả
- Vote thất bại → KHÔNG update last_vote_time → chạy lại được
"""

import sys
import os
import re
import requests
import datetime
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# CẤU HÌNH VOTE
# ============================================================
TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
#TARGET_ID   = "69e1fef9a51bd7bcd50c5b40"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"

NUM_WORKERS = 1   # Số luồng song song
COOLDOWN_HOURS = 24  # Phải cách bao nhiêu giờ mới được vote lại
DELAY_BETWEEN_ACCOUNTS =  1.6 # Giây chờ giữa mỗi tài khoản (0 = không chờ)

# Cấu hình danh sách Proxy. Mỗi luồng sẽ tự động lấy 1 proxy khác nhau để chạy.
PROXIES = [
    "http://f9m2:ye17@160.250.184.194:27189",
    "http://q8h1:q8h1@160.22.175.80:17316",
    "http://53ny:53ny@160.22.174.117:20674",
]

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# ============================================================
# VOTE HEADERS
# ============================================================
HEADERS_VOTE = {
    'accept': 'text/x-component',
    'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
    'content-type': 'text/plain;charset=UTF-8',
    'origin': 'https://events.elle.vn',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    'next-action': '288bd3262db6e09085c5f3f89856bb17fb9abf1a',
    'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
    'referer': f'https://events.elle.vn{URL_PATH}',
}

# ============================================================
# SHARED STATE (thread-safe)
# ============================================================
lock = threading.Lock()
stop_event = threading.Event()
stats = {"success": 0, "fail": 0, "processed": 0}

# Shared clients — tạo 1 lần, dùng chung (tránh TLS handshake lặp lại)
_sb_client = None
_http_sessions = {}

def get_shared_sb():
    global _sb_client
    if _sb_client is None:
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb_client

def get_http_session():
    """requests.Session với connection pooling — chia proxy theo từng luồng độc lập."""
    global _http_sessions
    tid = threading.get_ident()
    with lock:
        if tid not in _http_sessions:
            sess = requests.Session()
            sess.headers.update(HEADERS_VOTE)
            if PROXIES:
                proxy = PROXIES[len(_http_sessions) % len(PROXIES)]
                sess.proxies = {"http": proxy, "https": proxy}
            _http_sessions[tid] = sess
        return _http_sessions[tid]


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_eligible_accounts(sb) -> list[dict]:
    """
    Query Supabase: chỉ lấy account có cookie_sid VÀ đủ điều kiện vote:
      - last_time_vote IS NULL (chưa từng vote)
      - last_time_vote < (now - COOLDOWN_HOURS)
    Dùng pagination để lấy hết.
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(hours=COOLDOWN_HOURS)).isoformat()

    all_rows = []
    offset = 0
    PAGE = 1000

    while True:
        # Lấy account chưa vote HOẶC vote đã quá cooldown
        res = (sb.table("accounts")
               .select("id, email, cookie_sid, last_time_vote")
               .not_.is_("cookie_sid", "null")
               .or_(f"last_time_vote.is.null,last_time_vote.lt.{cutoff}")
               .range(offset, offset + PAGE - 1)
               .execute())
        if not res.data:
            break
        all_rows.extend(res.data)
        if len(res.data) < PAGE:
            break
        offset += PAGE

    return all_rows


def vote_with_sid(sid: str) -> tuple[bool, str]:
    """Gửi request vote bằng cookie_sid, trả về (thành_công, lỗi)."""
    try:
        payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
        sess = get_http_session()
        res = sess.post(
            f'https://events.elle.vn{URL_PATH}',
            cookies={'vote_sid': sid},
            data=payload.encode('utf-8'),
            timeout=15
        )
        # Dùng content.decode để tránh mojibake
        text = res.content.decode('utf-8', errors='replace')

        if res.status_code == 200 and '"ok":false' not in text:
            return True, ""
        else:
            match = re.search(r'"error"\s*:\s*"([^"]+)"', text)
            err = match.group(1) if match else text[:120]
            return False, err[:80]  # Giới hạn 80 ký tự
    except Exception as e:
        return False, str(e)[:80]


def process_account(row: dict, idx: int, total: int) -> dict:
    """Xử lý 1 tài khoản: vote → update DB nếu thành công."""
    # Kiểm tra stop trước khi làm gì
    if stop_event.is_set():
        return {"status": "cancelled"}

    email  = row.get("email", "")
    sid    = row.get("cookie_sid", "")
    row_id = row.get("id")

    prefix = f"[{idx}/{total}] {email[:40]}"

    if not sid:
        print(f"{prefix} → ⚠️  Thiếu SID, bỏ qua")
        return {"status": "skip"}

    # Kiểm tra stop lần nữa trước khi gọi network
    if stop_event.is_set():
        return {"status": "cancelled"}

    ok, err = vote_with_sid(sid)

    if ok:
        # Chỉ update last_time_vote khi THÀNH CÔNG
        new_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            get_shared_sb().table("accounts").update(
                {"last_time_vote": new_time}
            ).eq("id", row_id).execute()
        except Exception as db_e:
            print(f"{prefix} → ⚠️  Lưu DB thất bại: {db_e}")
        print(f"{prefix} → ✅ THÀNH CÔNG")
        result = {"status": "ok"}
    else:
        print(f"{prefix} → ❌ {err}")
        if "Please sign in before voting." in err:
            try:
                get_shared_sb().table("accounts").delete().eq("id", row_id).execute()
                print(f"{prefix} → 🗑️  Đã xoá account khỏi DB do SID hết hạn (Please sign in before voting).")
            except Exception as db_e:
                print(f"{prefix} → ⚠️  Lỗi khi xoá account: {db_e}")
        result = {"status": "fail"}

    # Delay giữa mỗi tài khoản
    if DELAY_BETWEEN_ACCOUNTS > 0 and not stop_event.is_set():
        time.sleep(DELAY_BETWEEN_ACCOUNTS)

    return result


def print_progress(total: int, vote_target: int):
    s, f, p = stats["success"], stats["fail"], stats["processed"]
    target_str = f"/{vote_target:,}" if vote_target else ""
    print(f"\r  📊 [{p}/{total}]  ✅ {s}{target_str}  ❌ {f}", end="", flush=True)


def main():
    print("=" * 60)
    print("  VOTE TỰ ĐỘNG — TÁI SỬ DỤNG SID TỪ SUPABASE")
    print(f"  Target: {TARGET_ID} | Cooldown: {COOLDOWN_HOURS}h | Workers: {NUM_WORKERS}")
    print(f"  Delay: {DELAY_BETWEEN_ACCOUNTS}s giữa mỗi tài khoản")
    print("=" * 60)

    # Hỏi số vote mục tiêu
    raw = input("\n  🎯 Nhập số vote mục tiêu (Enter = vote tất cả): ").strip()
    if raw:
        try:
            vote_target = int(raw)
            print(f"  → Dừng khi đạt {vote_target:,} vote thành công.\n")
        except ValueError:
            print("  ⚠️  Không hợp lệ, vote tất cả.\n")
            vote_target = 0
    else:
        vote_target = 0
        print("  → Vote tất cả tài khoản đủ điều kiện.\n")

    # Chỉ lấy account đủ điều kiện từ DB
    print("[*] Đang query tài khoản đủ điều kiện từ Supabase...")
    sb = get_shared_sb()
    all_rows = fetch_eligible_accounts(sb)

    if not all_rows:
        print("[!] Không có tài khoản nào đủ điều kiện vote.")
        return

    total = len(all_rows)
    print(f"[*] Tìm thấy {total:,} tài khoản sẵn sàng vote.\n")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {}
        for i, row in enumerate(all_rows, 1):
            if stop_event.is_set():
                break
            futures[ex.submit(process_account, row, i, total)] = row

        for f in as_completed(futures):
            if stop_event.is_set():
                break  # Thoát luôn, không drain

            r = f.result()
            if r["status"] == "cancelled":
                continue

            with lock:
                if r["status"] == "ok":
                    stats["success"] += 1
                elif r["status"] == "fail":
                    stats["fail"] += 1
                stats["processed"] += 1
                print_progress(total, vote_target)

                # Đạt target → dừng
                if vote_target and stats["success"] >= vote_target:
                    print(f"\n\n  🎯 ĐÃ ĐẠT {vote_target:,} VOTE! Dừng lại.")
                    stop_event.set()
                    for pending in futures:
                        pending.cancel()
                    break

    # Kết quả
    s, f, p = stats["success"], stats["fail"], stats["processed"]
    print("\n" + "=" * 60)
    print(f"  KẾT QUẢ CUỐI CÙNG")
    if vote_target:
        print(f"  🎯 Mục tiêu   : {vote_target:,}")
    print(f"  ✅ Thành công : {s:,}")
    print(f"  ❌ Thất bại   : {f:,}  (không update time → chạy lại được)")
    print(f"  📊 Đã xử lý  : {p:,}/{total:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()

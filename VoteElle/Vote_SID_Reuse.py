"""
Vote_SID_Reuse.py
─────────────────
Lấy toàn bộ tài khoản đã lưu trên Supabase, kiểm tra xem đã đủ 24h
kể từ lần vote gần nhất chưa, rồi vote bằng cookie_sid có sẵn.
Sau khi vote thành công → update last_time_vote thành thời điểm hiện tại (UTC).

Lưu ý: last_time_vote trên Supabase lưu dạng UTC (giờ quốc tế).
Script này tự chuyển đổi sang giờ VN (UTC+7) để hiển thị cho dễ đọc.
"""

import sys
import os
import requests
import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# CẤU HÌNH VOTE
# ============================================================
TARGET_ID  = "69e1ff11df6e31bd3fa4c707"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"

NUM_WORKERS = 10   # Số luồng song song
COOLDOWN_HOURS = 24  # Phải cách bao nhiêu giờ mới được vote lại

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

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_utc_time(ts_str: str) -> datetime.datetime:
    """Parse chuỗi ISO timestamp từ Supabase về datetime UTC-aware."""
    if not ts_str:
        return None
    # Supabase trả về dạng "2026-04-25T11:30:00+00:00" hoặc "2026-04-25T11:30:00Z"
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(ts_str)
    except Exception:
        return None

def is_ready_to_vote(last_time_str: str) -> tuple[bool, str]:
    """
    Kiểm tra xem tài khoản đã đủ COOLDOWN_HOURS kể từ lần vote cuối chưa.
    Trả về (True/False, thông điệp hiển thị giờ VN)
    """
    if not last_time_str:
        return True, "Chưa từng vote"
    
    last_time_utc = parse_utc_time(last_time_str)
    if not last_time_utc:
        return True, "Không đọc được timestamp"
    
    # Đảm bảo timezone-aware
    if last_time_utc.tzinfo is None:
        last_time_utc = last_time_utc.replace(tzinfo=datetime.timezone.utc)
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    elapsed = now_utc - last_time_utc
    hours_elapsed = elapsed.total_seconds() / 3600
    
    # Hiển thị giờ VN cho dễ đọc
    last_time_vn = last_time_utc.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    
    if hours_elapsed >= COOLDOWN_HOURS:
        return True, f"Vote lần cuối: {last_time_vn} VN ({hours_elapsed:.1f}h trước) ✅"
    else:
        remaining = COOLDOWN_HOURS - hours_elapsed
        return False, f"Vote lần cuối: {last_time_vn} VN → còn {remaining:.1f}h nữa ⏳"

def vote_with_sid(sid: str) -> tuple[bool, str]:
    """Gửi request vote bằng cookie_sid, trả về (thành_công, lỗi)."""
    try:
        payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
        res = requests.post(
            f'https://events.elle.vn{URL_PATH}',
            headers=HEADERS_VOTE,
            cookies={'vote_sid': sid},
            data=payload.encode('utf-8'),
            timeout=15
        )
        if res.status_code == 200 and '"ok":false' not in res.text:
            return True, ""
        else:
            # Extract thông điệp lỗi
            import re
            match = re.search(r'"error"\s*:\s*"([^"]+)"', res.text)
            err = match.group(1) if match else res.text[:150]
            return False, err
    except Exception as e:
        return False, str(e)

def process_account(row: dict, idx: int, total: int) -> dict:
    """Xử lý 1 tài khoản: validate → vote → update DB."""
    email     = row.get("email", "")
    sid       = row.get("cookie_sid", "")
    last_time = row.get("last_time_vote", "")
    row_id    = row.get("id")

    prefix = f"[{idx}/{total}] {email[:40]}"

    if not sid:
        print(f"{prefix} → ⚠️  Không có cookie_sid, bỏ qua")
        return {"status": "skip"}

    ready, msg = is_ready_to_vote(last_time)
    if not ready:
        print(f"{prefix} → {msg}")
        return {"status": "skip"}

    print(f"{prefix} → {msg} → Đang vote...")
    ok, err = vote_with_sid(sid)

    if ok:
        # Update last_time_vote lên DB (lưu dạng UTC ISO)
        new_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            get_supabase().table("accounts").update({"last_time_vote": new_time}).eq("id", row_id).execute()
        except Exception as db_e:
            print(f"{prefix} → ⚠️  Lưu DB thất bại: {db_e}")
        print(f"{prefix} → ✅ VOTE THÀNH CÔNG! DB đã cập nhật.")
        return {"status": "ok"}
    else:
        print(f"{prefix} → ❌ Vote thất bại: {err[:100]}")
        return {"status": "fail"}

def main():
    print("=" * 60)
    print("  VOTE TỰ ĐỘNG — TÁI SỬ DỤNG SID TỪ SUPABASE")
    print(f"  Target: {TARGET_ID} | Cooldown: {COOLDOWN_HOURS}h | Luồng: {NUM_WORKERS}")
    print("=" * 60)

    print("[*] Đang tải danh sách tài khoản từ Supabase...")
    sb = get_supabase()

    # Lấy tất cả tài khoản có cookie_sid
    # Supabase giới hạn 1000 row mỗi lần → dùng pagination
    all_rows = []
    offset = 0
    PAGE = 1000
    while True:
        res = sb.table("accounts").select("id, email, cookie_sid, last_time_vote") \
               .not_.is_("cookie_sid", "null") \
               .range(offset, offset + PAGE - 1) \
               .execute()
        if not res.data:
            break
        all_rows.extend(res.data)
        if len(res.data) < PAGE:
            break
        offset += PAGE

    if not all_rows:
        print("[!] Không có tài khoản nào có cookie_sid trên Supabase.")
        return

    print(f"[*] Tổng {len(all_rows)} tài khoản có SID. Đang lọc theo {COOLDOWN_HOURS}h cooldown...\n")

    success = fail = skip = 0
    total = len(all_rows)

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {ex.submit(process_account, row, i, total): row
                   for i, row in enumerate(all_rows, 1)}
        for f in as_completed(futures):
            r = f.result()
            if r["status"] == "ok":
                success += 1
            elif r["status"] == "fail":
                fail += 1
            else:
                skip += 1

    print("\n" + "=" * 60)
    print(f"  ✅ Thành công: {success}  |  ❌ Thất bại: {fail}  |  ⏳ Bỏ qua: {skip}")
    print("=" * 60)

if __name__ == "__main__":
    main()

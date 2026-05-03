"""
Login_Vote_Reuse.py
- Đọc danh sách email từ smvmail_exported.txt
- Tự động lấy Turnstile token từ Supabase để Login
- Login xong lấy được SID mới -> Lấy SID đó đi Vote luôn
- Lưu thông tin (email, password, SID, last_time_vote) ngược lại vào Supabase
- Dù Vote thành công hay thất bại cũng lưu last_time_vote
"""
import sys
import os
import requests
import datetime
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
# TARGET_ID   = "69e1fef9a51bd7bcd50c5b40"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"

NUM_WORKERS = 5
PASSWORD = "Trieu@123"

_sb_client = None
def get_sb():
    global _sb_client
    if _sb_client is None:
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb_client

def get_fresh_token() -> str:
    try:
        res = get_sb().rpc("pop_token").execute()
        return res.data if res.data else ""
    except Exception:
        return ""

def wait_for_token(prefix) -> str:
    print(f"{prefix} → Đang chờ Turnstile token...")
    while True:
        token = get_fresh_token()
        if token:
            return token
        time.sleep(2)

def process_email(email: str, idx: int, total: int):
    prefix = f"[{idx}/{total}] {email[:30]}"
    email = email.strip()
    if not email:
        return

    # Lấy token
    token = wait_for_token(prefix)
    
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=5)
    session.mount('https://', adapter)

    headers_base = {
        'accept': 'text/x-component',
        'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
        'origin': 'https://events.elle.vn',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    # 1. ĐĂNG NHẬP
    headers_login = headers_base.copy()
    headers_login['next-action'] = '49be4f5334755d0610d3145cfc19c274abef2e1a'
    headers_login['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%5C%22returnTo%5C%22%3A%5C%22%2Felle-beauty-awards-2026%5C%22%7D%22%2C%7B%7D%2C%22%2Flogin%3FreturnTo%3D%252Felle-beauty-awards-2026%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    headers_login['referer'] = 'https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026'

    files_login = [
        ('1_$ACTION_REF_1', (None, '')),
        ('1_$ACTION_1:0', (None, '{"id":"49be4f5334755d0610d3145cfc19c274abef2e1a","bound":"$@1"}')),
        ('1_$ACTION_1:1', (None, '[{"error":""}]')),
        ('1_$ACTION_KEY', (None, 'k2964878165')),
        ('1_returnTo', (None, '/elle-beauty-awards-2026')),
        ('1_identifier', (None, email)),
        ('1_password', (None, PASSWORD)),
        ('1_cf-turnstile-response', (None, token)),
        ('1_cf-turnstile-response', (None, token)),
        ('0', (None, '[{"error":""},"$K1"]')),
    ]

    try:
        res_login = session.post(
            'https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026',
            headers=headers_login, files=files_login, allow_redirects=True, timeout=15
        )
    except Exception as e:
        print(f"{prefix} → ❌ Lỗi mạng khi Login: {e}")
        return

    vote_sid = session.cookies.get('vote_sid')
    if not vote_sid:
        for cookie in res_login.cookies:
            if cookie.name == 'vote_sid':
                vote_sid = cookie.value
                session.cookies.set('vote_sid', vote_sid)
                break

    if not vote_sid:
        print(f"{prefix} → ❌ Login thất bại (Không lấy được SID).")
        return

    print(f"{prefix} → ✅ Login thành công, đang Vote...")

    # 2. VOTE BẰNG SID VỪA LẤY
    headers_vote = headers_base.copy()
    headers_vote['content-type']           = 'text/plain;charset=UTF-8'
    headers_vote['next-action']            = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
    headers_vote['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    headers_vote['referer']                = f'https://events.elle.vn{URL_PATH}'

    vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
    vote_success = False
    try:
        res_vote = session.post(f'https://events.elle.vn{URL_PATH}', headers=headers_vote, data=vote_payload.encode('utf-8'), timeout=15)
        if res_vote.status_code in [200, 302] and '"ok":false' not in res_vote.text:
            vote_success = True
            print(f"{prefix} → 🎉 VOTE THÀNH CÔNG!")
        else:
            err_msg = res_vote.text[:80]
            print(f"{prefix} → ⚠️ Vote thất bại: {err_msg}")
    except Exception as e:
        print(f"{prefix} → ⚠️ Lỗi khi Vote: {e}")

    # 3. LƯU VÀO DATABASE
    # Theo yêu cầu: Dù vote thất bại vẫn lưu last_time_vote
    sb = get_sb()
    try:
        # Xóa bản ghi cũ để tránh lỗi duplicate email (nếu có)
        sb.table("accounts").delete().eq("email", email).execute()
        # Thêm mới với SID và last_time_vote hiện tại
        account_data = {
            "email": email,
            "password": PASSWORD,
            "cookie_sid": vote_sid,
            "last_time_vote": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        sb.table("accounts").insert(account_data).execute()
        print(f"{prefix} → 💾 Đã lưu DB (SID & time).")
    except Exception as db_e:
        print(f"{prefix} → ❌ Lỗi khi lưu DB: {db_e}")


def main():
    print("=" * 60)
    print("  LOGIN & VOTE BẰNG EMAIL TỪ smvmail_exported.txt")
    print(f"  Workers: {NUM_WORKERS} | Password: {PASSWORD}")
    print("=" * 60)

    txt_file = "smvmail_exported.txt"
    if not os.path.exists(txt_file):
        print(f"❌ Không tìm thấy file {txt_file}!")
        return

    with open(txt_file, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    emails = [l.strip() for l in lines if l.strip()]
    total = len(emails)
    if total == 0:
        print(f"⚠️ File {txt_file} trống.")
        return

    print(f"[*] Tìm thấy {total} email. Đang chạy...\n")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {ex.submit(process_email, email, i, total): email for i, email in enumerate(emails, 1)}
        try:
            for f in as_completed(futures):
                f.result()
        except KeyboardInterrupt:
            print("\n🛑 Dừng chương trình...")

if __name__ == "__main__":
    main()

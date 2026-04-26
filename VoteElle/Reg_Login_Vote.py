import requests
import json
import os
import sys
import random
import string
import time
import re
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

# ================= CẤU HÌNH =================
TARGET_ID  = "69e1ff11df6e31bd3fa4c707"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"
NUM_WORKERS = 3   # Số luồng chạy song song (tăng lên tuỳ token farm được)
# ==============================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")

# Lock để print không bị lẫn lộn giữa các luồng
print_lock = threading.Lock()

def log(worker_id, msg):
    with print_lock:
        print(f"[Worker-{worker_id}] {msg}")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_fresh_token() -> str:
    try:
        res = get_supabase().rpc("pop_token").execute()
        return res.data if res.data else ""
    except Exception as e:
        return ""

def wait_for_token(worker_id, task_name) -> str:
    log(worker_id, f"Chờ token cho [{task_name}]...")
    while True:
        token = get_fresh_token()
        if token:
            log(worker_id, f"[v] Có token cho [{task_name}]!")
            return token
        time.sleep(3)

VN_NAMES = [
    "anh", "thy", "pham", "nguyen", "tran", "le", "hoang", "huynh", "phan", "vu", "vo", "dang",
    "bui", "do", "ho", "ngo", "duong", "ly", "thanh", "tuan", "minh", "hieu", "khoa", "phat",
    "dat", "son", "hai", "long", "thang", "tien", "quang", "tai", "thinh", "tinh", "bao",
    "tri", "duc", "trong", "sang", "linh", "trang", "ngoc", "mai", "lan", "huong", "phuong",
    "thu", "yen", "oanh", "vy", "my", "tram", "nhi", "yen", "chau", "nhung", "tuyen", "quy"
]

def gen_user():
    num_words = random.choice([2, 3])
    words = random.choices(VN_NAMES, k=num_words)
    suffix_len = random.randint(5, 7)
    suffix = ''.join(random.choices(string.digits, k=suffix_len))
    return f"{''.join(words)}{suffix}"

# ==========================================
# TOÀN BỘ FLOW CHO 1 TÀI KHOẢN
# ==========================================
def run_one_account(worker_id: int):
    # --- Lấy 2 token trước khi bắt đầu ---
    token_reg   = wait_for_token(worker_id, "Đăng Ký")
    token_login = wait_for_token(worker_id, "Đăng Nhập")

    random_user = gen_user()
    email       = f"{random_user}@smvmail.com"
    password    = "Trieu@123"
    session     = requests.Session()

    headers_base = {
        'accept': 'text/x-component',
        'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
        'origin': 'https://events.elle.vn',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    # BƯỚC 1: ĐĂNG KÝ
    log(worker_id, f"1. Đăng ký: {email}")
    headers_reg = headers_base.copy()
    headers_reg['next-action'] = 'ecb6a6ba19e2a6c226360a24043314cd2dffb8f8'
    headers_reg['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%22register%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fregister%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    headers_reg['referer'] = 'https://events.elle.vn/register'

    files_reg = [
        ('1_returnTo', (None, '/')),
        ('1_username', (None, random_user)),
        ('1_email', (None, email)),
        ('1_password', (None, password)),
        ('1_passwordConfirmation', (None, password)),
        ('1_cf-turnstile-response', (None, token_reg)),
        ('1_cf-turnstile-response', (None, token_reg)),
        ('0', (None, '[{"error":"","success":""},"$K1"]')),
    ]

    res_reg = session.post('https://events.elle.vn/register', headers=headers_reg, files=files_reg)
    if res_reg.status_code != 200:
        log(worker_id, f"[-] Đăng ký thất bại ({res_reg.status_code})")
        return False
    log(worker_id, "[v] Đăng ký thành công!")
    time.sleep(3)

    # BƯỚC 2: ĐỢI EMAIL XÁC THỰC
    log(worker_id, "2. Đang chờ email xác thực...")
    activation_link = None
    for attempt in range(12):
        time.sleep(5)
        try:
            res = requests.get(f"https://smvmail.com/api/email?page=1&q=&email={email}", timeout=10)
            docs = res.json().get('data', {}).get('docs', [])
            for doc in docs:
                content = json.dumps(doc).replace('\\/', '/')
                links = re.findall(r'https://baseapi\.elle\.vn/auth/email-confirmation\?confirmation=[a-f0-9]+', content)
                if links:
                    activation_link = links[0]
                    break
            if activation_link:
                break
            log(worker_id, f"  [{attempt+1}/12] Chưa có mail...")
        except Exception:
            pass

    if not activation_link:
        log(worker_id, "[-] Timeout! Không tìm thấy email xác thực")
        return False
    log(worker_id, f"[v] Có link xác thực!")

    # BƯỚC 3: KÍCH HOẠT
    log(worker_id, "3. Kích hoạt tài khoản...")
    res_verify = session.get(activation_link, allow_redirects=True)
    if res_verify.status_code not in [200, 303]:
        log(worker_id, f"[-] Kích hoạt thất bại ({res_verify.status_code})")
        return False
    log(worker_id, "[v] Kích hoạt thành công!")
    time.sleep(1)

    # BƯỚC 4: ĐĂNG NHẬP
    log(worker_id, f"4. Đăng nhập {email}...")
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
        ('1_password', (None, password)),
        ('1_cf-turnstile-response', (None, token_login)),
        ('1_cf-turnstile-response', (None, token_login)),
        ('0', (None, '[{"error":""},"$K1"]')),
    ]

    res_login = session.post(
        'https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026',
        headers=headers_login, files=files_login, allow_redirects=True
    )

    vote_sid = session.cookies.get('vote_sid')
    if not vote_sid:
        for cookie in res_login.cookies:
            if cookie.name == 'vote_sid':
                vote_sid = cookie.value
                session.cookies.set('vote_sid', vote_sid)
                break

    if not vote_sid:
        log(worker_id, f"[-] Không lấy được cookie login ({res_login.status_code})")
        return False
    log(worker_id, f"[v] Đăng nhập thành công! vote_sid: {vote_sid[:16]}...")

    # BƯỚC 5: VOTE
    log(worker_id, f"5. Đang vote cho {TARGET_ID}...")
    headers_vote = headers_base.copy()
    headers_vote['content-type']           = 'text/plain;charset=UTF-8'
    headers_vote['next-action']            = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
    headers_vote['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    headers_vote['referer']                = f'https://events.elle.vn{URL_PATH}'

    vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
    res_vote = session.post(f'https://events.elle.vn{URL_PATH}', headers=headers_vote, data=vote_payload.encode('utf-8'))

    if res_vote.status_code == 200 and '"ok":false' not in res_vote.text:
        log(worker_id, "[v] VOTE THÀNH CÔNG!")
        # Lưu lên Supabase
        try:
            account_data = {
                "email": email,
                "password": password,
                "cookie_sid": vote_sid,
                "last_time_vote": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            get_supabase().table("accounts").insert(account_data).execute()
            log(worker_id, "[v] Đã lưu tài khoản lên Supabase!")
        except Exception as e:
            log(worker_id, f"[-] Lỗi lưu DB: {e}")
        return True
    else:
        log(worker_id, f"[-] Vote thất bại: {res_vote.text[:150]}")
        return False


# ==========================================
# MAIN: CHẠY ĐA LUỒNG
# ==========================================
if __name__ == "__main__":
    with print_lock:
        print("=" * 55)
        print(f"  BẮT ĐẦU ĐĂNG KÝ & VOTE ĐA LUỒNG ({NUM_WORKERS} luồng)")
        print("=" * 55)

    success = 0
    fail = 0

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Chạy vô hạn cho đến khi Ctrl+C
        futures = {executor.submit(run_one_account, i + 1): i for i in range(NUM_WORKERS)}
        try:
            while True:
                for future in as_completed(futures):
                    worker_id = futures[future] + 1
                    try:
                        result = future.result()
                        if result:
                            success += 1
                        else:
                            fail += 1
                    except Exception as e:
                        with print_lock:
                            print(f"[Worker-{worker_id}] Lỗi: {e}")
                        fail += 1

                    with print_lock:
                        print(f"\n  → Đã thành công: {success} | Thất bại: {fail}\n")

                    # Submit lại ngay luồng vừa xong
                    new_future = executor.submit(run_one_account, worker_id)
                    futures[new_future] = worker_id - 1
                    del futures[future]
                    break  # Chỉ xử lý 1 future mỗi lần để tránh dict size change

        except KeyboardInterrupt:
            with print_lock:
                print(f"\n{'='*55}")
                print(f"  DỪNG CHƯƠNG TRÌNH")
                print(f"  Thành công: {success} | Thất bại: {fail}")
                print(f"{'='*55}")

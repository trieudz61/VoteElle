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
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

is_running = True

def sleep_if_running(secs):
    for _ in range(int(secs * 10)):
        if not is_running: return False
        time.sleep(0.1)
    return True
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

# ================= CẤU HÌNH =================
#TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
TARGET_ID   = "69e1fef9a51bd7bcd50c5b40"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"

ENABLE_VOTE = False # Nếu False: chỉ Login lấy SID rồi lưu DB, không Vote ngay (cho phép vote sau)

NUM_WORKERS = int(os.environ.get("NUM_WORKERS", 15))  # Env var hoặc mặc định
# ==============================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")

# Dashboard TUI
from dashboard import Dashboard
dash = Dashboard(f"SMVMAIL — {NUM_WORKERS} luồng", NUM_WORKERS)
print_lock = threading.Lock()

def log(worker_id, msg):
    dash.log(worker_id, msg)

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
    while is_running:
        token = get_fresh_token()
        if token:
            log(worker_id, f"[v] Có token cho [{task_name}]!")
            return token
        if not sleep_if_running(3):
            break
    return ""

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
    # --- Lấy token đăng ký trước ---
    token_reg   = wait_for_token(worker_id, "Đăng Ký")
    if not token_reg: return False

    # Lấy token login SONG SONG với poll email (bên dưới)
    token_login = [None]
    def _fetch_login_token():
        token_login[0] = wait_for_token(worker_id, "Đăng Nhập")
    login_thread = threading.Thread(target=_fetch_login_token, daemon=True)

    random_user = gen_user()
    email       = f"{random_user}@smvmail.com"
    password    = "Trieu@123"
    session     = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=5)
    session.mount('https://', adapter)

    headers_base = {
        'accept': 'text/x-component',
        'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
        'origin': 'https://events.elle.vn',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    # BƯỚC 1: ĐĂNG KÝ (retry nếu CAPTCHA fail)
    reg_ok = False
    for attempt in range(3):
        if attempt > 0:
            log(worker_id, f"1. Retry đăng ký lần {attempt+1} — lấy token mới...")
            token_reg = wait_for_token(worker_id, "Đăng Ký")
            if not token_reg: return False
        else:
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
        res_reg.encoding = 'utf-8'
        dash.log_request(worker_id, "POST", "/register", res_reg.status_code, resp_text=res_reg.text[:300])
        if res_reg.status_code != 200:
            log(worker_id, f"[-] Đăng ký thất bại ({res_reg.status_code})")
            continue
        body = res_reg.text
        if '"error":""' not in body or '"success":""' in body:
            err_match = re.search(r'"error":"([^"]+)"', body)
            err_msg = err_match.group(1) if err_match else body[:150]
            if "CAPTCHA" in err_msg or "bảo mật" in err_msg or "xác minh" in err_msg.lower():
                log(worker_id, f"[!] CAPTCHA expired, retry...")
                continue
            log(worker_id, f"[-] Đăng ký thất bại: {err_msg}")
            return False
        reg_ok = True
        break

    if not reg_ok:
        log(worker_id, "[-] Đăng ký thất bại sau 3 lần retry CAPTCHA")
        return False
    log(worker_id, "[v] Đăng ký thành công!")

    # BƯỚC 2: ĐỢI EMAIL XÁC THỰC
    log(worker_id, "2. Đang chờ email xác thực...")
    login_thread.start()  # Bắt đầu lấy token login song song
    activation_link = None
    for attempt in range(7):
        if not sleep_if_running(3): return False
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
            log(worker_id, f"  [{attempt+1}/7] Chưa có mail...")
        except Exception:
            pass

    if not activation_link:
        log(worker_id, "[-] Timeout! Không tìm thấy email xác thực")
        return False
    log(worker_id, f"[v] Có link xác thực!")

    # BƯỚC 3: KÍCH HOẠT
    log(worker_id, "3. Kích hoạt tài khoản...")
    headers_verify = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }
    res_verify = session.get(activation_link, headers=headers_verify, allow_redirects=True)
    dash.log_request(worker_id, "GET", activation_link[:80], res_verify.status_code)
    if res_verify.status_code not in [200, 302, 303]:
        log(worker_id, f"[-] Kích hoạt thất bại ({res_verify.status_code}) {res_verify.text[:100]}")
        return False
    log(worker_id, "[v] Kích hoạt thành công!")

    # Chờ token login (thường đã sẵn sàng từ lúc poll email)
    login_thread.join()
    if not token_login[0]: return False

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
        ('1_cf-turnstile-response', (None, token_login[0])),
        ('1_cf-turnstile-response', (None, token_login[0])),
        ('0', (None, '[{"error":""},"$K1"]')),
    ]

    res_login = session.post(
        'https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026',
        headers=headers_login, files=files_login, allow_redirects=True
    )
    dash.log_request(worker_id, "POST", "/login", res_login.status_code, resp_text=res_login.text[:200])

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
    if ENABLE_VOTE:
        log(worker_id, f"5. Đang vote cho {TARGET_ID}...")
        headers_vote = headers_base.copy()
        headers_vote['content-type']           = 'text/plain;charset=UTF-8'
        headers_vote['next-action']            = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
        headers_vote['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
        headers_vote['referer']                = f'https://events.elle.vn{URL_PATH}'

        vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
        res_vote = session.post(f'https://events.elle.vn{URL_PATH}', headers=headers_vote, data=vote_payload.encode('utf-8'))
        dash.log_request(worker_id, "POST", URL_PATH, res_vote.status_code, resp_text=res_vote.text[:200])

        if res_vote.status_code in [200, 302] and '"ok":false' not in res_vote.text:
            log(worker_id, "[v] VOTE THÀNH CÔNG!")
            last_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        else:
            log(worker_id, f"[-] Vote thất bại: {res_vote.text[:150]}")
            return False
    else:
        log(worker_id, "[v] Lấy SID thành công (Bỏ qua Vote)!")
        last_time = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc).isoformat()

    # Lưu lên Supabase
    try:
        account_data = {
            "email": email,
            "password": password,
            "cookie_sid": vote_sid,
            "last_time_vote": last_time
        }
        get_supabase().table("accounts").insert(account_data).execute()
        log(worker_id, "[v] Đã lưu tài khoản lên Supabase!")
        return True
    except Exception as e:
        log(worker_id, f"[-] Lỗi lưu DB: {e}")
        return False


# ==========================================
# MAIN: CHẠY ĐA LUỒNG
# ==========================================
if __name__ == "__main__":
    dash.start()

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(run_one_account, i + 1): i for i in range(NUM_WORKERS)}
        try:
            while is_running:
                try:
                    for future in as_completed(futures, timeout=1.0):
                        worker_id = futures[future] + 1
                        try:
                            result = future.result()
                            if result: dash.add_success()
                            else:      dash.add_fail()
                        except Exception as e:
                            dash.log(worker_id, f"Lỗi: {e}")
                            dash.add_fail()

                        if is_running:
                            new_future = executor.submit(run_one_account, worker_id)
                            futures[new_future] = worker_id - 1
                        del futures[future]
                        break
                except TimeoutError:
                    continue
        except KeyboardInterrupt:
            is_running = False
            for future in list(futures.keys()):
                future.cancel()
            dash.stop()
            print(f"\n{'='*55}")
            print(f"  DỪNG CHƯƠNG TRÌNH...")
            print(f"  Thành công: {dash.success} | Thất bại: {dash.fail}")
            print(f"{'='*55}")
            os._exit(0)

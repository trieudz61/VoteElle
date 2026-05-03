"""
Reg_Login_Vote_TempMailMMO.py
Đăng ký + Vote ELLE Beauty Awards dùng TempMailMMO API
API docs: https://tempmailmmo.com/docs/index.html
"""
import json, os, sys, re, datetime, threading, time, random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

is_running = True

def sleep_if_running(secs):
    for _ in range(int(secs * 10)):
        if not is_running: return False
        time.sleep(0.1)
    return True

# ================= CẤU HÌNH =================
#TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
TARGET_ID   = "69e1fef9a51bd7bcd50c5b40"
CATEGORY    = "celebrity"
URL_PATH    = "/elle-beauty-awards-2026/nhan-vat"

ENABLE_VOTE = False # Nếu False: chỉ Login lấy SID rồi lưu DB, không Vote ngay (cho phép vote sau)

NUM_WORKERS = int(os.environ.get("NUM_WORKERS", 15))  # Env var hoặc mặc định
# ==============================================

TEMPMAILMMO_BASE = "https://tempmailmmo.com"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")

# Dashboard TUI
from dashboard import Dashboard
dash = Dashboard(f"TEMPMAILMMO — {NUM_WORKERS} luồng", NUM_WORKERS)
print_lock = threading.Lock()  # giữ lại cho tương thích

def log(worker_id, msg):
    dash.log(worker_id, msg)

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_fresh_turnstile() -> str:
    try:
        res = get_supabase().rpc("pop_token").execute()
        return res.data if res.data else ""
    except Exception:
        return ""

def wait_for_token(worker_id, task_name) -> str:
    log(worker_id, f"Chờ turnstile [{task_name}]...")
    while is_running:
        token = get_fresh_turnstile()
        if token:
            log(worker_id, f"[v] Turnstile [{task_name}] OK!")
            return token
        if not sleep_if_running(3):
            break
    return ""


# ==========================================
# TEMPMAILMMO API
# ==========================================
ELLE_CONFIRM_RE = re.compile(
    # Token có thể là hex hoặc alphanumeric
    r'https://baseapi\.elle\.vn/auth/email-confirmation\?confirmation=[A-Za-z0-9]+'
)
REDIRECT_RE = re.compile(
    r'https://r\.wwwdigitalnetwork\.com/tr/cl/[A-Za-z0-9_\-]+'
)

MMO_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent"  : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer"     : "https://tempmailmmo.com/",
}

def mmo_post(endpoint: str, data: dict) -> dict | None:
    """POST tới /ajax.php?f=<endpoint>"""
    try:
        r = requests.post(
            f"{TEMPMAILMMO_BASE}/ajax.php?f={endpoint}",
            headers=MMO_HEADERS,
            data=data,
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  [mmo] {endpoint} HTTP {r.status_code}: {r.text[:100]}")
            return None
        return r.json()
    except Exception as e:
        print(f"  [mmo] {endpoint} lỗi: {e}")
        return None

MMO_DOMAINS = [
    "tempmailmmo.com", "communitymmo.tokyo", "mailmmo.io.vn",
    "vibecodingmmo.com", "liscensekey.io.vn", "mailmmo.eu.cc",
    "workspacevn.indevs.in", "tempmailmmo.co.uk", "mmo.dpdns.org",
    "phucuongth.edu.vn", "brewvn.io.vn", "dichvu.linkpc.net",
    "coding.publicvm.com", "teamdev.work.gd", "brewvn.com",
    "toolkitmmo.com", "chiasemienphi.indevs.in", "diendanviet.sryze.cc",
    "studentidcard.me", "nghiendesigner.store",
]

def mmo_create_email(worker_id) -> tuple[str, str] | tuple[None, None]:
    """Tạo mailbox mới với domain ngẫu nhiên. Trả về (email_address, sid_token)."""
    domain = random.choice(MMO_DOMAINS)
    d = mmo_post("get_email_address", {"email_domain": domain, "lang": "vi"})
    if not d:
        log(worker_id, "[-] Không tạo được email MMO")
        return None, None
    email   = d.get("email_addr", "")
    sid     = d.get("sid_token", "")
    if not email or not sid:
        log(worker_id, f"[-] Response bất thường: {d}")
        return None, None
    return email, sid

def mmo_list_emails(sid: str) -> tuple[list[dict], str]:
    """
    Lấy danh sách email trong inbox.
    Trả về (list, new_sid) — MMO có thể renew token trong header.
    """
    try:
        r = requests.post(
            f"{TEMPMAILMMO_BASE}/ajax.php?f=get_email_list",
            headers=MMO_HEADERS,
            data={"sid_token": sid, "offset": "0"},
            timeout=15,
        )
        if r.status_code == 401:
            return [], ""  # Signal cần renew session
        if r.status_code != 200:
            print(f"  [mmo] get_email_list HTTP {r.status_code}: {r.text[:100]}")
            return [], sid
        d = r.json()
        # Trả về list và giữ nguyên sid (không rotate theo docs)
        return d.get("list", []), sid
    except Exception as e:
        print(f"  [mmo] get_email_list lỗi: {e}")
        return [], sid

def mmo_fetch_email(sid: str, email_id: str) -> str:
    """Lấy nội dung đầy đủ 1 email. Trả về mail_body (HTML)."""
    d = mmo_post("fetch_email", {"sid_token": sid, "email_id": str(email_id)})
    if not d:
        return ""
    return d.get("mail_body", "")

def mmo_renew_session(email_addr: str) -> str:
    """Mở lại mailbox cũ để lấy sid_token mới khi session expired."""
    d = mmo_post("open_email_address", {"email_addr": email_addr, "force_takeover": "1", "lang": "vi"})
    return d.get("sid_token", "") if d else ""

def follow_redirect(worker_id: int, url: str) -> str:
    """
    Follow redirect từng bước (allow_redirects=False).
    DỪNG và trả về URL ngay khi gặp ELLE confirmation URL trong Location header.
    Không follow qua URL đó (tránh tiêu thụ token trước bước activate).
    """
    current_url = url
    for hop in range(15):
        try:
            r = requests.get(current_url, allow_redirects=False, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            loc = r.headers.get("Location", "")
            log(worker_id, f"  hop {hop+1}: HTTP {r.status_code} → {loc[:120]}")

            if not loc:
                break

            # Kiểm tra ELLE confirmation URL ngay trong Location header
            m = ELLE_CONFIRM_RE.search(loc)
            if m:
                return m.group(0)

            # Tiếp tục theo redirect (relative → absolute)
            if loc.startswith("/"):
                from urllib.parse import urljoin
                loc = urljoin(current_url, loc)
            current_url = loc

        except Exception as e:
            log(worker_id, f"  hop {hop+1} lỗi: {e}")
            break
    return ""


def wait_for_elle_link(worker_id, sid: str, email_addr: str, timeout=21, interval=3) -> str | None:
    """Poll MMO inbox đến khi có link xác thực ELLE."""
    elapsed = 0
    current_sid = sid
    while elapsed < timeout:
        if not sleep_if_running(interval):
            return None
        elapsed += interval
        log(worker_id, f"  [{elapsed}s/{timeout}s] Poll inbox MMO...")

        emails, new_sid = mmo_list_emails(current_sid)

        # 401 = session invalid — thử renew
        if not new_sid:
            log(worker_id, "  [!] Session expired, thử renew...")
            current_sid = mmo_renew_session(email_addr)
            if not current_sid:
                log(worker_id, "[-] Không renew được session")
                return None
            log(worker_id, "  [v] Renew session OK")
            emails, current_sid = mmo_list_emails(current_sid)
            if not current_sid:
                return None
        else:
            current_sid = new_sid

        if emails:
            log(worker_id, f"  Inbox: {len(emails)} email")

        for mail_meta in emails:
            mail_id = mail_meta.get("mail_id") or mail_meta.get("id", "")
            subject = mail_meta.get("mail_subject", "")
            log(worker_id, f"  Email: [{mail_id}] {subject}")

            # Lấy body đầy đủ
            body = mmo_fetch_email(current_sid, str(mail_id))
            if not body:
                continue

            body_clean = body.replace("\\/", "/")

            # Tìm link ELLE trực tiếp
            m = ELLE_CONFIRM_RE.search(body_clean)
            if m:
                log(worker_id, f"[v] Link xác thực: {m.group(0)}")
                return m.group(0)

            # Tìm tracking redirect → follow tất cả hop → lấy link ELLE
            for m2 in REDIRECT_RE.finditer(body_clean):
                tracking_url = m2.group(0)
                log(worker_id, f"  Follow redirect: {tracking_url[:70]}...")
                elle_link = follow_redirect(worker_id, tracking_url)
                if elle_link:
                    log(worker_id, f"[v] Link xác thực (redirect): {elle_link}")
                    return elle_link

    log(worker_id, "[-] Timeout — không tìm thấy link xác thực")
    return None


# ==========================================
# FLOW CHO 1 TÀI KHOẢN
# ==========================================
def run_one_account(worker_id: int) -> bool:
    # Lấy 2 token song song
    tokens = [None, None]
    def _get_reg():
        tokens[0] = wait_for_token(worker_id, "Đăng Ký")
    def _get_login():
        tokens[1] = wait_for_token(worker_id, "Đăng Nhập")
    t1 = threading.Thread(target=_get_reg, daemon=True)
    t2 = threading.Thread(target=_get_login, daemon=True)
    t1.start(); t2.start()
    t1.join(); t2.join()
    token_reg, token_login = tokens
    if not token_reg or not token_login: return False

    session  = requests.Session()
    # Connection pooling — giữ kết nối TCP mở, tránh handshake lại
    adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=5)
    session.mount('https://', adapter)
    password = "Trieu@123"

    headers_base = {
        "accept"          : "text/x-component",
        "accept-language" : "en-US,en;q=0.9,vi;q=0.8",
        "origin"          : "https://events.elle.vn",
        "user-agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    }

    # ── BƯỚC 0: TẠO EMAIL ────────────────────────────────────
    log(worker_id, "0. Tạo email TempMailMMO...")
    email, sid = mmo_create_email(worker_id)
    if not email:
        return False
    log(worker_id, f"  Email: {email}")
    username = re.sub(r"[^a-z0-9]", "", email.split("@")[0].lower())

    # ── BƯỚC 1: ĐĂNG KÝ (retry nếu CAPTCHA fail) ─────────────
    reg_ok = False
    for attempt in range(3):
        if attempt > 0:
            log(worker_id, f"1. Retry đăng ký lần {attempt+1} — lấy token mới...")
            token_reg = wait_for_token(worker_id, "Đăng Ký")
            if not token_reg: return False
        else:
            log(worker_id, f"1. Đăng ký {email}")

        headers_reg = headers_base.copy()
        headers_reg["next-action"]            = "ecb6a6ba19e2a6c226360a24043314cd2dffb8f8"
        headers_reg["next-router-state-tree"] = "%5B%22%22%2C%7B%22children%22%3A%5B%22register%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fregister%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
        headers_reg["referer"]                = "https://events.elle.vn/register"

        files_reg = [
            ("1_returnTo",              (None, "/")),
            ("1_username",              (None, username)),
            ("1_email",                 (None, email)),
            ("1_password",              (None, password)),
            ("1_passwordConfirmation",  (None, password)),
            ("1_cf-turnstile-response", (None, token_reg)),
            ("1_cf-turnstile-response", (None, token_reg)),
            ("0",                       (None, '[{"error":"","success":""},"$K1"]')),
        ]

        res_reg = session.post("https://events.elle.vn/register", headers=headers_reg, files=files_reg)
        res_reg.encoding = "utf-8"
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

    # ── BƯỚC 2: ĐỢI EMAIL XÁC THỰC ──────────────────────────
    log(worker_id, "2. Chờ email xác thực từ TempMailMMO...")
    activation_link = wait_for_elle_link(worker_id, sid, email_addr=email, timeout=21, interval=3)
    if not activation_link:
        return False

    # ── BƯỚC 3: KÍCH HOẠT ────────────────────────────────────
    log(worker_id, "3. Kích hoạt tài khoản...")
    headers_verify = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }
    res_verify = session.get(activation_link, headers=headers_verify, allow_redirects=True)
    dash.log_request(worker_id, "GET", activation_link[:80], res_verify.status_code)
    if res_verify.status_code not in [200, 302, 303]:
        log(worker_id, f"[-] Kích hoạt thất bại ({res_verify.status_code})")
        return False
    log(worker_id, "[v] Kích hoạt thành công!")

    # ── BƯỚC 4: ĐĂNG NHẬP ────────────────────────────────────
    log(worker_id, f"4. Đăng nhập {email}...")
    headers_login = headers_base.copy()
    headers_login["next-action"]            = "49be4f5334755d0610d3145cfc19c274abef2e1a"
    headers_login["next-router-state-tree"] = "%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%5C%22returnTo%5C%22%3A%5C%22%2Felle-beauty-awards-2026%5C%22%7D%22%2C%7B%7D%2C%22%2Flogin%3FreturnTo%3D%252Felle-beauty-awards-2026%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
    headers_login["referer"]                = "https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026"

    files_login = [
        ("1_$ACTION_REF_1",         (None, "")),
        ("1_$ACTION_1:0",           (None, '{"id":"49be4f5334755d0610d3145cfc19c274abef2e1a","bound":"$@1"}')),
        ("1_$ACTION_1:1",           (None, '[{"error":""}]')),
        ("1_$ACTION_KEY",           (None, "k2964878165")),
        ("1_returnTo",              (None, "/elle-beauty-awards-2026")),
        ("1_identifier",            (None, email)),
        ("1_password",              (None, password)),
        ("1_cf-turnstile-response", (None, token_login)),
        ("1_cf-turnstile-response", (None, token_login)),
        ("0",                       (None, '[{"error":""},"$K1"]')),
    ]

    res_login = session.post(
        "https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026",
        headers=headers_login, files=files_login, allow_redirects=True
    )
    dash.log_request(worker_id, "POST", "/login", res_login.status_code, resp_text=res_login.text[:200])

    vote_sid = session.cookies.get("vote_sid")
    if not vote_sid:
        for cookie in res_login.cookies:
            if cookie.name == "vote_sid":
                vote_sid = cookie.value
                session.cookies.set("vote_sid", vote_sid)
                break

    if not vote_sid:
        log(worker_id, f"[-] Không lấy được cookie login ({res_login.status_code})")
        return False
    log(worker_id, f"[v] Đăng nhập thành công! vote_sid: {vote_sid[:16]}...")

    # ── BƯỚC 5: VOTE ─────────────────────────────────────────
    if ENABLE_VOTE:
        log(worker_id, f"5. Vote cho {TARGET_ID}...")
        headers_vote = headers_base.copy()
        headers_vote["content-type"]           = "text/plain;charset=UTF-8"
        headers_vote["next-action"]            = "288bd3262db6e09085c5f3f89856bb17fb9abf1a"
        headers_vote["next-router-state-tree"] = "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
        headers_vote["referer"]                = f"https://events.elle.vn{URL_PATH}"

        vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
        res_vote = session.post(
            f"https://events.elle.vn{URL_PATH}",
            headers=headers_vote, data=vote_payload.encode("utf-8")
        )
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

    try:
        get_supabase().table("accounts").insert({
            "email"          : email,
            "password"       : password,
            "cookie_sid"     : vote_sid,
            "last_time_vote" : last_time,
        }).execute()
        log(worker_id, "[v] Đã lưu Supabase!")
        return True
    except Exception as e:
        log(worker_id, f"[-] Lỗi lưu DB: {e}")
        return False


# ==========================================
# MAIN
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
            for f in list(futures.keys()):
                f.cancel()
            dash.stop()
            print(f"\n{'='*57}")
            print(f"  DỪNG CHƯƠNG TRÌNH...")
            print(f"  Thành công: {dash.success} | Thất bại: {dash.fail}")
            print(f"{'='*57}")
            import os; os._exit(0)

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

sys.stdout.reconfigure(encoding='utf-8')

is_running = True

def sleep_if_running(secs):
    for _ in range(int(secs * 10)):
        if not is_running: return False
        time.sleep(0.1)
    return True

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ================= CẤU HÌNH =================
# TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
TARGET_ID   = "69e1fef9a51bd7bcd50c5b40"
CATEGORY    = "celebrity"
URL_PATH    = "/elle-beauty-awards-2026/nhan-vat"

ENABLE_VOTE = False # Nếu False: chỉ Login lấy SID rồi lưu DB, không Vote ngay (cho phép vote sau)

# NUM_WORKERS = len(ACCOUNT_PAIRS)  ← tự động set bên dưới sau khi khai báo ACCOUNT_PAIRS

# -------------------------------------------------------
# DANH SÁCH CẶP Gmail → Hotmail
# Mỗi gmail_base đã bật forward đến hotmail tương ứng.
# Worker sẽ được gán cặp theo: worker_id % len(ACCOUNT_PAIRS)
# Thêm cặp mới vào đây để mở rộng số luồng độc lập.
# -------------------------------------------------------
ACCOUNT_PAIRS = [
    {
        "gmail_base"    : "trieusamlivn",   # phần trước @gmail.com
        "hotmail_email" : "jgramirez9604ls@hotmail.com",
        "refresh_token" : "M.C519_BAY.0.U.-CpurcJ3lMtal0ZGAJQq!ZYmbK7XpiFeC5zu1!E2pePgEned83tnyDdXCybl0ZJvwYOr48IGhB1swSpBpln2598iLV4ozubQl5*qGe8hd!MXJVEfpFA91ligN6IGIF!OWvMNKoVlXILnPSwYOCSjAQMEyDsuFFQGDeS*7C7QZnpWtOnb3H!He2k5vTnBWsIiVnYuzn2Bd29s4FSvHJhI74Cj6Lg52!*RKRkrdIwwArqkyLiKFUJH*VZPlfBPGUhF0nKzw20fb7TcFXait8wtizRBeDS5U5TLnb5A0l4NkR2pK0KeeYXbi9mxHj*cBNkB2!dSOipTEb*Uy!nRZYVoZwAWhqjRIgomDbwsQMX!D4gNGw7cfCNlyKfA6N8FbAMGebUq2sYTvuX5WW1KrgTUJAow$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
    {
        "gmail_base"    : "trieusamlivn3",
        "hotmail_email" : "kturner1396hhcg@hotmail.com",
        "refresh_token" : "M.C519_BAY.0.U.-Cp0uJkFlq0mNXiUwPB1rGSRzl7PzEG!wxq1OLfUnEX1lQouJcP7jcqMPVbKjg2KVx6ggWJOWbggcN85UF7kVfq8OahNdX7sMIPewZnnJoe*W7dKIv0LvPwo63sha7BgzwpwW0uUJvyV68lBv!ySHRvcdMDN6i9ahaUE5m4V5hxMi35eL7qfo26X!mWm8bO9TN6G0YkXsHDXxouICK3C8MxIEfswdawzq7H7j9hXMcQn*j5IjntLpRzn3R3oP3JHPSw8D0fYsf5vcNYI!WbS!Zm!tuJeNBFohqhrexfY1rBvaZ81A*!lTkEXdGyskcxRjsjpWdBkWWOJLXr4bjUhM79u*oSJGrx4uUiUeIsLQQsN6Pn!7*GkRHyrkiv4hS31nuRfeqH4LCRz8ZJcGCV4QnEE$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
        {
        "gmail_base"    : "kongminhkinh0",
        "hotmail_email" : "obmurphy8433qaty@hotmail.com",
        "refresh_token" : "M.C537_BAY.0.U.-CnLfl0zMQfcHhLfNKohpjxelIaf*UX73yVpmCUpv4g7uEgC6WdAANv30Mj2SPiTGNN!lypasu7leo!Zs3JNCqwbfv97yz9MXAN0PTQnbdIbCUOFI71jrbSETibOd2N!*zhKEttwoRvE9Zkiy7caKZLmeF3oJycin0gv0QR*!Y1FZcOEsDguOQ5WuTDfVWUX05M2EisMbxzXc37TpeSWDcDRBxflbF*RmRkiS5AxtM8EKuSXk7qqQsDm1ncizt2CRdgyLyIUduCASfhqN8nbkOj2E4lh8QXA28eli0csIAdxd8lufYFKtZKuaDYd56dh3XU8bTp54ctoV9HUR!Q!CKUq2ugiJU2x8gfkdatDtPHEaHhNOZX01X73XiO6bvP61wKo8MsCQ6O4lyShMsv1REIw$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
    {
        "gmail_base"    : "chaubaybe2k",
        "hotmail_email" : "randerson2144fos@hotmail.com",
        "refresh_token" : "M.C544_BAY.0.U.-ChV*WSAghqdIfmKksuE1rCk8A83e!RjiUvgDXVK8s9BjxYxfgqbGdeC232!AHAnnwKOeRVzO6o9MZK2ebGikooti*yIYXO0P0b*jmpU3n5Xf9y5*vjjkvggXXzvgEGQLbnRgyLg*WneOlmBAth7IbzDPpOsANR4XmJAAdCfUfPiZhgtgCkKGLe2jqgFVroU4w*PctTAAhHemXLuzwsniZwTVEp86MZ09aOHdqGkUVALrn!6EPQ5d3RAJMWlqJz0yhRLg8ShSFhfr9gFJbw*sa03y2rDP*ZhtiF0TtyibVJftgEUJx3i6VqcANqO7H*QwfjOysXL2VhTcm5QZZlBsdx6FuWuefQ9!obsr37ok2!bTtO12uOZRtXiFrY1zQA5DdPDXL8QU0*LGemguO7GMTt4$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
    {
        "gmail_base"    : "trieusamlivn2",
        "hotmail_email" : "longalbert4044xh@hotmail.com",
        "refresh_token" : "M.C540_BAY.0.U.-ClM5H3d!LlK24cblIuBJT!sc4qyPRzJ8lcpxX6azCXZZ5YsNrw8s*9Cjxxq1tAePUhOB0yz82D41zt0iMBosQVGgbdw!Gu3vqGw0Qt20DNjc!ftKKvXdZbIVgCG1F5rXW6NQY4uBc*z6JnDwvoZmlr4*f7r6wgLsG0ouYGbRXBrKMSqNQsFsxci!CUuMr2LAB8DzPWREMQYK3Md*p86B86IYRFgFfpgSOe2anbiHxN04j30rKdBSGPozQk38bQTeTCkPczfymAFAyYoRewjGARzdUFgh!CmKOYNtWrgSSLDJvPvOFjyrevish*O1i334JQdIh9Uqk*V2gYI0ou7DZExiXw05oFwBIBgZqi7HS!Hj9JXu8X2DxbQQZl9zfN1e0ddux*x0fSC8s7n1BAjqWWw$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
    {
        "gmail_base"    : "trieutran827261",
        "hotmail_email" : "ashleycooper9194aleo@hotmail.com",
        "refresh_token" : "M.C527_BAY.0.U.-Ci6pWcq0hJOHEfjEnJ6eJKVwKjacFhbNKFu8YUfIznE0!Z23MmEpx516R32!8Xgz8A1n4Im5HSskklidMV*KchBsGkFHOV15k2gs7vs*7*N5OaU3O!VuJn0GSmku4r62OWAMrxVIVHeZB5X01CKjEeoi4mNKwj9WFCIfvp7IYazctvq*F!*zHz1rxfu1l0PZEfTGViogfw1WpkE0M5!9EiEqHz!dA0jsfsWHTfdc45eXhUjOVDGxAVvKpFHcnv*0WTrBOsy6wrJZ5pO6v1jn2WtlY06Gvfe0n!tqVheKpxcAaKzbQepzHl5Sllrp5vo4j98QHYxLAedFkhrgefleEdpsW!ewpopsPKk91WSkuJiSgUREFs4TM9gj0Pm2PNNYrUFqYETNt!VRuXdz3KqDuq8$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
    {
        "gmail_base"    : "trieutran028181",
        "hotmail_email" : "bakeralbert9147oz@hotmail.com",
        "refresh_token" : "M.C505_BAY.0.U.-CvefWUDJwgFeNXxxCjcq7vZ2IQ1TxSn66!LTeWNZcEZjj*dm*l*5fKnn1nwWnbqDHj9Pvsn*Ia1TT*ZT3bonDjo7WqqH31fyc8uFHEva31rJ9yQVlcH9cZhDBMXDs0xDPFVOjpu2GFeUevHbFNx0brM14hFFRcfLbGG4rSbag4YYWPJInmraV6B1d8uRVftG2ZqveITTFjDaORnQFIYN5EPk27YXiD!7A2k3jglVg*FpBHj6*gf4ajcW603OyWy*PNyE25s2EjUESIurBniz!TqmT6L0HJ8jkqEnhpCs*z7ZAsPcNlo1xXlZv5hgN7HC1Op4XK1WQjqKDuHJt2F*ny*DzxqUhpyV5kSG4DxSml2APiARbLG*Bi8TK2aYBz9poLNfChK3Gn6M9bHBpMC9Ka4$",
        "client_id"     : "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    },
]
# 1 cặp = 1 luồng — KHÔNG share Hotmail giữa các worker
NUM_WORKERS = min(int(os.environ.get("NUM_WORKERS", len(ACCOUNT_PAIRS))), len(ACCOUNT_PAIRS))
# ==============================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")

# Dashboard TUI
from dashboard import Dashboard
dash = Dashboard(f"NEWWAY Gmail+Hotmail — {NUM_WORKERS} luồng", NUM_WORKERS)
print_lock = threading.Lock()

def log(worker_id, msg):
    dash.log(worker_id, msg)

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_fresh_token() -> str:
    try:
        res = get_supabase().rpc("pop_token").execute()
        return res.data if res.data else ""
    except Exception:
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


def get_pair(worker_id: int) -> dict:
    """
    Trả về cặp Gmail/Hotmail được gán cho worker này.
    worker_id 1 → ACCOUNT_PAIRS[0], worker_id 2 → ACCOUNT_PAIRS[1], ...
    Mỗi cặp chỉ dùng cho đúng 1 worker — không share.
    """
    idx = (worker_id - 1) % len(ACCOUNT_PAIRS)  # modulo chỉ để an toàn khi restart worker
    return ACCOUNT_PAIRS[idx]


# ==========================================
# GMAIL DOT + PLUS TRICK
# ==========================================
def gen_gmail_variant(gmail_base: str) -> str:
    """
    Sinh biến thể Gmail từ gmail_base:
      - Nếu có @domain → dùng domain đó (vd: ioscontrol.com)
      - Nếu không → dùng @gmail.com
      - Chèn 1-4 dấu chấm random + số 1-999
    """
    if "@" in gmail_base:
        local, domain = gmail_base.split("@", 1)
    else:
        local, domain = gmail_base, "gmail.com"

    num_dots = random.randint(1, min(4, len(local) - 1))
    positions = sorted(random.sample(range(1, len(local)), num_dots), reverse=True)
    dotted = local
    for pos in positions:
        dotted = dotted[:pos] + "." + dotted[pos:]
    suffix = random.randint(1, 999)
    return f"{dotted}+{suffix}@{domain}"


# ==========================================
import urllib.parse

# ==========================================
# HOTMAIL API — ĐỌC LINK KÍCH HOẠT ELLE
# ==========================================
REDIRECT_PATTERN = re.compile(
    r'https://r\.wwwdigitalnetwork\.com/tr/cl/[A-Za-z0-9_\-]+'
)
ACTIVATION_PATTERN = re.compile(
    r'https://baseapi\.elle\.vn/auth/email-confirmation\?confirmation=[a-f0-9]+'
)

def _parse_date(date_str: str):
    """Parse date string 'HH:MM - DD/MM/YYYY' thành datetime để so sánh."""
    try:
        return datetime.datetime.strptime(date_str.strip(), "%H:%M - %d/%m/%Y")
    except Exception:
        return None

def _fetch_hotmail_messages(pair: dict) -> list:
    """Gọi API dongvanfb lấy mail từ Hotmail của pair."""
    try:
        resp = requests.post(
            "https://tools.dongvanfb.net/api/get_messages_oauth2",
            json={
                "email"         : pair["hotmail_email"],
                "refresh_token" : pair["refresh_token"],
                "client_id"     : pair["client_id"],
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") is True and data.get("messages"):
            return data["messages"]
    except Exception:
        pass
    return []

def _extract_redirect_urls(msg: dict) -> list:
    """Trích xuất tất cả redirect URLs từ body của 1 message."""
    body = msg.get("message", "") or msg.get("body", "") or json.dumps(msg)
    body = urllib.parse.unquote(body.replace("\\/", "/"))
    return REDIRECT_PATTERN.findall(body)

def _find_confirmation_in_urls(redirect_urls: list, tried_urls: set) -> str | None:
    """
    Follow từng redirect URL chưa thử, tìm link xác nhận email.
    Trả về link baseapi.elle.vn nếu tìm thấy.
    """
    for url in redirect_urls:
        if url in tried_urls:
            continue
        tried_urls.add(url)
        try:
            headers_get = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'}
            resp = requests.get(url, headers=headers_get, allow_redirects=False, timeout=8)
            loc = resp.headers.get('Location', '')
            m = ACTIVATION_PATTERN.search(loc)
            if m:
                return m.group(0)
        except Exception:
            pass
    return None

def get_baseline(pair: dict) -> tuple[str | None, set]:
    """Lấy date message mới nhất + TẤT CẢ redirect URLs hiện tại làm baseline."""
    msgs = _fetch_hotmail_messages(pair)
    if not msgs:
        return None, set()
    top_date = msgs[0].get("date", "")
    # Collect TẤT CẢ redirect URLs từ tất cả messages làm baseline
    all_urls = set()
    for msg in msgs:
        all_urls.update(_extract_redirect_urls(msg))
    return top_date, all_urls

def wait_for_new_link(worker_id, pair: dict, baseline_date: str | None, baseline_urls: set, timeout=21, interval=3) -> str | None:
    """
    Poll Hotmail đến khi có message MỚI HƠN baseline_date.
    Với messages cùng phút baseline: chỉ xét URLs chưa có trong baseline_urls.
    """
    baseline_dt = _parse_date(baseline_date) if baseline_date else None
    log(worker_id, f"  Hotmail: {pair['hotmail_email']} | Baseline date: {baseline_date} ({len(baseline_urls)} urls)")
    elapsed = 0
    tried_urls = set()
    while elapsed < timeout:
        if not sleep_if_running(interval): return None
        elapsed += interval
        log(worker_id, f"  [{elapsed}s/{timeout}s] Poll {pair['hotmail_email']}...")
        msgs = _fetch_hotmail_messages(pair)
        if not msgs:
            log(worker_id, f"  API trả 0 msgs, chờ tiếp...")
            continue

        # Tìm messages MỚI HƠN baseline
        new_msgs = []
        for msg in msgs:
            msg_dt = _parse_date(msg.get("date", ""))
            if msg_dt and baseline_dt:
                if msg_dt > baseline_dt:
                    # Phút mới hơn hẳn → chắc chắn mới
                    new_msgs.append(msg)
                elif msg_dt == baseline_dt:
                    # Cùng phút → check xem có URL mới không
                    msg_urls = set(_extract_redirect_urls(msg))
                    if msg_urls - baseline_urls:
                        new_msgs.append(msg)
                else:
                    break  # Messages sorted mới→cũ
            elif not baseline_dt:
                new_msgs.append(msg)  # Không có baseline → tất cả là mới

        if not new_msgs:
            log(worker_id, f"  Chưa có email mới (API: {len(msgs)} msgs), chờ tiếp...")
            continue

        log(worker_id, f"  Có {len(new_msgs)} email mới, tìm link xác nhận...")
        for msg in new_msgs:
            redirect_urls = _extract_redirect_urls(msg)
            # Bỏ qua URLs đã có trong baseline (cùng phút)
            fresh_urls = [u for u in redirect_urls if u not in baseline_urls]
            link = _find_confirmation_in_urls(fresh_urls, tried_urls)
            if link:
                log(worker_id, f"[v] Link kích hoạt: {link}")
                return link
        log(worker_id, f"  Chưa tìm được link xác nhận, chờ tiếp...")

    log(worker_id, "[-] Timeout — không nhận được link kích hoạt")
    return None



# ==========================================
# TOÀN BỘ FLOW CHO 1 TÀI KHOẢN
# ==========================================
def run_one_account(worker_id: int):
    # --- Lấy 2 Turnstile token song song ---
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

    # --- Lấy cặp Gmail/Hotmail dành riêng cho worker này ---
    pair     = get_pair(worker_id)
    email    = gen_gmail_variant(pair["gmail_base"])
    password = "Trieu@123"
    session  = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=5)
    session.mount('https://', adapter)

    log(worker_id, f"📧 Email: {email} → Hotmail: {pair['hotmail_email']}")

    headers_base = {
        'accept'          : 'text/x-component',
        'accept-language' : 'en-US,en;q=0.9,vi;q=0.8',
        'origin'          : 'https://events.elle.vn',
        'user-agent'      : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    # ── BƯỚC 0: BASELINE ──────────────────────────────────────
    log(worker_id, "0. Lấy baseline Hotmail...")
    baseline_date, baseline_urls = get_baseline(pair)

    # ── BƯỚC 1: ĐĂNG KÝ (retry nếu CAPTCHA fail) ─────────────
    reg_ok = False
    for attempt in range(3):
        if attempt > 0:
            log(worker_id, f"1. Retry đăng ký lần {attempt+1} — lấy token mới...")
            token_reg = wait_for_token(worker_id, "Đăng Ký")
            if not token_reg: return False
        else:
            log(worker_id, f"1. Đăng ký với {email}")

        headers_reg = headers_base.copy()
        headers_reg['next-action']            = 'ecb6a6ba19e2a6c226360a24043314cd2dffb8f8'
        headers_reg['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%22register%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fregister%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
        headers_reg['referer']                = 'https://events.elle.vn/register'

        username_raw = email.split("@")[0]
        username     = re.sub(r'[^a-z0-9]', '', username_raw.lower())

        files_reg = [
            ('1_returnTo',               (None, '/')),
            ('1_username',               (None, username)),
            ('1_email',                  (None, email)),
            ('1_password',               (None, password)),
            ('1_passwordConfirmation',   (None, password)),
            ('1_cf-turnstile-response',  (None, token_reg)),
            ('1_cf-turnstile-response',  (None, token_reg)),
            ('0',                        (None, '[{"error":"","success":""},"$K1"]')),
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

    # ── BƯỚC 2: ĐỢI LINK KÍCH HOẠT TỪ HOTMAIL ───────────────
    log(worker_id, "2. Chờ email kích hoạt từ Hotmail (forward từ Gmail)...")
    activation_link = wait_for_new_link(worker_id, pair, baseline_date, baseline_urls, timeout=21, interval=3)
    if not activation_link:
        return False

    # ── BƯỚC 3: KÍCH HOẠT ────────────────────────────────────
    log(worker_id, "3. Kích hoạt tài khoản...")
    headers_verify = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }
    res_verify = session.get(activation_link, headers=headers_verify, allow_redirects=True)
    if res_verify.status_code not in [200, 302, 303]:
        log(worker_id, f"[-] Kích hoạt thất bại ({res_verify.status_code}) {res_verify.text[:100]}")
        return False
    log(worker_id, "[v] Kích hoạt thành công!")
    if not sleep_if_running(1): return False

    # ── BƯỚC 4: ĐĂNG NHẬP ────────────────────────────────────
    log(worker_id, f"4. Đăng nhập {email}...")
    headers_login = headers_base.copy()
    headers_login['next-action']            = '49be4f5334755d0610d3145cfc19c274abef2e1a'
    headers_login['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%5C%22returnTo%5C%22%3A%5C%22%2Felle-beauty-awards-2026%5C%22%7D%22%2C%7B%7D%2C%22%2Flogin%3FreturnTo%3D%252Felle-beauty-awards-2026%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
    headers_login['referer']                = 'https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026'

    files_login = [
        ('1_$ACTION_REF_1',         (None, '')),
        ('1_$ACTION_1:0',           (None, '{"id":"49be4f5334755d0610d3145cfc19c274abef2e1a","bound":"$@1"}')),
        ('1_$ACTION_1:1',           (None, '[{"error":""}]')),
        ('1_$ACTION_KEY',           (None, 'k2964878165')),
        ('1_returnTo',              (None, '/elle-beauty-awards-2026')),
        ('1_identifier',            (None, email)),
        ('1_password',              (None, password)),
        ('1_cf-turnstile-response', (None, token_login)),
        ('1_cf-turnstile-response', (None, token_login)),
        ('0',                       (None, '[{"error":""},"$K1"]')),
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

    # ── BƯỚC 5: VOTE ─────────────────────────────────────────
    if ENABLE_VOTE:
        log(worker_id, f"5. Vote cho {TARGET_ID}...")
        headers_vote = headers_base.copy()
        headers_vote['content-type']           = 'text/plain;charset=UTF-8'
        headers_vote['next-action']            = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
        headers_vote['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
        headers_vote['referer']                = f'https://events.elle.vn{URL_PATH}'

        vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
        res_vote = session.post(
            f'https://events.elle.vn{URL_PATH}',
            headers=headers_vote, data=vote_payload.encode('utf-8')
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
        account_data = {
            "email"          : email,
            "password"       : password,
            "cookie_sid"     : vote_sid,
            "last_time_vote" : last_time,
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

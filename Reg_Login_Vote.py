import requests
import json
import os
import sys
import random
import string
import time
import re

sys.stdout.reconfigure(encoding='utf-8')

# ================= CẤU HÌNH VOTE =================
TARGET_ID  = "69e1ff11df6e31bd3fa4c707"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"
# =================================================

# ---------- Hàm đọc token từ Supabase Online ----------
def get_fresh_token():
    try:
        from dotenv import load_dotenv
        from supabase import create_client, Client
        load_dotenv()
        
        url = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
        if not url or not key:
            print("[-] Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong file .env!")
            return ""
            
        supabase: Client = create_client(url, key)
        
        # Gọi hàm pop_token (đã tự động lọc token < 5 phút và xoá sau khi rút)
        res = supabase.rpc("pop_token").execute()
        return res.data if res.data else ""
        
    except Exception as e:
        print(f"[-] Lỗi lấy Token từ Database đám mây: {e}")
    return ""

def gen_user(length=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# ---------- Lấy 2 token ----------
token_reg   = get_fresh_token()
token_login = get_fresh_token()

if not token_reg or not token_login:
    print("[-] CẦN ÍT NHẤT 2 TURNSTILE TOKEN (1 Đăng ký + 1 Login).")
    print("[-] Hãy chạy Turnstile_Sele.py trước để tích đủ token!")
    sys.exit(1)

random_user = gen_user()
email       = f"{random_user}@smvmail.com"
password    = "Trieu@123"

session = requests.Session()

headers_base = {
    'accept': 'text/x-component',
    'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
    'origin': 'https://events.elle.vn',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
}

# ============================================================
# BƯỚC 1: ĐĂNG KÝ TÀI KHOẢN
# ============================================================
print(f"[*] 1. ĐĂNG KÝ: {email}")
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
if res_reg.status_code == 200:
    print("[v] Đăng ký thành công!")
    time.sleep(3)
else:
    print(f"[-] Đăng ký thất bại ({res_reg.status_code}). Nội dung: {res_reg.text[:200]}")
    sys.exit(1)

# ============================================================
# BƯỚC 2: ĐỢI EMAIL XÁC THỰC VÀ LẤY LINK
# ============================================================
print(f"\n[*] 2. ĐANG CHỜ EMAIL XÁC THỰC TỪ SMVMAIL (Tối đa 60s)...")
activation_link = None

for attempt in range(12):
    time.sleep(2)
    try:
        res = requests.get(f"https://smvmail.com/api/email?page=1&q=&email={email}", timeout=10)
        data = res.json()
        docs = data.get('data', {}).get('docs', [])

        if not docs:
            print(f"    [{attempt+1}/12] Chưa có mail, đang chờ...")
            continue

        for doc in docs:
            email_content = json.dumps(doc)
            email_content = email_content.replace('\\/', '/')

            # Link xác thực nằm ở baseapi.elle.vn
            links = re.findall(r'https://baseapi\.elle\.vn/auth/email-confirmation\?confirmation=[a-f0-9]+', email_content)
            if links:
                activation_link = links[0]
                break

        if activation_link:
            break
        else:
            # Debug: in ra xem email có gì
            print(f"    [{attempt+1}/12] Có {len(docs)} email nhưng không tìm thấy link xác thực.")
    except Exception as e:
        print(f"    [{attempt+1}/12] Lỗi: {e}")

if not activation_link:
    print("[-] Không tìm thấy email xác thực (Timeout)!")
    # Debug: in nội dung email cuối cùng nếu có
    try:
        res = requests.get(f"https://smvmail.com/api/email?page=1&q=&email={email}", timeout=10)
        data = res.json()
        docs = data.get('data', {}).get('docs', [])
        if docs:
            content = json.dumps(docs[0])
            content = content.replace('\\/', '/')
            # Tìm tất cả URL trong email
            all_urls = re.findall(r'https?://[^\s"\\]+', content)
            print("[DEBUG] Các URL tìm thấy trong email:")
            for u in all_urls:
                print(f"  → {u}")
    except:
        pass
    sys.exit(1)

print(f"[v] Lấy được link xác thực: {activation_link[:70]}...")


# ============================================================
# BƯỚC 3: KÍCH HOẠT TÀI KHOẢN
# ============================================================
print("[*] 3. KÍCH HOẠT TÀI KHOẢN...")
# Trích lấy code từ link
code_match = re.search(r'code=([a-f0-9]+)', activation_link)
verify_code = code_match.group(1) if code_match else ""

res_verify = session.get(activation_link, allow_redirects=True)
if res_verify.status_code in [200, 303]:
    print("[v] Kích hoạt thành công!")
else:
    print(f"[-] Kích hoạt lỗi: {res_verify.status_code}")
    sys.exit(1)

time.sleep(1)

# ============================================================
# BƯỚC 4: LOGIN TRỰC TIẾP
# ============================================================
print(f"[*] 4. ĐĂNG NHẬP với {email}...")
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
    headers=headers_login,
    files=files_login,
    allow_redirects=True
)

vote_sid = session.cookies.get('vote_sid')
if not vote_sid:
    # Thử lấy từ response headers
    for cookie in res_login.cookies:
        if cookie.name == 'vote_sid':
            vote_sid = cookie.value
            session.cookies.set('vote_sid', vote_sid)
            break

if vote_sid:
    print(f"[v] Đăng nhập thành công! vote_sid: {vote_sid[:16]}...")
else:
    print(f"[-] Không lấy được Cookie login ({res_login.status_code}). Email có thể chưa được kích hoạt.")
    sys.exit(1)

# ============================================================
# BƯỚC 5: VOTE
# ============================================================
print(f"[*] 5. ĐANG VOTE cho {TARGET_ID}...")
headers_vote = headers_base.copy()
headers_vote['content-type']            = 'text/plain;charset=UTF-8'
headers_vote['next-action']             = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
headers_vote['next-router-state-tree']  = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
headers_vote['referer']                 = f'https://events.elle.vn{URL_PATH}'

vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
res_vote = session.post(f'https://events.elle.vn{URL_PATH}', headers=headers_vote, data=vote_payload.encode('utf-8'))

if res_vote.status_code == 200 and '"ok":false' not in res_vote.text:
    print("[v] VOTE THÀNH CÔNG!")
    
    # --- Lưu tài khoản lên Cloud DB thay vì file TXT ---
    try:
        from dotenv import load_dotenv
        from supabase import create_client, Client
        import datetime
        load_dotenv()
        
        url = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
        if url and key:
            supabase: Client = create_client(url, key)
            account_data = {
                "email": email,
                "password": password,
                "cookie_sid": vote_sid,
                "last_time_vote": datetime.datetime.utcnow().isoformat()
            }
            supabase.table("accounts").insert(account_data).execute()
            print("[v] Đã lưu tài khoản an toàn lên bảng 'accounts' của Supabase!")
        else:
            with open("accounts_voted.txt", "a", encoding="utf-8") as f:
                f.write(f"{email}|{password}|{vote_sid}\n")
    except Exception as e:
        print(f"[-] Lỗi lưu Acc lên DB: {e}")
else:
    print(f"[-] Vote thất bại: {res_vote.text[:200]}")

print("\n[★★★] HOÀN THÀNH! (Đăng ký → Xác thực Email → Login → Vote) [★★★]")

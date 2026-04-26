import requests
import json
import os
import sys
import random
import string
import time
import re
import urllib.parse

# Fix lỗi hiển thị tiếng Việt trên Terminal Windows
sys.stdout.reconfigure(encoding='utf-8')

# ---------- Hàm lấy token từ DB (Có vòng lặp chờ) ----------
def get_fresh_token():
    try:
        from dotenv import load_dotenv
        from supabase import create_client, Client
        import os
        load_dotenv()
        
        url = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
        if not url or not key:
            return ""
            
        supabase: Client = create_client(url, key)
        res = supabase.rpc("pop_token").execute()
        return res.data if res.data else ""
    except Exception as e:
        pass
    return ""

def wait_for_token(task_name):
    print(f"[*] Đang chờ rình Token cho {task_name}...")
    while True:
        token = get_fresh_token()
        if token:
            print(f"    [v] Mlem! Đã chộp được 1 token từ DB cho {task_name}!")
            return token
        # Nghỉ 3 giây trước khi quét lại DB tránh quá tải
        time.sleep(3)

def generate_random_string(length=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

token_reg = wait_for_token("Bước Đăng ký")
token_forgot = wait_for_token("Bước Quên Pass")
token_reset = wait_for_token("Bước Đổi Pass")

random_user = generate_random_string()
email = f"{random_user}@smvmail.com"
password = "Trieu@123"

# Dùng Session để lưu trữ Cookie sau khi đăng nhập thành công
session = requests.Session()

print(f"[*] 1. ĐĂNG KÝ TÀI KHOẢN: Username: {random_user} | Email: {email} | Pass: {password}")

headers_base = {
    'accept': 'text/x-component',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://events.elle.vn',
    'priority': 'u=1, i',
    'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
}

# --- BƯỚC 1: ĐĂNG KÝ ---
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
    # Đợi 3 giây để server cập nhật database trước khi gọi Quên mật khẩu
    time.sleep(3)
else:
    print(f"[-] Lỗi đăng ký: {res_reg.status_code}")
    print("[-] Lỗi Rate Limit khi đăng ký. Vui lòng đổi IP.")
    exit(1)


# --- BƯỚC 2: QUÊN MẬT KHẨU ---
print(f"\n[*] 2. GỬI YÊU CẦU QUÊN MẬT KHẨU CHO EMAIL {email}...")
headers_forgot = headers_base.copy()
headers_forgot['next-action'] = '315f786e78979a0bfca55b4ebcf648cf51d986b3'
headers_forgot['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%22forgot-password%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fforgot-password%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
headers_forgot['referer'] = 'https://events.elle.vn/forgot-password'

files_forgot = [
    ('1_email', (None, email)),
    ('1_cf-turnstile-response', (None, token_forgot)),
    ('1_cf-turnstile-response', (None, token_forgot)),
    ('0', (None, '[{"error":"","success":""},"$K1"]')),
]

res_forgot = session.post('https://events.elle.vn/forgot-password', headers=headers_forgot, files=files_forgot)
if res_forgot.status_code == 200:
    print("[v] Đã gửi yêu cầu reset mật khẩu!")
else:
    print(f"[-] Lỗi gửi yêu cầu: {res_forgot.status_code}")


# --- BƯỚC 3: ĐỌC MAIL LẤY CODE ---
print("\n[*] 3. ĐANG CHỜ EMAIL CHỨA LINK RESET PASSWORD TỪ SMVMAIL (Tối đa 60s)...")
reset_code = None

for _ in range(12):
    time.sleep(5)
    try:
        res = requests.get(f"https://smvmail.com/api/email?page=1&q=&email={email}", timeout=10)
        data = res.json()
        docs = data.get('data', {}).get('docs', [])
        
        # Có thể có 2 email (1 cái đăng ký, 1 cái quên pass), ta lặp qua hết
        for doc in docs:
            email_content = json.dumps(doc)
            email_content = email_content.replace('\\/', '/')
            
            # Tìm code reset trong link
            links = re.findall(r'code=([a-f0-9]{50,})', email_content)
            if links:
                reset_code = links[0]
                break
                
        if reset_code:
            break
    except Exception as e:
        pass

if not reset_code:
    print("[-] Không tìm thấy email chứa code đổi mật khẩu (Timeout)!")
    exit(1)
    
print(f"[v] Lấy được Reset Code: {reset_code[:15]}...")


# --- BƯỚC 4: ĐỔI MẬT KHẨU ---
print("\n[*] 4. ĐANG GỬI YÊU CẦU ĐỔI MẬT KHẨU VÀ TỰ ĐỘNG LOGIN...")
headers_reset = headers_base.copy()
headers_reset['next-action'] = 'e55f2a8c002ab55945fde53be82c573b2b86d65b'
headers_reset['referer'] = f'https://events.elle.vn/reset-password?code={reset_code}'

# Tạo router state tree động dựa trên mã code để khớp y hệt Next.js
router_tree = f'["", {{"children": ["reset-password", {{"children": ["__PAGE__?{{\\"code\\":\\"{reset_code}\\"}}", {{}}, "/reset-password?code={reset_code}", "refresh"]}}]}}, null, null, true]'
headers_reset['next-router-state-tree'] = urllib.parse.quote(router_tree)

files_reset = [
    ('1_$ACTION_REF_1', (None, '')),
    ('1_$ACTION_1:0', (None, '{"id":"e55f2a8c002ab55945fde53be82c573b2b86d65b","bound":"$@1"}')),
    ('1_$ACTION_1:1', (None, '[{"error":"","success":""}]')),
    ('1_$ACTION_KEY', (None, 'k904744799')),
    ('1_code', (None, reset_code)),
    ('1_returnTo', (None, '/')),
    ('1_password', (None, password)),
    ('1_passwordConfirmation', (None, password)),
    ('1_cf-turnstile-response', (None, token_reset)),
    ('1_cf-turnstile-response', (None, token_reset)),
    ('0', (None, '[{"error":"","success":""},"$K1"]')),
]

res_reset = session.post(f'https://events.elle.vn/reset-password?code={reset_code}', headers=headers_reset, files=files_reset)
if res_reset.status_code == 200:
    print("[v] Đã đổi mật khẩu và đăng nhập thành công!")
    # Kiểm tra cookie trực tiếp từ headers nếu session jar bị trống
    if not session.cookies.get('vote_sid'):
        for cookie in res_reset.cookies:
            if cookie.name == 'vote_sid':
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
else:
    print(f"[-] Lỗi đổi mật khẩu: {res_reset.status_code}")

print("\n[*] HOÀN TẤT! COOKIE CỦA TÀI KHOẢN ĐÃ ĐĂNG NHẬP:")
# Hiển thị tất cả cookie đang có
cookie_list = session.cookies.get_dict()
print(cookie_list)

# --- BƯỚC 5: TỰ ĐỘNG BÌNH CHỌN (VOTE) ---
print("\n[*] 5. ĐANG GỬI LỆNH BÌNH CHỌN (VOTE)...")
headers_vote = headers_base.copy()
headers_vote['content-type'] = 'text/plain;charset=UTF-8'
headers_vote['next-action'] = '288bd3262db6e09085c5f3f89856bb17fb9abf1a'
headers_vote['next-router-state-tree'] = '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
headers_vote['referer'] = 'https://events.elle.vn/elle-beauty-awards-2026/nhan-vat'

# Payload Vote chứa thông tin nhân vật
# format: ["loại_giải", "id_ứng_viên", "url_trả_về"]
vote_payload = '["celebrity","69e1ff11df6e31bd3fa4c707","/elle-beauty-awards-2026/nhan-vat"]'

res_vote = session.post('https://events.elle.vn/elle-beauty-awards-2026/nhan-vat', headers=headers_vote, data=vote_payload.encode('utf-8'))

if res_vote.status_code == 200:
    print("[v] Bình chọn thành công! (Server trả về cục dữ liệu Next.js của cả trang web đã được ẩn đi để đỡ rối mắt)")
    
    # --- LƯU LẠI TÀI KHOẢN VÀO THẲNG BẢNG SUPABASE TỰ THÊM TIME_VOTE ---
    vote_sid = session.cookies.get('vote_sid')
    if vote_sid:
        try:
            from dotenv import load_dotenv
            from supabase import create_client, Client
            import datetime
            import os
            load_dotenv()
            
            url = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
            key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
            if url and key:
                supabase: Client = create_client(url, key)
                account_data = {
                    "email": email,
                    "password": password,
                    "cookie_sid": vote_sid,
                    "last_time_vote": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                supabase.table("accounts").insert(account_data).execute()
                print("[v] Đã lưu tài khoản an toàn lên bảng 'accounts' của Supabase!")
            else:
                with open("accounts_voted.txt", "a", encoding="utf-8") as f:
                    f.write(f"{email}|{password}|{vote_sid}\n")
        except Exception as e:
            print(f"[-] Lỗi lưu Acc lên DB: {e}")
else:
    print("[-] Có lỗi xảy ra khi vote:", res_vote.status_code, res_vote.text[:200])

print("\n[★★★] ĐÃ HOÀN THÀNH QUÁ TRÌNH TỪ ĐĂNG KÝ ĐẾN VOTE CHO 1 TÀI KHOẢN! [★★★]")


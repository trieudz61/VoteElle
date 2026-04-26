"""
Google OAuth Login → Vote → Lưu Supabase
Dùng nodriver (Chrome hệ thống) để login Google, lấy vote_sid, rồi vote bằng requests.
"""
import asyncio
import requests
import os
import sys
import datetime
import threading
import nodriver as uc
import nodriver.cdp.network as cdp_net
from dotenv import load_dotenv
from supabase import create_client, Client

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

# --- File Operations with Locks ---
file_lock = threading.Lock()

def remove_from_main_file(line_to_remove):
    with file_lock:
        if not os.path.exists(ACCOUNT_FILE): return
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip() != line_to_remove.strip():
                    f.write(line)

def append_to_failed_file(line_to_add):
    with file_lock:
        with open("accounts_failed.txt", "a", encoding="utf-8") as f:
            f.write(line_to_add.strip() + "\n")

# ── Patch nodriver bug: Chrome 125+ bỏ 'sameParty' field ──
_orig_cookie_from_json = cdp_net.Cookie.from_json
def _patched_cookie_from_json(json_data):
    json_data.setdefault('sameParty', False)
    return _orig_cookie_from_json(json_data)
cdp_net.Cookie.from_json = staticmethod(_patched_cookie_from_json)

# ================= CẤU HÌNH =================
TARGET_ID  = "69e1ff11df6e31bd3fa4c707"
CATEGORY   = "celebrity"
URL_PATH   = "/elle-beauty-awards-2026/nhan-vat"
CONNECT_URL = "https://baseapi.elle.vn/connect/google?callback=https%3A%2F%2Fevents.elle.vn%2Flogin%2Fcallback%3FreturnTo%3D%252Felle-beauty-awards-2026"
NUM_WORKERS = 4  # Số luồng (Chrome) chạy đồng thời

ACCOUNT_FILE = "accounts_google.txt"

# Đọc danh sách tài khoản từ file
if not os.path.exists(ACCOUNT_FILE):
    with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
        f.write("email1@domain.com|password123\n")
    print(f"⚠️ Đã tạo file '{ACCOUNT_FILE}' mẫu. Vui lòng thêm các tài khoản (định dạng email|password) vào file này rồi chạy lại script.")
    sys.exit(0)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip() and '|' in line]

if not ALL_ACCOUNTS:
    print(f"❌ File '{ACCOUNT_FILE}' đang trống. Vui lòng thêm tài khoản.")
    sys.exit(0)

# Lấy danh sách email đã lưu trên DB
print(f"[*] Xin đợi... Đang kiểm tra Supabase để loại bỏ tài khoản trùng lặp...")
supabase = get_supabase()
try:
# Lấy toàn bộ column email (chia nhỏ chunk 100 để không vượt quá giới hạn URL của API và limit 1000 row)
    emails_to_check = [acc.split("|")[0].strip() for acc in ALL_ACCOUNTS]
    db_emails = set()
    for i in range(0, len(emails_to_check), 100):
        chunk = emails_to_check[i:i+100]
        res = supabase.table("accounts").select("email").in_("email", chunk).execute()
        if hasattr(res, 'data') and res.data:
            db_emails.update(item['email'] for item in res.data)
except Exception as e:
    print(f"⚠️ Lỗi kết nối DB: {e}")
    db_emails = set()

ACCOUNTS = []
for acc in ALL_ACCOUNTS:
    email = acc.split("|")[0].strip()
    if email not in db_emails:
        ACCOUNTS.append(acc)

# Ghi lại những tài khoản chưa có lên file (xoá các tài khoản đã làm rồi)
with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
    for acc in ACCOUNTS:
        f.write(acc + "\n")

if len(ALL_ACCOUNTS) > len(ACCOUNTS):
    print(f"[*] Đã lọc và HIỄN TIỄN {len(ALL_ACCOUNTS) - len(ACCOUNTS)} tài khoản đã có trên Supabase khỏi file.")

if not ACCOUNTS:
    print(f"✅ Tuyệt vời! Toàn bộ 100% tài khoản trong file đều đã Login thành công trên Supabase.")
    sys.exit(0)


# ==========================================
# BƯỚC 1: LOGIN GOOGLE → LẤY vote_sid
# ==========================================
async def get_vote_sid_google(index: int, email: str, password: str) -> str | None:
    print(f"[{index}] 🌐 Mở Chrome → Google OAuth...")
    
    # Tính toán vị trí cửa sổ dựa trên index nhưng xoay vòng theo NUM_WORKERS
    # Giới hạn cửa sổ chỉ xếp trong N khu vực thay vì tràn màn hình
    slot = index % max(NUM_WORKERS, 1)
    x_pos = slot * 310
    config = uc.Config()
    config.add_argument('--window-size=1,1')
    config.add_argument('--window-position=-10000,0')
    config.add_argument('--disable-sync')
    config.add_argument('--no-first-run')
    config.add_argument('--password-store=basic')
    config.add_argument('--disable-gpu')
    config.add_argument('--mute-audio')
    
    browser = await uc.start(headless=False, config=config)

    try:
        tab = await browser.get(CONNECT_URL)

        # Chờ Google OAuth page
        for _ in range(20):
            await tab.sleep(0.5)
            if 'accounts.google.com' in tab.url:
                break

        # Nhập email
        print(f"[{index}] 📧 Nhập email: {email}")
        email_input = await tab.select('input[type="email"]', timeout=15)
        await tab.sleep(1)
        await email_input.send_keys(email)
        await tab.sleep(0.5)
        try:
            next_btn = await tab.select('#identifierNext button', timeout=3)
            await next_btn.click()
        except:
            pass

        # Chờ password page
        for _ in range(30):
            await tab.sleep(0.5)
            if 'challenge' in tab.url or 'pwd' in tab.url:
                break
        await tab.sleep(1.5)

        pass_input = await tab.select('input[type="password"]', timeout=15)
        print(f"[{index}] 🔑 Nhập password...")
        await pass_input.send_keys(password)
        await tab.sleep(0.5)
        try:
            next_btn2 = await tab.select('#passwordNext button', timeout=3)
            await next_btn2.click()
        except:
            pass

        # Xử lý consent + redirect
        tos_clicked = False
        consent_clicked = False
        for i in range(60):
            await tab.sleep(0.5)
            url = tab.url

            # ToS (account mới)
            if not tos_clicked and 'speedbump/gaplustos' in url:
                print(f"[{index}] 📜 Click 'Tôi hiểu' (ToS)...")
                try:
                    confirm_btn = await tab.select('input#confirm', timeout=5)
                    if confirm_btn:
                        await confirm_btn.click()
                        tos_clicked = True
                        await tab.sleep(3)
                except:
                    pass
                continue

            # OAuth consent
            if not consent_clicked and 'accounts.google.com' in url and 'challenge' not in url and 'identifier' not in url and 'speedbump' not in url:
                try:
                    # Hỗ trợ cả tiếng Anh lẫn tiếng Việt
                    btn = None
                    try:
                        btn = await tab.find("Continue", best_match=True)
                    except:
                        pass
                        
                    if not btn:
                        try:
                            btn = await tab.find("Tiếp tục", best_match=True)
                        except:
                            pass

                    if btn:
                        print(f"[{index}] 🤝 Click 'Continue/Tiếp tục' (consent)...")
                        await btn.click()
                        consent_clicked = True
                        await tab.sleep(2)
                except:
                    pass

            # Đã về elle.vn → lấy sid
            if 'events.elle.vn' in url and 'error' not in url:
                try:
                    all_cookies = await browser.cookies.get_all()
                    vote_sid = next((c.value for c in all_cookies if c.name == 'vote_sid'), None)
                    if vote_sid:
                        print(f"[{index}] ✅ Lấy cookie thành công: {vote_sid[:20]}...")
                    return vote_sid
                except:
                    pass
                return None

            if 'error=Grant' in url or 'misconfigured' in url:
                print(f"[{index}] ❌ Session error")
                break

        return None
    except Exception as e:
        print(f"[{index}] ❌ Chrome Error: {e}")
        return None
    finally:
        try:
            browser.stop()
        except:
            pass

# ==========================================
# BƯỚC 2: VOTE BẰNG REQUESTS
# ==========================================
def vote_with_sid(vote_sid: str) -> tuple[bool, str]:
    headers_vote = {
        'accept': 'text/x-component',
        'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
        'content-type': 'text/plain;charset=UTF-8',
        'origin': 'https://events.elle.vn',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'next-action': '288bd3262db6e09085c5f3f89856bb17fb9abf1a',
        'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
        'referer': f'https://events.elle.vn{URL_PATH}',
    }
    cookies = {'vote_sid': vote_sid}
    vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'

    res = requests.post(
        f'https://events.elle.vn{URL_PATH}',
        headers=headers_vote,
        cookies=cookies,
        data=vote_payload.encode('utf-8')
    )

    if res.status_code == 200 and '"ok":false' not in res.text:
        return True, ""
    else:
        return False, f"Status: {res.status_code}, Response: {res.text[:200]}"


# ==========================================
# BƯỚC 3: CHẠY TOÀN BỘ FLOW
# ==========================================
async def run_one_account(index: int, account_line: str):
    parts = account_line.strip().split('|')
    if len(parts) != 2:
        print(f"[{index}] ❌ Format sai: {account_line}")
        await asyncio.to_thread(remove_from_main_file, account_line)
        await asyncio.to_thread(append_to_failed_file, account_line)
        return False

    email, password = parts
    success = False
    error_msg = ""

    print(f"\n[{index}] {'='*40}")
    print(f"[{index}] 🚀 Bắt đầu cho: {email}")

    try:
        # Login Google → lấy vote_sid
        vote_sid = await get_vote_sid_google(index, email, password)
        if not vote_sid:
            error_msg = "Không lấy được vote_sid (Lỗi Login hoặc Crash)"
        else:
            # Vote
            print(f"[{index}] 🗳️ Đang Vote cho {TARGET_ID}...")
            # Chạy requests trong thread để không block asyncio loop
            vote_ok, e_msg = await asyncio.to_thread(vote_with_sid, vote_sid)
            
            if vote_ok:
                print(f"[{index}] ✅ VOTE THÀNH CÔNG!")
                # Lưu Supabase
                try:
                    await asyncio.to_thread(
                        lambda: get_supabase().table("accounts").insert({
                            "email": email,
                            "password": password,
                            "cookie_sid": vote_sid,
                            "last_time_vote": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }).execute()
                    )
                    print(f"[{index}] 💾 Đã lưu DB Supabase")
                except Exception as db_e:
                    print(f"[{index}] ⚠️ Lỗi lưu DB: {db_e}")
                
                success = True
            else:
                error_msg = f"Vote thất bại: {e_msg.strip()}"
    except Exception as e:
        error_msg = f"Lỗi không xác định: {e}"

    # Luôn xoá khỏi file gốc để làm tới đâu gọn tới đó
    await asyncio.to_thread(remove_from_main_file, account_line)

    if success:
        return True
    else:
        print(f"[{index}] ❌ {error_msg}")
        await asyncio.to_thread(append_to_failed_file, account_line)
        return False

async def bounded_run(sem, index, acc):
    async with sem:
        return await run_one_account(index, acc)


async def main():
    print("=" * 55)
    print(f"  GOOGLE LOGIN → VOTE ({len(ACCOUNTS)} tài khoản, {NUM_WORKERS} luồng CÙNG LÚC)")
    print("=" * 55)

    success = 0
    fail = 0

    sem = asyncio.Semaphore(NUM_WORKERS)
    tasks = [bounded_run(sem, i, acc) for i, acc in enumerate(ACCOUNTS, 1)]
    
    # Chạy tất cả các luồng cùng lúc với giới hạn Semaphore
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, r in enumerate(results, 1):
        if isinstance(r, Exception):
            print(f"[{i}] Ngoại lệ xảy ra: {r}")
            fail += 1
        elif r:
            success += 1
        else:
            fail += 1

    print(f"\n{'='*55}")
    print(f"  KẾT QUẢ ĐA LUỒNG: ✅ {success} | ❌ {fail}")
    print(f"{'='*55}")


if __name__ == "__main__":
    asyncio.run(main())

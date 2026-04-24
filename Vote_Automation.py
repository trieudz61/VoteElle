import requests
import sys
import time
import os

sys.stdout.reconfigure(encoding='utf-8')

# ================= CẤU HÌNH VOTE =================
# ID của nhân vật bạn muốn dồn vote
TARGET_ID = "69e1fabda51bd7bcd50c5b30" # Thay ID Idol của bạn vào đây

# (Thường không cần đổi nếu vẫn vote danh sách Nhân Vật)
CATEGORY = "celebrity"
URL_PATH = "/elle-beauty-awards-2026/nhan-vat"
# =================================================

headers_vote = {
    'accept': 'text/x-component',
    'accept-language': 'en-US,en;q=0.9,vi;q=0.8,fr-FR;q=0.7,fr;q=0.6,am;q=0.5,zh-CN;q=0.4,zh;q=0.3',
    'content-type': 'text/plain;charset=UTF-8',
    'next-action': '288bd3262db6e09085c5f3f89856bb17fb9abf1a',
    'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
    'origin': 'https://events.elle.vn',
    'referer': f'https://events.elle.vn{URL_PATH}',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'
}

vote_payload = f'["{CATEGORY}","{TARGET_ID}","{URL_PATH}"]'
api_endpoint = f'https://events.elle.vn{URL_PATH}'

if not os.path.exists("accounts_voted.txt"):
    print("[-] Không tìm thấy file accounts_voted.txt. Vui lòng chạy Reg_ForgotPass.py trước để tích luỹ tài khoản.")
    sys.exit(1)

# Đọc tài khoản
with open("accounts_voted.txt", "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

if not lines:
    print("[-] File accounts_voted.txt đang trống. Bạn chưa lưu được tài khoản nào.")
    sys.exit(1)

print("=" * 50)
print(f"[*] BẮT ĐẦU VOTE TỰ ĐỘNG HÀNG LOẠT")
print(f"[*] Số lượng tài khoản: {len(lines)}")
print(f"[*] Target ID: {TARGET_ID} ({CATEGORY})")
print("=" * 50)

success_count = 0
fail_count = 0

for i, line in enumerate(lines, 1):
    parts = line.split("|")
    if len(parts) >= 3:
        email = parts[0]
        vote_sid = parts[-1]
        
        print(f"[{i}/{len(lines)}] Đang vote bằng: {email} ...", end=" ")
        
        cookies = {'vote_sid': vote_sid}
        
        try:
            res = requests.post(api_endpoint, headers=headers_vote, cookies=cookies, data=vote_payload.encode('utf-8'))
            
            if '"ok":false' in res.text or 'Báº¡n chá»‰ cÃ³ thá»ƒ bÃ¬nh chá» n' in res.text:
                print("[-] Thất bại (Hết lượt/Đã vote)")
                fail_count += 1
            elif res.status_code == 200:
                print("[v] Thành công!")
                success_count += 1
            else:
                print(f"[-] Lỗi ({res.status_code})")
                fail_count += 1
                
        except Exception as e:
            print(f"[-] Lỗi kết nối: {str(e)}")
            fail_count += 1
            
        # Nghỉ 1 giây để Server không nghi ngờ bot
        time.sleep(1)
    else:
        print(f"[{i}/{len(lines)}] Dòng dữ liệu bị lỗi format: {line}")

print("\n" + "=" * 50)
print(f"[★★★] HOÀN TẤT VOTE HÀNG LOẠT [★★★]")
print(f"    - Thành công : {success_count} lượt")
print(f"    - Thất bại   : {fail_count} lượt")
print("=" * 50)

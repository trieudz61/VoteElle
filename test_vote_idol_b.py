import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

headers_vote = {
    'accept': 'text/x-component',
    'accept-language': 'en-US,en;q=0.9,vi;q=0.8,fr-FR;q=0.7,fr;q=0.6,am;q=0.5,zh-CN;q=0.4,zh;q=0.3',
    'content-type': 'text/plain;charset=UTF-8',
    'next-action': '288bd3262db6e09085c5f3f89856bb17fb9abf1a',
    'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
    'origin': 'https://events.elle.vn',
    'referer': 'https://events.elle.vn/elle-beauty-awards-2026/nhan-vat',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'
}

# Thay bằng Cookie của nick vừa test xong
cookies = {
    'vote_sid': '844a3717-aa94-4fe5-a4d9-e8433b4ded3a'
}

# Thử vote cho Idol A (ID khác) để xem hệ thống có cho phép không
vote_payload = '["celebrity","69e1ff11df6e31bd3fa4c707","/elle-beauty-awards-2026/nhan-vat"]'

res = requests.post('https://events.elle.vn/elle-beauty-awards-2026/nhan-vat', headers=headers_vote, cookies=cookies, data=vote_payload.encode('utf-8'))

print("Status:", res.status_code)
# Phân tích xem có lỗi gì trong response trả về của Next.js không
# Ở Next.js Server Actions, lỗi thực sự thường trả về kiểu "ok":false
if '"ok":false' in res.text or 'Báº¡n chá»‰ cÃ³ thá»ƒ bÃ¬nh chá» n' in res.text:
    print("[-] Bị chặn! Hệ thống báo đã đạt giới hạn vote.")
    # In ra một phần nội dung lỗi
    print(res.text[:500])
else:

    print("[v] Vẫn trả về data giao diện. Rất có khả năng là VOTE THÀNH CÔNG cho Idol B!")

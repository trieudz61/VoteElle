"""
export_delete_smvmail.py
- Tải toàn bộ email có đuôi @hadanu.us từ Supabase
- Lưu danh sách email ra file smvmail_exported.txt
- Xoá toàn bộ các tài khoản này khỏi bảng accounts trong Supabase
"""
import sys
import os
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

SUPABASE_URL = 'https://lzwxjlpmjfudlwesvsjp.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo'

def main():
    print("[*] Đang kết nối Supabase...")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    all_smv_emails = []
    offset = 0
    PAGE_SIZE = 1000

    print("[*] Đang tải dữ liệu các email @hadanu.us...")
    while True:
        try:
            res = sb.table('accounts').select('email').like('email', '%@hadanu.us').range(offset, offset + PAGE_SIZE - 1).execute()
            rows = res.data or []
            if not rows:
                break
            
            for r in rows:
                all_smv_emails.append(r['email'])
                
            print(f"    ... Đã tải {len(all_smv_emails)} email", end="\r")
            
            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        except Exception as e:
            print(f"\n❌ Lỗi khi tải dữ liệu: {e}")
            return

    total = len(all_smv_emails)
    print()
    if total == 0:
        print("Không tìm thấy tài khoản @hadanu.us nào trong database.")
        return

    print(f"[*] Tìm thấy tổng cộng {total} tài khoản @hadanu.us.")
    
    # 1. Ghi ra file TXT
    txt_file = "smvmail_exported.txt"
    txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), txt_file)
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            for email in all_smv_emails:
                f.write(email + "\n")
        print(f"✅ Đã lưu {total} email vào file: {txt_path}")
    except Exception as e:
        print(f"❌ Lỗi ghi file TXT: {e}")
        return

    # 2. Xóa khỏi DB bằng điều kiện LIKE
    print(f"[*] Đang yêu cầu Supabase xóa toàn bộ tài khoản @hadanu.us...")
    try:
        sb.table('accounts').delete().like('email', '%@hadanu.us').execute()
        print(f"✅ Đã gửi lệnh XÓA thành công toàn bộ email @hadanu.us khỏi Database!")
    except Exception as e:
        print(f"❌ Lỗi khi xóa trên DB: {e}")

if __name__ == "__main__":
    main()

import sys
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions
import os
import time
import json
import tempfile

# --- CẤU HÌNH CHO TURNSTILE ---
SITE_KEY = "0x4AAAAAACnJ4TeSqCnnHCkt" # Mã của WeChoice
DOMAIN = "events.elle.vn"

def save_to_json(data):
    # Dù tên là save_to_json nhưng giờ đây nó tự động đầy thẳng lên cấu hình Supabase Cloud!
    if isinstance(data, dict) and "token" in data:
        tokens = [data["token"]]
    elif isinstance(data, list):
        tokens = [t["token"] if isinstance(t, dict) else t for t in data]
    else:
        tokens = []

    if not tokens:
        return

    try:
        from dotenv import load_dotenv
        from supabase import create_client, Client
        load_dotenv()
        url = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
        if not url or not key:
            print("[-] LỖI: Vui lòng dán URL và KEY vào file .env")
            return
            
        supabase: Client = create_client(url, key)
        
        for token in tokens:
            supabase.table("turnstile_tokens").insert({"token": token}).execute()
        print(f"[v] Đã nạp thành công {len(tokens)} TOKEN TƯƠI MỚI vào Supabase!")
    except Exception as e:
        print(f"[-] Lỗi nạp dữ liệu lên Supabase: {e}")
def main():
    co = ChromiumOptions()
    # Mẹo: Đẩy cửa sổ ra khỏi màn hình để ẩn mà không bị Cloudflare phát hiện là Bot (Headless)
    co.set_argument('--window-position=0,0')
    co.set_argument('--window-size=200,350')
    
    # Sử dụng profile mới hoàn toàn để không bị lưu session cũ
    tmp_dir = tempfile.mkdtemp()
    co.set_argument(f'--user-data-dir={tmp_dir}')
    
    # Mở trình duyệt
    page = ChromiumPage(co)
    
    print(f"[*] Đang truy cập trực tiếp trang https://{DOMAIN} để vượt qua kiểm tra Domain và HSTS...")
    page.get(f"https://{DOMAIN}")
    
    collected_tokens = []
    attempt = 1
    
    while len(collected_tokens) < 10:
        i = len(collected_tokens) + 1
        print(f"\n[***] LẦN {i}/3 (Thử lần {attempt}) - Đang tiêm mã Turnstile widget vào trang...")
        js_code = f"""
            // Xóa nội dung trang web để tránh xung đột
            document.body.innerHTML = '';
            document.body.style.background = '#f0f0f0';
            document.title = 'Turnstile Local Solver {i}/3';

            var div = document.createElement('div');
            div.id = 'tw';
            div.style.position = 'fixed';
            div.style.top = '50px';
            div.style.left = '50px';
            div.style.zIndex = '999999';
            div.style.background = 'white';
            div.style.padding = '30px';
            div.style.borderRadius = '10px';
            div.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
            document.body.appendChild(div);

            var title = document.createElement('h3');
            title.innerText = 'Đang giải mã Turnstile lần {i}/3...';
            title.style.fontFamily = 'sans-serif';
            title.style.marginTop = '0';
            div.appendChild(title);

            var widgetBox = document.createElement('div');
            widgetBox.id = 'widget-box';
            div.appendChild(widgetBox);

            window.__TOKEN__ = null;
            window.onloadTurnstileCallback = function() {{
                turnstile.render('#widget-box', {{
                    sitekey: '{SITE_KEY}',
                    callback: function(token) {{
                        window.__TOKEN__ = token;
                    }}
                }});
            }};
            
            // Xóa script cũ nếu có
            var oldScript = document.getElementById('cf-turnstile-script');
            if (oldScript) oldScript.remove();
            
            var script = document.createElement('script');
            script.id = 'cf-turnstile-script';
            script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback&render=explicit";
            script.async = true;
            document.head.appendChild(script);
        """
        page.run_js(js_code)
        
        print("[*] Đang chờ giải quyết Turnstile (vui lòng đợi hoặc click nếu có yêu cầu)...")
        
        max_wait = 5
        start_time = time.time()
        token = None
        
        while time.time() - start_time < max_wait:
            try:
                token = page.run_js('return window.__TOKEN__;')
                if token and token != "":
                    print(f"\n[!] ĐÃ LẤY ĐƯỢC TURNSTILE TOKEN LẦN {i}: \n{token[:50]}...")
                    # Đẩy thẳng trực tiếp token này lên Supabase ngay lập tức!
                    save_to_json({"token": token})
                    collected_tokens.append(token)
                    break
            except Exception as e:
                pass
                
            time.sleep(1)
            
            # Click tự động nếu Turnstile hiển thị checkbox
            try:
                iframe = page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0)
                if iframe:
                    iframe.click()
            except:
                pass
                
        if not token:
            print(f"[-] Hết thời gian chờ {max_wait}s. Không nhận được token, tải lại trang và thử lại...")
            
        # Refresh trang để reset Cloudflare state cho lần lấy kế tiếp
        if len(collected_tokens) < 3:
            page.refresh()
            time.sleep(2)
            
        attempt += 1

    if not collected_tokens:
        print("[-] Lỗi: Không lấy được token nào sau 3 lần thử!")
        
    # Tùy chọn: Đóng trình duyệt sau khi xong
    page.quit()

if __name__ == "__main__":
    main()
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
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captcha_data.json")
    # Nếu đang lưu mảng tokens thì append vào mảng cũ nếu có
    if isinstance(data, dict) and "token" in data:
        # Giữ tương thích ngược với code cũ, biến nó thành mảng
        tokens = [data["token"]]
    elif isinstance(data, list):
        tokens = data
    else:
        tokens = []

    # Thử đọc mảng cũ nếu có để cộng dồn (tránh ghi đè nếu chạy nhiều lần)
    existing_tokens = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, list):
                    existing_tokens = content
                elif isinstance(content, dict) and "token" in content:
                    existing_tokens = [content["token"]]
        except:
            pass

    existing_tokens.extend(tokens)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_tokens, f, ensure_ascii=False, indent=4)
    print(f"[v] Đã lưu {len(tokens)} token mới vào: {file_path}. Tổng cộng: {len(existing_tokens)} tokens.")

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
    
    while len(collected_tokens) < 3:
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
                    print(f"\\n[!] ĐÃ LẤY ĐƯỢC TURNSTILE TOKEN LẦN {i}: \\n{token[:50]}...")
                    collected_tokens.append({
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "captcha_type": "turnstile",
                        "domain": DOMAIN,
                        "token": token
                    })
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

    # Lưu mảng 3 tokens vào file JSON cộng dồn
    if collected_tokens:
        save_to_json(collected_tokens)
    else:
        print("[-] Lỗi: Không lấy được token nào sau 3 lần thử!")
        
    # Tùy chọn: Đóng trình duyệt sau khi xong
    page.quit()

if __name__ == "__main__":
    main()
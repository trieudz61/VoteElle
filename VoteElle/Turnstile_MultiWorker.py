import sys
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions
import os
import time
import json
import tempfile
import threading
import datetime

# =============== CẤU HÌNH ===============
SITE_KEY  = "0x4AAAAAACnJ4TeSqCnnHCkt"
DOMAIN    = "events.elle.vn"
NUM_TABS  = 3         # Số tab chạy song song
TARGET    = 99999     # Chạy vô hạn (đặt số cụ thể nếu muốn dừng)
MAX_POOL  = 30       # Giới hạn tối đa số token lưu trong DB cùng lúc
# ========================================

from dotenv import load_dotenv
from supabase import create_client
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzwxjlpmjfudlwesvsjp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Lock để tránh race condition khi in log
print_lock = threading.Lock()
total_collected = 0
total_lock = threading.Lock()

def log(tab_id, msg):
    with print_lock:
        print(f"[Tab {tab_id}] {msg}")

def push_token(token, tab_id):
    global total_collected
    try:
        supabase.table("turnstile_tokens").insert({"token": token}).execute()
        with total_lock:
            total_collected += 1
            count = total_collected
        log(tab_id, f"[v] TOKEN #{count} đã lên Supabase! {token[:30]}...")
    except Exception as e:
        log(tab_id, f"[-] Lỗi Supabase: {e}")

def cleanup_worker():
    """Luồng chạy ngầm tự động xóa token quá 3 phút và giới hạn số lượng"""
    while True:
        try:
            # 1. Xóa các token quá cũ (>3 phút)
            three_mins_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=3)
            iso_time = three_mins_ago.isoformat()
            
            res_old = supabase.table("turnstile_tokens").delete().lte("created_at", iso_time).execute()
            deleted_old = len(res_old.data) if hasattr(res_old, 'data') and res_old.data else 0
            
            # 2. Xóa các token thừa (giữ lại tối đa MAX_POOL token mới nhất)
            res_all = supabase.table("turnstile_tokens").select("token").order("created_at", desc=True).execute()
            deleted_excess = 0
            if hasattr(res_all, 'data') and res_all.data and len(res_all.data) > MAX_POOL:
                excess_tokens = [item["token"] for item in res_all.data[MAX_POOL:]]
                
                # Chia mảng ra cắt dần nếu quá dài (Supabase limit url / payload)
                chunk_size = 50
                for i in range(0, len(excess_tokens), chunk_size):
                    chunk = excess_tokens[i:i + chunk_size]
                    supabase.table("turnstile_tokens").delete().in_("token", chunk).execute()
                    deleted_excess += len(chunk)
            
            total_deleted = deleted_old + deleted_excess
            if total_deleted > 0:
                with print_lock:
                    print(f"\n[🧹 CLEANUP] Đã dọn {deleted_old} token cũ & {deleted_excess} token thừa (giữ tối đa {MAX_POOL}).\n")
        except Exception:
            pass # Bỏ qua lỗi mạng
            
        time.sleep(20) # Mỗi 20 giây kiểm tra 1 lần

JS_INJECT = """
    document.body.innerHTML = '';
    document.body.style.background = '#e8f5e9';

    var div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:30px;left:30px;background:white;padding:20px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:sans-serif;';
    div.innerHTML = '<h4 style="margin:0 0 10px">Tab {TAB_ID} - Đang lấy token...</h4>';
    document.body.appendChild(div);

    var box = document.createElement('div');
    box.id = 'widget-box';
    div.appendChild(box);

    window.__TOKEN__ = null;
    window.onloadTurnstileCallback = function() {
        turnstile.render('#widget-box', {
            sitekey: '{SITE_KEY}',
            callback: function(t) { window.__TOKEN__ = t; }
        });
    };

    var old = document.getElementById('cf-ts');
    if (old) old.remove();
    var s = document.createElement('script');
    s.id = 'cf-ts';
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback&render=explicit';
    s.async = true;
    document.head.appendChild(s);
"""

def worker(tab_id):
    """Mỗi worker chạy 1 ChromiumPage riêng biệt, liên tục lấy token."""
    while True:
        log(tab_id, "Đang khởi động trình duyệt...")
        
        co = ChromiumOptions()
        # Xếp cửa sổ theo hàng ngang để dễ quan sát
        x_pos = (tab_id - 1) * 220
        co.set_argument(f'--window-position={x_pos},0')
        co.set_argument('--window-size=210,350')
        # Dùng address riêng để tạo PROCESS Chrome hoàn toàn mới, không share với tab khác
        port = 9220 + tab_id
        co.set_argument(f'--remote-debugging-port={port}')
        tmp_dir = tempfile.mkdtemp()
        co.set_argument(f'--user-data-dir={tmp_dir}')
        co.auto_port()

        try:
            page = ChromiumPage(co)
            page.get(f"https://{DOMAIN}")
        except Exception as e:
            log(tab_id, f"Lỗi khởi tạo Chrome: {e}. Thử lại sau 3s...")
            time.sleep(3)
            continue
            
        log(tab_id, "Trình duyệt sẵn sàng, bắt đầu lấy token...")

        local_count = 0
        while local_count < 30:
            try:
                js = JS_INJECT.replace('{TAB_ID}', str(tab_id)).replace('{SITE_KEY}', SITE_KEY)
                page.run_js(js)

                # Chờ tối đa 8 giây
                start = time.time()
                token = None
                while time.time() - start < 8:
                    try:
                        token = page.run_js('return window.__TOKEN__;')
                        if token:
                            break
                    except:
                        pass
                    time.sleep(0.5)
                    # Thử click vào iframe checkbox nếu có
                    try:
                        iframe = page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0)
                        if iframe:
                            iframe.click()
                    except:
                        pass

                if token:
                    push_token(token, tab_id)
                    local_count += 1
                    with total_lock:
                        if total_collected >= TARGET:
                            log(tab_id, f"Đủ {TARGET} token, dừng tab này.")
                            page.quit()
                            return
                else:
                    log(tab_id, "Timeout, refresh và thử lại...")

                # Refresh để reset cho lần tiếp theo
                page.refresh()
                time.sleep(1.5)

            except Exception as e:
                log(tab_id, f"Lỗi: {e}. Refresh trình duyệt lỗi...")
                time.sleep(2)
                try:
                    page.refresh()
                except:
                    break   # Trình duyệt Crash, thoát vòng lặp nội bộ để khởi động lại Chrome

        log(tab_id, f"🔄 Đã nạp đủ 30 token đợt này. Đóng để xả RAM...")
        try:
            page.quit()
        except:
            pass
        time.sleep(2)

if __name__ == "__main__":
    print(f"[*] KHỞI ĐỘNG {NUM_TABS} TAB SONG SONG - Đẩy token lên Supabase liên tục...")
    print(f"[*] Nhấn Ctrl+C để dừng bất cứ lúc nào.\n")

    # Bật luồng dọn rác token tự động
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()

    threads = []
    for i in range(1, NUM_TABS + 1):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(2)  # Delay nhỏ để các tab không mở cùng lúc

    try:
        while True:
            time.sleep(3)
            with total_lock:
                count = total_collected
            print(f"\n[STATS] Tổng token đã nạp: {count}/{TARGET}\n")
            if count >= TARGET:
                break
    except KeyboardInterrupt:
        pass
    print(f"\n[*] Đã dừng. Tổng cộng đã nạp {total_collected} token lên Supabase.")

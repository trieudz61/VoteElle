import sys
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions
import os
import time
import json
import tempfile
import threading
import datetime
import shutil

# =============== CẤU HÌNH ===============
SITE_KEY  = "0x4AAAAAACnJ4TeSqCnnHCkt"
DOMAIN    = "events.elle.vn"
NUM_TABS  = int(os.environ.get("NUM_TABS", 12))  # Env var hoặc mặc định
TARGET    = 99999     # Chạy vô hạn (đặt số cụ thể nếu muốn dừng)
MAX_POOL  = 60       # Giới hạn tối đa số token lưu trong DB cùng lúc
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
active_pages = []
pages_lock = threading.Lock()

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
        # Lấy pool count thực tế
        try:
            pool = supabase.table("turnstile_tokens").select("token", count="exact").execute()
            pool_count = pool.count if pool.count is not None else "?"
        except:
            pool_count = "?"
        log(tab_id, f"[v] TOKEN #{count} đã lên Supabase! Pool: {pool_count} | {token[:30]}...")
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
        # Tiết kiệm RAM
        co.set_argument('--window-size=210,350')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-background-networking')
        co.set_argument('--disable-sync')
        co.set_argument('--no-first-run')
        co.set_argument('--disable-default-apps')
        co.set_argument('--disable-translate')
        co.set_argument('--renderer-process-limit=1')
        co.set_argument('--disable-dev-shm-usage')
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36')
        # Dùng address riêng để tạo PROCESS Chrome hoàn toàn mới, không share với tab khác
        port = 9220 + tab_id
        co.set_argument(f'--remote-debugging-port={port}')
        # Dùng profile cố định để nuôi trust (tránh bị Cloudflare bắt bot do profile trống)
        profile_dir = os.path.join(os.getcwd(), f"chrome_profiles/tab_{tab_id}")
        os.makedirs(profile_dir, exist_ok=True)
        co.set_argument(f'--user-data-dir={profile_dir}')
        co.auto_port()

        try:
            page = ChromiumPage(co)
            
            # Khắc phục lỗi tràn RAM: Đóng tất cả các tab cũ bị kẹt do Chrome không thoát hẳn
            try:
                tabs = page.tab_ids
                if len(tabs) > 1:
                    for t_id in tabs[:-1]:
                        page.get_tab(t_id).close()
            except:
                pass

            with pages_lock:
                active_pages.append(page)
            # Xếp cửa sổ dạng lưới: 5 cột, mỗi ô 210x350
            try:
                cols_per_row = 5
                w, h = 210, 350
                col = (tab_id - 1) % cols_per_row
                row = (tab_id - 1) // cols_per_row
                x, y = col * w, row * h
                win_id = page.run_cdp('Browser.getWindowForTarget')['windowId']
                page.run_cdp('Browser.setWindowBounds',
                             windowId=win_id,
                             bounds={'left': x, 'top': y, 'width': w, 'height': h, 'windowState': 'normal'})
            except:
                pass
            page.get(f"https://{DOMAIN}")
        except Exception as e:
            log(tab_id, f"Lỗi khởi tạo Chrome: {e}. Thử lại sau 3s...")
            time.sleep(3)
            continue
            
        log(tab_id, "Trình duyệt sẵn sàng, bắt đầu lấy token...")

        refresh_count = 0
        while refresh_count < 15:
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
                    # Spam click vật lý tọa độ (78,115) - nút "I am human"
                    # Dùng CDP dispatchMouseEvent xuyên qua mọi element
                    try:
                        # Hiện dot đỏ tại vị trí click
                        page.run_js('''
                            if (!document.getElementById("click-dot")) {
                                var dot = document.createElement("div");
                                dot.id = "click-dot";
                                dot.style.cssText = "position:fixed;left:73px;top:110px;width:10px;height:10px;background:red;border-radius:50%;z-index:999999;pointer-events:none;box-shadow:0 0 6px red;";
                                document.body.appendChild(dot);
                            }
                        ''')
                    except:
                        pass
                    try:
                        # CDP raw mouse click tại (78,115)
                        page.run_cdp('Input.dispatchMouseEvent',
                                     type='mousePressed', x=78, y=115,
                                     button='left', clickCount=1)
                        page.run_cdp('Input.dispatchMouseEvent',
                                     type='mouseReleased', x=78, y=115,
                                     button='left', clickCount=1)
                    except:
                        pass

                if token:
                    push_token(token, tab_id)
                    with total_lock:
                        if total_collected >= TARGET:
                            log(tab_id, f"Đủ {TARGET} token, dừng tab này.")
                            with pages_lock:
                                if page in active_pages:
                                    active_pages.remove(page)
                            page.quit()
                            return
                else:
                    log(tab_id, "Timeout, refresh và thử lại...")

                # Refresh để reset cho lần tiếp theo
                page.refresh()
                refresh_count += 1
                time.sleep(1.5)

            except Exception as e:
                err_str = str(e)
                # Lỗi page bị refresh/crash → tắt mở lại Chrome luôn
                if '页面被刷新' in err_str or '页面已被销毁' in err_str:
                    log(tab_id, f"⚠️ Page lỗi, restart Chrome...")
                    break
                log(tab_id, f"Lỗi: {e}. Refresh trình duyệt lỗi...")
                time.sleep(2)
                try:
                    page.refresh()
                    refresh_count += 1
                except:
                    break   # Trình duyệt Crash, thoát vòng lặp nội bộ để khởi động lại Chrome

        log(tab_id, f"🔄 Đã refresh 15 lần đợt này. Đóng để xả RAM...")
        with pages_lock:
            if page in active_pages:
                active_pages.remove(page)
        try:
            page.quit()
        except:
            pass
        
        # BỎ XÓA PROFILE ĐỂ NUÔI TRUST (Lịch sử, Cookie giúp qua mặt Cloudflare)
        time.sleep(2)

if __name__ == "__main__":
    print(f"[*] KHỞI ĐỘNG {NUM_TABS} TAB SONG SONG - Đẩy token lên Supabase liên tục...")
    print(f"[*] Nhấn Ctrl+C để dừng bất cứ lúc nào.\n")

    # Xóa toàn bộ token cũ trước khi bắt đầu
    try:
        res_clear = supabase.table("turnstile_tokens").delete().neq("token", "").execute()
        deleted = len(res_clear.data) if hasattr(res_clear, 'data') and res_clear.data else 0
        print(f"[🧹] Đã xóa {deleted} token cũ từ DB.\n")
    except Exception as e:
        print(f"[!] Lỗi xóa token cũ: {e}\n")

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
        print("\n[!] Nhận lệnh Ctrl+C, đang đóng các trình duyệt...")
        pass
    print(f"\n[*] Đã dừng. Tổng cộng đã nạp {total_collected} token lên Supabase.")
    with pages_lock:
        for p in active_pages:
            try:
                p.quit()
            except:
                pass
    os._exit(0)

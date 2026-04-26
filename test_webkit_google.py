import asyncio
import requests
import nodriver as uc
import nodriver.cdp.network as cdp_net

# ── Patch nodriver bug: Chrome 125+ bỏ 'sameParty' field ──
_orig_cookie_from_json = cdp_net.Cookie.from_json
def _patched_cookie_from_json(json_data):
    json_data.setdefault('sameParty', False)
    return _orig_cookie_from_json(json_data)
cdp_net.Cookie.from_json = staticmethod(_patched_cookie_from_json)

EMAIL    = "tranthihuyentrang2xyvylyfsylg@hadanu.us"
PASSWORD = "Phan9999"
CONNECT_URL = "https://baseapi.elle.vn/connect/google?callback=https%3A%2F%2Fevents.elle.vn%2Flogin%2Fcallback%3FreturnTo%3D%252Felle-beauty-awards-2026"

async def get_vote_sid_google(email: str, password: str) -> str | None:
    print("[1] Mở Chrome...")
    browser = await uc.start(headless=False)

    # ── Bước 1: Navigate → backend tự set strapi.sid + redirect Google ──
    print("[2] Navigate đến backend connect URL...")
    tab = await browser.get(CONNECT_URL)

    print("[3] Chờ Google OAuth page...")
    for _ in range(20):
        await tab.sleep(0.5)
        if 'accounts.google.com' in tab.url:
            break
    print(f"    URL: {tab.url[:80]}")

    # ── Bước 2: Nhập email ──
    print("[4] Chờ email field...")
    email_input = await tab.select('input[type="email"]', timeout=15)
    await tab.sleep(1)
    print(f"    Nhập email: {email}")
    await email_input.send_keys(email)
    await tab.sleep(0.5)
    next_btn = await tab.find("Next", best_match=True)
    await next_btn.click()

    # ── Bước 3: Chờ password page ──
    print("[5] Chờ password page...")
    for _ in range(30):
        await tab.sleep(0.5)
        if 'challenge' in tab.url or 'pwd' in tab.url:
            break
    await tab.sleep(1.5)
    print(f"    URL: {tab.url[:80]}")

    pass_input = await tab.select('input[type="password"]', timeout=15)
    print("    Nhập password...")
    await pass_input.send_keys(password)
    await tab.sleep(0.5)
    next_btn2 = await tab.find("Next", best_match=True)
    await next_btn2.click()

    # ── Bước 4: Xử lý consent + chờ redirect ──
    print("[6] Chờ redirect về events.elle.vn...")
    tos_clicked = False      # ToS chỉ click 1 lần
    consent_clicked = False   # Consent chỉ click 1 lần
    for i in range(60):       # Tăng timeout cho acc mới (có 2 bước xác nhận)
        await tab.sleep(0.5)
        url = tab.url
        if i % 4 == 0:
            print(f"    [{i//2}s] {url[:90]}")

        # Xử lý trang ToS của Google Workspace (account mới)
        if not tos_clicked and 'speedbump/gaplustos' in url:
            print("    [!] Google ToS page - click input#confirm...")
            try:
                # Dùng nodriver native click (không phải JS) để trigger Google jsaction
                confirm_btn = await tab.select('input#confirm', timeout=5)
                if confirm_btn:
                    await confirm_btn.click()
                    tos_clicked = True
                    await tab.sleep(3)
            except Exception as e:
                print(f"    ToS click error: {e}")
            continue

        # OAuth consent screen → chỉ click 1 lần (xuất hiện SAU ToS)
        if not consent_clicked and 'accounts.google.com' in url and 'challenge' not in url and 'identifier' not in url and 'speedbump' not in url:
            try:
                # Tìm nút Continue bằng text TRƯỚC để tránh click Cancel
                btn = await tab.find("Continue", best_match=True)
                if btn:
                    print("    [!] Click Continue (consent)...")
                    await btn.click()
                    consent_clicked = True
                    await tab.sleep(2)
            except:
                pass

        if 'events.elle.vn' in url and 'error' not in url:
            print(f"    ✅ Đã về elle.vn! Lấy vote_sid...")
            try:
                all_cookies = await browser.cookies.get_all()
                vote_sid = next((c.value for c in all_cookies if c.name == 'vote_sid'), None)
                if vote_sid:
                    print(f"\n✅ THÀNH CÔNG! vote_sid: {vote_sid}")
                else:
                    print(f"\n❌ Không thấy vote_sid trong cookies")
            except Exception as e:
                print(f"    Lỗi CDP: {e}")
                vote_sid = None
            browser.stop()
            return vote_sid

        if 'error=Grant' in url or 'misconfigured' in url:
            print(f"    ❌ Session error: {url}")
            break

    browser.stop()
    return None

if __name__ == "__main__":
    asyncio.run(get_vote_sid_google(EMAIL, PASSWORD))

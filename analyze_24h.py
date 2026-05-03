"""
analyze_24h.py — Xem nhanh bao nhiêu tài khoản sẵn sàng vote
Hiển thị: hiện tại, +1h, +2h, +3h, ... +24h
"""
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client

sys.stdout.reconfigure(encoding='utf-8')

SUPABASE_URL = 'https://lzwxjlpmjfudlwesvsjp.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo'
VN_TZ = timezone(timedelta(hours=7))
COOLDOWN = timedelta(hours=24)

# ── Lấy dữ liệu ──
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
all_rows = []
offset = 0
while True:
    res = sb.table('accounts').select('last_time_vote') \
           .not_.is_('cookie_sid', 'null') \
           .order('last_time_vote') \
           .range(offset, offset + 999).execute()
    rows = res.data or []
    all_rows.extend(rows)
    if len(rows) < 1000:
        break
    offset += 1000

now_utc = datetime.now(timezone.utc)
now_vn = now_utc.astimezone(VN_TZ)
total = len(all_rows)

# ── Tính unlock time cho mỗi account ──
unlock_times = []
never_voted = 0

for acc in all_rows:
    raw = acc.get('last_time_vote')
    if not raw:
        never_voted += 1
        continue
    last = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    unlock_utc = last + COOLDOWN
    unlock_times.append(unlock_utc)

# Sort để dùng binary search
unlock_times.sort()

# ── Đếm sẵn sàng tại mỗi mốc thời gian ──
def count_ready_at(target_utc):
    """Đếm số account sẵn sàng tại thời điểm target_utc."""
    # Tất cả account chưa vote + account có unlock <= target
    count = never_voted
    # Binary search: tìm số unlock_time <= target_utc
    lo, hi = 0, len(unlock_times)
    while lo < hi:
        mid = (lo + hi) // 2
        if unlock_times[mid] <= target_utc:
            lo = mid + 1
        else:
            hi = mid
    count += lo
    return count

# ── Hiển thị ──
print()
print("=" * 62)
print(f"  📊 PHÂN TÍCH TÀI KHOẢN SẴN SÀNG VOTE")
print(f"  🕐 Hiện tại: {now_vn.strftime('%H:%M %d/%m/%Y')} (VN)")
print(f"  📦 Tổng TK có SID: {total:,}")
print("=" * 62)
print()

ready_now = count_ready_at(now_utc)

# Tìm max để scale biểu đồ
max_ready = count_ready_at(now_utc + timedelta(hours=24))
bar_max = 30

rows = []
for h in range(25):  # 0h (now) → 24h
    target = now_utc + timedelta(hours=h)
    target_vn = target.astimezone(VN_TZ)
    ready = count_ready_at(target)
    rows.append((h, target_vn, ready))

# Header
print(f"  {'Thời điểm':<22} {'Sẵn sàng':>10}  {'Thêm':>8}  Biểu đồ")
print("  " + "─" * 58)

prev = 0
for h, t_vn, ready in rows:
    delta = ready - prev
    bar_len = int((ready / max_ready) * bar_max) if max_ready > 0 else 0
    bar = "█" * bar_len

    if h == 0:
        label = f"⏰ Ngay bây giờ"
        delta_str = ""
    else:
        label = f"   +{h:>2}h → {t_vn.strftime('%H:%M %d/%m')}"
        delta_str = f"+{delta:,}" if delta > 0 else "—"

    print(f"  {label:<22} {ready:>8,} TK  {delta_str:>8}  {bar}")
    prev = ready

print()
print("  " + "─" * 58)
print(f"  🟢 Ngay bây giờ  : {ready_now:,} TK sẵn sàng")
print(f"  🔵 Sau 6h        : {count_ready_at(now_utc + timedelta(hours=6)):,} TK")
print(f"  🟡 Sau 12h       : {count_ready_at(now_utc + timedelta(hours=12)):,} TK")
print(f"  🔴 Sau 24h       : {max_ready:,} TK")
print("=" * 62)
print()

import os, datetime
from supabase import create_client

url = "https://lzwxjlpmjfudlwesvsjp.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo"
sb = create_client(url, key)
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

all_rows = []
offset = 0
while True:
    res = sb.table("accounts").select("email,last_time_vote").not_.is_("cookie_sid","null").range(offset, offset+999).execute()
    if not res.data: break
    all_rows.extend(res.data)
    if len(res.data) < 1000: break
    offset += 1000

now_utc = datetime.datetime.now(datetime.timezone.utc)

timed = []
for row in all_rows:
    lt = row.get("last_time_vote")
    if not lt: continue
    lt = lt.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(lt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    elapsed_h = (now_utc - dt).total_seconds() / 3600
    ready_at = dt + datetime.timedelta(hours=24)
    ready_at_vn = ready_at.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    timed.append((dt, row["email"], elapsed_h, ready_at_vn))

timed.sort(key=lambda x: x[0])

print(f"{'#':<4} {'Email':<42} {'Vote lúc (VN)':<16} {'Đủ điều kiện lúc':<18} Còn lại")
print("-"*105)
for i, (dt, email, elapsed, ready_at_vn) in enumerate(timed[:30], 1):
    dt_vn = dt.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    remain = 24 - elapsed
    status = "✅ SẴN SÀNG!" if remain <= 0 else f"⏳ {remain:.1f}h nữa"
    print(f"{i:<4} {email[:42]:<42} {dt_vn:<16} {ready_at_vn:<18} {status}")

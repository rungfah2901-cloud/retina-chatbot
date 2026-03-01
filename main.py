# --- แก้ไขส่วนเชื่อมต่อ Sheet ให้กลับมาใช้ภาษาอังกฤษที่เสถียรกว่าค่ะ ---
try:
    if google_json_str:
        service_account_info = json.loads(google_json_str)
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        client = gspread.authorize(creds)
        # ใช้รหัสไฟล์เดิมของคุณพยาบาล และระบุเป็น .sheet1 (ซึ่งก็คือแผ่นงานแรก)
        sheet = client.open_by_key("1joOjhQSn4sGtRkF9-_9dwwEvmtC1On24JEyrJHK6mXs").sheet1
except Exception as e:
    print(f"❌ เชื่อมต่อ Sheets ไม่สำเร็จเพราะ: {e}") # ตัวนี้จะไปโชว์ใน Logs ของ Render ค่ะ
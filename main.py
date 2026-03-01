import os
import json
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    PostbackEvent, TemplateSendMessage, ButtonsTemplate, 
    DatetimePickerAction
)
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# 1. โหลดการตั้งค่า
load_dotenv()

app = FastAPI()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 2. ตั้งค่าการเชื่อมต่อ Google Sheets
# ตรวจสอบ ID: 1joOjhQSn4sGtRkF9-_9dwwEvmtC1On24JEyrJHK6mXs
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    google_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if google_json_str:
        service_account_info = json.loads(google_json_str)
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        client = gspread.authorize(creds)
        # เชื่อมต่อกับ Sheet1 (ต้องเปลี่ยนชื่อใน Google Sheets เป็น Sheet1 ด้วยนะคะ)
        sheet = client.open_by_key("1joOjhQSn4sGtRkF9-_9dwwEvmtC1On24JEyrJHK6mXs").sheet1
except Exception as e:
    print(f"Error connecting to Google Sheets: {e}")

# 3. ข้อมูลคำถามที่พบบ่อย (FAQ)
faq = {
    "ฉีดยา": "การฉีดยาเข้าน้ำวุ้นตา ใช้เวลาประมาณ 30-60 นาทีค่ะ ไม่เจ็บมากเพราะมีการหยอดยาชาก่อนค่ะ",
    "เตรียมตัว": "ก่อนฉีดยา: อาบน้ำสระผมให้เรียบร้อย ไม่แต่งหน้า ไม่ใส่คอนแทคเลนส์ และพาญาติมาด้วยได้ค่ะ",
    "หลังฉีด": "หลังฉีดยา ตาอาจแดงเล็กน้อยเป็นเรื่องปกติค่ะ ถ้ามีอาการปวดตามาก ตามัวลงฉับพลัน ให้รีบมาพบแพทย์ทันทีค่ะ",
    "นัด": "ถ้าต้องการเลื่อนนัด กรุณาติดต่อ OPD ตา โทร 055-022-000 ต่อ 2501 ในวันทำการค่ะ",
}

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    try:
        handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

# 4. ส่วนรับข้อความ (จดชื่อ และ แสดงปุ่มนัด)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    # เมื่อกดปุ่ม "ลงนัดฉีดยา"
    if "ลงนัด" in user_message:
        buttons_template = ButtonsTemplate(
            title="ลงทะเบียนวันนัดหมาย",
            text="กรุณาเลือกรายการนัดที่ต้องการค่ะ",
            actions=[
                DatetimePickerAction(label="เข็มที่ 1", data="action=set_nood&no=1", mode="date"),
                DatetimePickerAction(label="เข็มที่ 2", data="action=set_nood&no=2", mode="date"),
                DatetimePickerAction(label="เข็มที่ 3", data="action=set_nood&no=3", mode="date"),
                DatetimePickerAction(label="ติดตามอาการ", data="action=set_nood&no=4", mode="date"),
            ]
        )
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text="เลือกนัดหมาย", template=buttons_template))
        return

    # ตอบ FAQ
    for key, value in faq.items():
        if key in user_message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=value))
            return

    # จดชื่อ-นามสกุล (ต้องมีเว้นวรรค)
    if " " in user_message and len(user_message) > 5:
        try:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            sheet.append_row([now, user_id, user_message])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พยาบาลจดชื่อ 'คุณ {user_message}' เรียบร้อยแล้วค่ะ 😊"))
        except Exception as e:
            print(f"Error logging name: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยค่ะ ระบบจดชื่อขัดข้องชั่วคราว"))

# 5. ส่วนรับค่าจากปฏิทิน (จดวันนัด + เตือนความปลอดภัย)
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    selected_date = event.postback.params.get('date')
    data = event.postback.data
    
    if "action=set_nood" in data:
        nood_no = data.split("no=")[1]
        col_map = {"1": 4, "2": 5, "3": 6, "4": 7}
        col_num = col_map.get(nood_no)

        try:
            cell = sheet.find(user_id, in_column=2)
            if cell:
                sheet.update_cell(cell.row, col_num, selected_date)
                
                safety_msg = (
                    f"✅ บันทึกนัดเข็มที่ {nood_no} เรียบร้อยค่ะ วันที่ {selected_date}\n\n"
                    f"⚠️ สำคัญมาก:\n"
                    f"ห้ามขับรถมาเองในวันนัดนะคะ เนื่องจากต้องปิดตาข้างที่ฉีดยา "
                    f"และบางรายอาจต้องขยายม่านตา จะทำให้ตามัวชั่วคราวค่ะ"
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=safety_msg))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ ไม่พบชื่อในระบบ รบกวนแจ้งชื่อ-นามสกุลก่อนนะคะ"))
        except Exception as e:
            print(f"Error updating appointment: {e}")
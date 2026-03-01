from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    PostbackEvent, TemplateSendMessage, ButtonsTemplate, 
    DatetimePickerAction
)
from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# 1. โหลดค่าคอนฟิกต่างๆ
load_dotenv()

app = FastAPI()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 2. เชื่อมต่อ Google Sheets
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
google_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

try:
    if google_json_str:
        service_account_info = json.loads(google_json_str)
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        client = gspread.authorize(creds)
        # ใช้ ID ไฟล์ของคุณพยาบาล
        # แก้ไขจาก .sheet1 เป็นการระบุชื่อแผ่นงานภาษาไทย "ชีต1" ค่ะ
        sheet = client.open_by_key("1joOjhQSn4sGtRkF9-_9dwwEvmtC1On24JEyrJHK6mXs").worksheet("ชีต1")
except Exception as e:
    print(f"❌ เชื่อมต่อ Sheets ไม่สำเร็จ: {e}")

# 3. คลังคำตอบ FAQ
faq = {
    "ฉีดยา": "การฉีดยาเข้าน้ำวุ้นตา ใช้เวลาประมาณ 30-60 นาทีค่ะ ไม่เจ็บมากเพราะมีการหยอดยาชาก่อนค่ะ",
    "เตรียมตัว": "ก่อนฉีดยา: อาบน้ำสระผมให้เรียบร้อย ไม่แต่งหน้า ไม่ใส่คอนแทคเลนส์ และพาญาติมาด้วยได้ค่ะ",
    "หลังฉีด": "หลังฉีดยา ตาอาจแดงเล็กน้อยเป็นเรื่องปกติค่ะ ถ้ามีอาการปวดตามาก ตามัวลงฉับพลัน ให้รีบมาพบแพทย์ทันทีค่ะ",
    "นัด": "ถ้าต้องการเลื่อนนัด กรุณาติดต่อ OPD ตา โทร 055-022-000 ต่อ 2501 ในวันทำการค่ะ",
}

@app.get("/")
def home():
    return {"message": "Retina Chatbot is Ready!"}

@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    try:
        handler.handle(body.decode(), signature)
    except Exception:
        raise HTTPException(status_code=400)
    return "OK"

# 4. ส่วนจัดการข้อความ (จดชื่อ และ แสดงปุ่มนัด)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    # ถ้ากดปุ่ม "ลงนัดฉีดยา" จาก Rich Menu
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

    # ตอบคำถามทั่วไป
    for key in faq:
        if key in user_message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=faq[key]))
            return

    # ถ้าพิมพ์ ชื่อ นามสกุล (มีเว้นวรรค) ให้จดลง Sheets
    if " " in user_message and len(user_message) > 5:
        try:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            sheet.append_row([now, user_id, user_message])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พยาบาลจดชื่อ 'คุณ {user_message}' เรียบร้อยแล้วค่ะ 😊"))
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยค่ะ ระบบจดชื่อขัดข้องชั่วคราว"))

# 5. ส่วนจัดการเมื่อเลือกวันที่จากปฏิทิน (Postback)
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    selected_date = event.postback.params.get('date') # วันที่จากปฏิทิน
    data = event.postback.data # ข้อมูลว่านัดที่เท่าไหร่
    
    if "action=set_nood" in data:
        nood_no = data.split("no=")[1]
        col_map = {"1": 4, "2": 5, "3": 6, "4": 7} # คอลัมน์ D, E, F, G
        col_num = col_map[nood_no]

        try:
            # ค้นหาคนไข้จาก LINE ID
            cell = sheet.find(user_id, in_column=2)
            if cell:
                # อัปเดตวันที่ลงช่องนัด
                sheet.update_cell(cell.row, col_num, selected_date)
                
                # แจ้งเตือนความปลอดภัยที่คุณพยาบาลเน้นย้ำ
                safety_msg = (
                    f"✅ บันทึกนัดเรียบร้อยค่ะ วันที่ {selected_date}\n\n"
                    f"⚠️ สำคัญมาก:\n"
                    f"ห้ามขับรถมาเองในวันนัดนะคะ เนื่องจากต้องปิดตาข้างที่ฉีดยา "
                    f"และบางรายอาจต้องขยายม่านตา จะทำให้ตามัวชั่วคราวค่ะ"
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=safety_msg))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ ไม่พบชื่อในระบบ รบกวนแจ้งชื่อ-นามสกุลเพื่อลงทะเบียนก่อนนะคะ"))
        except Exception as e:
            print(f"Error: {e}")
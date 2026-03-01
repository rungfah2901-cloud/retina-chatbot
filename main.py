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

# ประกาศตัวแปร sheet ไว้ด้านนอกเพื่อให้ทุกส่วนรู้จักชื่อนี้
sheet = None 

# 2. ตั้งค่าการเชื่อมต่อ Google Sheets
def connect_sheets():
    global sheet
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        google_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if google_json_str:
            service_account_info = json.loads(google_json_str)
            creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
            client = gspread.authorize(creds)
            # เชื่อมต่อกับ Sheet1 (ตรวจสอบรหัส ID ให้ถูกต้องนะคะ)
            sheet = client.open_by_key("1joOjhQSn4sGtRKF9-_9dwwEvmtC1On24JEyrJHK6mXs").sheet1
            print("✅ Connected to Google Sheets successfully!")
    except Exception as e:
        print(f"❌ Error connecting to Google Sheets: {e}")

connect_sheets()

# 3. คลังคำตอบ FAQ (อัปเดตตามข้อมูลล่าสุดของคุณพยาบาล)
faq = {
    "ฉีดยา": "การฉีดยาเข้าน้ำวุ้นตา ใช้เวลาประมาณ 30-60 นาทีค่ะ ไม่เจ็บมากเพราะมีการหยอดยาชาก่อนค่ะ",
    "เตรียมตัว": "ก่อนฉีดยา: อาบน้ำสระผมให้เรียบร้อย ไม่แต่งหน้า ไม่ใส่คอนแทคเลนส์ และพาญาติมาด้วยได้ค่ะ",
    "หลังฉีด": "หลังฉีดยา ตาอาจแดงเล็กน้อยเป็นเรื่องปกติค่ะ ถ้ามีอาการปวดตามาก ตามัวลงฉับพลัน หรือตาแดงมาก ให้รีบมาพบแพทย์ทันทีค่ะ",
    "นัด": "ถ้าต้องการเลื่อนนัดหรือสอบถามนัดหมาย กรุณาติดต่อ OPD ตา โทร 055-022-000 ต่อ 2501 ในวันทำการ ช่วงเวลา 14.00-16.00 น. ค่ะ",
    "จอตาเสื่อม": "โรคจอตาเสื่อมในผู้สูงอายุชนิดเปียก (Wet AMD) รักษาหลักด้วยการฉีดยาต้านสารสร้างหลอดเลือด (anti-VEGF) เข้าน้ำวุ้นตา เพื่อยับยั้งการรั่วซึมของหลอดเลือดใต้จอตา ช่วยชะลอโรคและป้องกันตาบอดถาวร โดยต้องฉีดต่อเนื่องทุกเดือนในช่วงแรก และปรับความถี่ตามอาการ",
    "เบาหวาน": "โรคเบาหวานขึ้นจอตาที่ต้องฉีดยาเข้าน้ำวุ้นตา (Intravitreal Injection) คือภาวะเบาหวานระยะรุนแรงที่ทำให้มีจุดภาพชัดบวม (DME) หรือมีเส้นเลือดงอกผิดปกติและเลือดออกในวุ้นตา โดยใช้ยาต้านการเจริญเติบโตของเส้นเลือด (Anti-VEGF) ฉีดเข้าตาโดยตรงเพื่อลดบวม หยุดเลือด และฟื้นฟูการมองเห็น เป็นการรักษาที่ปลอดภัยและได้ผลดี ควรคุมน้ำตาลให้ได้ HbA1c < 7% ค่ะ",
    "ฉุกเฉิน": "อาการที่ต้องมา ER ทันที: ตามัวลงฉับพลัน ปวดตามาก ตาแดงมากผิดปกติ มีหนองตา เห็นแสงวาบ หรือเห็นม่านดำค่ะ",
}

@app.get("/")
async def root():
    return {"status": "ok", "sheets_connected": sheet is not None}

@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    try:
        handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400)
    return "OK"

# 4. ส่วนจัดการข้อความ (จดชื่อ และ แสดงปุ่มนัด)
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

    # จดชื่อ-นามสกุล
    if " " in user_message and len(user_message) > 5:
        if sheet:
            try:
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                sheet.append_row([now, user_id, user_message])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พยาบาลจดชื่อ 'คุณ {user_message}' เรียบร้อยแล้วค่ะ 😊"))
            except Exception as e:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ขออภัยค่ะ ระบบจดชื่อขัดข้องชั่วคราว"))

# 5. ส่วนรับค่าจากปฏิทิน (จดวันนัด + เตือนความปลอดภัยที่เน้นย้ำ)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    # 1. เช็คปุ่มนัด
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

    # 2. เช็ค FAQ
    for key, value in faq.items():
        if key in user_message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=value))
            return

    # 3. ส่วนจดชื่อ (ปรับปรุงใหม่ให้บอทไม่เงียบ)
    if " " in user_message:
        if sheet is None:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ บอทหาไฟล์สมุดจดไม่เจอค่ะ เช็คการแชร์สิทธิ์หรือ ID ไฟล์นะคะ"))
        else:
            try:
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                sheet.append_row([now, user_id, user_message])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พยาบาลจดชื่อ 'คุณ {user_message}' เรียบร้อยแล้วค่ะ 😊"))
            except Exception as e:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ จดชื่อไม่สำเร็จเพราะ: {str(e)}"))
    else:
        # ถ้าพิมพ์มาแล้วไม่มีเว้นวรรค ให้บอททักท้วงแทนที่จะเงียบค่ะ
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="พยาบาลได้รับข้อความแล้วค่ะ แต่ถ้าจะลงทะเบียนชื่อ รบกวนพิมพ์ 'ชื่อ นามสกุล' แบบมีเว้นวรรคตรงกลางด้วยนะคะ")
        )
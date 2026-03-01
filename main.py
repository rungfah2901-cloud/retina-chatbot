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

load_dotenv()
app = FastAPI()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
sheet = None 

def connect_sheets():
    global sheet
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        google_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if google_json_str:
            service_account_info = json.loads(google_json_str)
            creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
            client = gspread.authorize(creds)
            # ⚠️ ตรวจสอบ ID ไฟล์ของคุณพยาบาลในเครื่องหมายคำพูดด้านล่างนี้ให้ถูกต้องนะคะ
            sheet = client.open_by_key("1joOjhQSn4sGtRKF9-_9dwwEvmtC1On24JEyrJHK6mXs").sheet1
            print("✅ Connected to Google Sheets!")
    except Exception as e:
        print(f"❌ Error: {e}")

connect_sheets()

faq = {
    "ฉีดยา": "การฉีดยาเข้าน้ำวุ้นตา ใช้เวลาประมาณ 30-60 นาทีค่ะ ไม่เจ็บมากเพราะมีการหยอดยาชาก่อนค่ะ",
    "เตรียมตัว": "ก่อนฉีดยา: อาบน้ำสระผมให้เรียบร้อย ไม่แต่งหน้า ไม่ใส่คอนแทคเลนส์ และพาญาติมาด้วยได้ค่ะ",
    "หลังฉีด": "หลังฉีดยา ตาอาจแดงเล็กน้อยเป็นเรื่องปกติค่ะ ถ้ามีอาการปวดตามาก ตามัวลงฉับพลัน หรือตาแดงมาก ให้รีบมาพบแพทย์ทันทีค่ะ",
    "นัด": "ถ้าต้องการเลื่อนนัดหมาย กรุณาติดต่อ OPD ตา โทร 055-022-000 ต่อ 2501 ในวันทำการค่ะ",
    "จอตาเสื่อม": "โรคจอตาเสื่อมชนิดเปียก รักษาด้วยการฉีดยา Anti-VEGF เพื่อชะลอโรคและป้องกันตาบอดถาวรค่ะ",
    "เบาหวาน": "เบาหวานขึ้นจอตาที่มีจุดภาพชัดบวม (DME) รักษาโดยการฉีดยาเข้าตาเพื่อลดบวมและฟื้นฟูการมองเห็นค่ะ",
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

# 4. ส่วนจัดการข้อความ (FAQ + ลงนัด + จดชื่อ + PDPA)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    # --- ส่วนที่ 1: ลงนัด ---
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

    # --- ส่วนที่ 2: ระบบลบข้อมูล PDPA ---
    if user_message == "ยกเลิกการลงทะเบียน" or user_message == "ลบข้อมูล":
        if sheet:
            try:
                cell = sheet.find(user_id, in_column=2)
                if cell:
                    sheet.delete_rows(cell.row)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ พยาบาลได้ลบข้อมูลชื่อและวันนัดของท่านออกจากระบบเรียบร้อยแล้วค่ะ ตามนโยบายคุ้มครองข้อมูลส่วนบุคคล (PDPA)"))
                else:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ ไม่พบข้อมูลของท่านในระบบค่ะ"))
            except:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ เกิดข้อผิดพลาดในการลบข้อมูล"))
        return

    # --- ส่วนที่ 3: FAQ ---
    for key, value in faq.items():
        if key in user_message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=value))
            return

    # --- ส่วนที่ 4: จดชื่อ-นามสกุล ---
    if " " in user_message:
        if sheet:
            try:
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                sheet.append_row([now, user_id, user_message])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พยาบาลจดชื่อ 'คุณ {user_message}' เรียบร้อยแล้วค่ะ 😊"))
            except:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ระบบจดชื่อขัดข้อง"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ บอทหาไฟล์สมุดจดไม่เจอ"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="หากต้องการลงทะเบียนนัดหมาย กรุณาพิมพ์ 'ชื่อ นามสกุล' แบบมีเว้นวรรคด้วยนะคะ (ข้อมูลของท่านจะถูกเก็บเป็นความลับเพื่อการรักษาเท่านั้นค่ะ)"))

# 5. ส่วนรับค่าจากปฏิทิน (แยกคำเตือนฉีดยา vs ขยายม่านตา)
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    selected_date = event.postback.params.get('date')
    data = event.postback.data
    
    if "action=set_nood" in data and sheet:
        nood_no = data.split("no=")[1]
        col_map = {"1": 4, "2": 5, "3": 6, "4": 7}
        col_num = col_map.get(nood_no)

        try:
            cell = sheet.find(user_id, in_column=2)
            if cell:
                sheet.update_cell(cell.row, col_num, selected_date)
                
                # แยกข้อความตามประเภทการนัด (ตามที่คุณพยาบาลระบุ)
                if nood_no == "4":
                    appointment_name = "ติดตามอาการ"
                    warning_detail = "เนื่องจากต้องขยายม่านตาเพื่อทำการตรวจรักษา จะทำให้ตามัวชั่วคราว 4-6 ชั่วโมงค่ะ"
                else:
                    appointment_name = f"เข็มที่ {nood_no}"
                    warning_detail = "เนื่องจากต้องปิดตาข้างที่ฉีดยา และบางรายอาจต้องขยายม่านตา จะทำให้ตามัวชั่วคราวค่ะ"

                safety_msg = (
                    f"✅ บันทึกนัด {appointment_name} เรียบร้อยค่ะ วันที่ {selected_date}\n\n"
                    f"⚠️ สำคัญมาก:\n"
                    f"ห้ามขับรถมาเองในวันนัดนะคะ {warning_detail}"
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=safety_msg))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ ไม่พบชื่อในระบบ รบกวนพิมพ์ 'ชื่อ นามสกุล' ก่อนนะคะ"))
        except Exception as e:
            print(f"Error: {e}")
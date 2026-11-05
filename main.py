import os
import sys
import tempfile
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.utils import get_display_name
from groq import Groq

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
GROQ_KEY = os.getenv("GROQ_KEY", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
OUTPUT = os.getenv("OUTPUT", "chat")
MAX_SECONDS = int(os.getenv("MAX_SECONDS", "600"))

groq = Groq(api_key=GROQ_KEY)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Sozlamalar:
current_status = "RestoFlow loyihasi va yangi AI integratsiyalari ustida ishlayapman."
voice_enabled = False  # Odatiy holatda o'chiq


def ovozni_matnga(path):
    with open(path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=("audio.ogg", f.read()),
            model="whisper-large-v3",
        )
    return r.text.strip()


def ai_javob(savol: str, sender_name: str, sender_username: str, sender_id: int) -> str:
    global current_status
    
    # Maxsus shaxs eslatmasi (Hadichaxon)
    special_rule = ""
    if (sender_username and sender_username.lower() == "soim_h") or sender_id == 7795903945:
        special_rule = "JUDA MUHIM: Bu qizning ismi Hadichaxon. Unga hurmat va samimiyat bilan faqat 'Hadichaxon' deb murojaat qil. Hech qanday boshqa nik yoki taxallus ishlatma!"

    system_prompt = f"""Sen Diego (Zulfiqor)ning shaxsiy sun'iy intellekt yordamchisisan (Diego AI).
Sen juda aqlli, ziyrak, zamonaviy va jonli gapiradigan shaxssan.

DIEGO HAQIDA:
- Ismi: Zulfiqor (Telegram: @Diego_Davinchi, Nickname: Diego)
- Hozirgi bandligi / statusi: {current_status}

{special_rule}

MUHIM QOIDALAR:
1. O'zbek tilidagi so'zlashuvni nozik tushun:
   - "Qanday aisan?" yoki "qanaqa aisan?" bu "qanday sun'iy intellektsan / vazifang nima?" degani ("qandaysan" bilan adashtirma!).
   - Javob: "Men Diegoning shaxsiy AI yordamchisiman 🤖. U band bo'lganida savollarga javob berib turaman." deb tushuntir.
2. Qisqa, lo'nda va tabiiy javob ber (1-3 gap). Kitobiy qotib qolgan tilda emas, jonli odamdek gapir.
3. Suhbatdoshning Telegramdagi nikini robotdek qaytarma.
4. Agar "Diego qayerda?", "nima qilyapti?" deb so'ralsa, uning hozirgi statusiga qarab javob ber.
5. Agar "Diegoni chaqir", "shoshilinch" desa, "Xo'p, hozir uning o'ziga signal yuboraman!" deb ayt.
"""

    try:
        resp = groq.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": savol},
            ],
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("❌ AI xatolik:", e)
        return "Kechirasiz, hozir serverda nosozlik bo'ldi. Birozdan so'ng qayta yozing."


# 1. "Избранное" (Saqlangan xabarlar) chatidan kelgan har qanday buyruqni tutish
@client.on(events.NewMessage(chats="me"))
async def me_commands_handler(event):
    global current_status, voice_enabled
    m = event.message
    if not m.text:
        return

    cmd = m.text.strip().lower()
    if cmd == "/voice on":
        voice_enabled = True
        await m.reply("🎙 **Goloslarni matnga o'girish YOQILDI!**\nEndi kelgan ovozli xabarlar avtomatik matnga aylanadi.")
        print("⚙️ Goloslar YOQILDI")
    elif cmd == "/voice off":
        voice_enabled = False
        await m.reply("⏸ **Goloslarni matnga o'girish O'CHIRILDI!**\nOvozli xabarlar avtomatik o'girilmaydi.")
        print("⚙️ Goloslar O'CHIRILDI")
    elif cmd.startswith("/status"):
        new_status = m.text.replace("/status", "").strip()
        if new_status:
            current_status = new_status
            await m.reply(f"✅ **Status yangilandi:**\n_{current_status}_")
        else:
            v_state = "YOQILGAN" if voice_enabled else "O'CHIRILGAN"
            await m.reply(f"📍 **Hozirgi status:**\n_{current_status}_\n🎙 Goloslar: **{v_state}**\n\nBoshqarish:\n• `/voice on` yoki `/voice off`\n• `/status [yangi status]`")


# 2. Boshqa foydalanuvchilardan kelgan xabarlarga javob berish
@client.on(events.NewMessage(incoming=True))
async def incoming_handler(event):
    global current_status, voice_enabled
    m = event.message
    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return

    me = await client.get_me()
    if sender and sender.id == me.id:
        return

    sender_name = get_display_name(sender) if sender else "Do'stim"
    sender_username = getattr(sender, "username", "") or ""
    sender_id = getattr(sender, "id", 0)

    # A. @diegohelp orqali murojaat
    if m.text and "@diegohelp" in m.text.lower():
        text_clean = m.text.replace("@diegohelp", "").replace("@Diegohelp", "").strip()
        print(f"📩 @diegohelp chaqirildi ({sender_name}): {text_clean}")
        
        # Agar biror golosga reply qilib @diegohelp deb yozilgan bo'lsa
        if m.is_reply:
            reply_msg = await m.get_reply_message()
            if reply_msg and (reply_msg.voice or reply_msg.video_note):
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        path = await reply_msg.download_media(file=os.path.join(tmp, "a.ogg"))
                        matn = await asyncio.to_thread(ovozni_matnga, path)
                    await m.reply(f"🎙 **Ovozli xabar matni:**\n\n_{matn}_")
                    return
                except Exception as e:
                    print("❌ Reply golos xato:", e)

        if not text_clean:
            await m.reply("🤖 **Diego AI:** Salom! Men Diegoning shaxsiy yordamchisiman. Sizga qanday yordam bera olaman?")
            return

        javob = await asyncio.to_thread(ai_javob, text_clean, sender_name, sender_username, sender_id)
        await m.reply(f"🤖 **Diego AI:**\n\n{javob}")

        # Shoshilinch chaqiriq bo'lsa, Diegoning "Избранное"siga xabar berish
        urgent_keywords = ["chaqir", "shoshilinch", "срочно", "позови", "urgent", "call"]
        if any(w in text_clean.lower() for w in urgent_keywords):
            chat_title = event.chat.title if event.is_group else sender_name
            notify_text = (
                f"🚨 **SHOSHILINCH BILDIRISHNOMA!**\n\n"
                f"👤 **Kimdan:** {sender_name} (@{sender_username})\n"
                f"💬 **Qayerda:** {chat_title}\n"
                f"📝 **Xabar:** {text_clean}"
            )
            await client.send_message("me", notify_text)
        return

    # B. Golos va dumaloq video (krujok) - faqat voice_enabled=True bo'lganda
    if (m.voice or m.video_note) and event.is_private and voice_enabled:
        dur = int(getattr(m.file, "duration", 0) or 0)
        if dur > MAX_SECONDS:
            return

        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = await m.download_media(file=os.path.join(tmp, "a.ogg"))
                matn = await asyncio.to_thread(ovozni_matnga, path)
        except Exception as e:
            print("❌ Golos xato:", e)
            return

        if not matn:
            return

        my_name = (getattr(me, "first_name", "") or "Diego").strip()
        if OUTPUT == "chat":
            await m.reply(f"__🤖 ai msg — transcribed for {my_name}__\n\n{matn}")
        else:
            await client.send_message("me", f"🎙 **{sender_name}** · {dur}s\n\n{matn}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Telethon bot (Render 24/7) ishga tushmoqda...")
    await client.start()
    print("Telethon bot muvaffaqiyatli ulandi!")
    yield
    print("Telethon bot to'xtatilmoqda...")
    await client.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def home():
    return {"status": "ok", "message": "Diego AI 24/7 ishlab turibdi"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

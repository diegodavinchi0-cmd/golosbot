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

# Serverdagi dinamik xotira (status)
current_status = "RestoFlow loyihasi va yangi AI integratsiyalari ustida ishlayapman."


def ovozni_matnga(path):
    with open(path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=("audio.ogg", f.read()),
            model="whisper-large-v3",
        )
    return r.text.strip()


def ai_javob(savol: str, sender_name: str, is_me: bool) -> str:
    global current_status
    system_prompt = (
        "Sen Diego'ning (Zulfiqor) shaxsiy sun'iy intellekt yordamchisisan (Diego AI).\n"
        f"DIEGO'NING HOZIRGI STATUSI: {current_status}\n\n"
        "QOIDALAR:\n"
        "1. Foydalanuvchi qaysi tilda yozsa, o'sha tilda qisqa, aniq va juda xushmuomala javob ber.\n"
        "2. Agar 'Diego nima qilyapti?', 'qayerda?' kabi savollar berilsa, yuqoridagi 'Hozirgi Status' asosida javob ber.\n"
        "3. Agar 'Diegoni chaqir', 'shoshilinch' desa: 'Xo'p, Diegoga hozir bildirishnoma yubordim!' deb ayt.\n"
        f"4. Suhbatdosh ismi: {sender_name}.\n"
    )
    if is_me:
        system_prompt += "Hozir senga yozayotgan odam — Diego (Zulfiqor)ning o'zi! Unga xo'jayindek samimiy muomala qil."
    else:
        system_prompt += "Hozir senga boshqa odam yozmoqda. Diego nomidan madaniyatli javob ber."

    try:
        resp = groq.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": savol},
            ],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("❌ AI xatolik:", e)
        return "Kechirasiz, hozir serverda nosozlik bo'ldi. Birozdan so'ng qayta yozing."


@client.on(events.NewMessage(incoming=True))
async def message_handler(event):
    global current_status
    m = event.message
    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return

    me = await client.get_me()
    sender_name = get_display_name(sender) if sender else "Do'stim"
    is_me = (sender and sender.id == me.id)

    # 0. Diego o'zining "Saqlangan xabarlar"idan statusni yangilashi mumkin (/status ...)
    if is_me and m.text and m.text.startswith("/status"):
        new_status = m.text.replace("/status", "").strip()
        if new_status:
            current_status = new_status
            await m.reply(f"✅ **Status yangilandi:**\n_{current_status}_")
            return
        else:
            await m.reply(f"📍 **Hozirgi status:**\n_{current_status}_\n\nYangilash uchun: `/status [yangi matn]` deb yozing.")
            return

    # 1. @diegohelp orqali murojaat
    if m.text and "@diegohelp" in m.text.lower():
        text_clean = m.text.replace("@diegohelp", "").replace("@Diegohelp", "").strip()
        print(f"📩 @diegohelp chaqirildi ({sender_name}): {text_clean}")
        
        if not text_clean:
            await m.reply(f"🤖 **Diego AI:** Salom {sender_name}! Men Diegoning shaxsiy yordamchisiman. Sizga qanday yordam bera olaman?")
            return

        javob = await asyncio.to_thread(ai_javob, text_clean, sender_name, is_me)
        await m.reply(f"🤖 **Diego AI:**\n\n{javob}")

        urgent_keywords = ["chaqir", "shoshilinch", "срочно", "позови", "urgent", "call"]
        if any(w in text_clean.lower() for w in urgent_keywords) and not is_me:
            chat_title = event.chat.title if event.is_group else sender_name
            notify_text = (
                f"🚨 **SHOSHILINCH BILDIRISHNOMA!**\n\n"
                f"👤 **Kimdan:** {sender_name} (@{getattr(sender, 'username', 'yoq')})\n"
                f"💬 **Qayerda:** {chat_title}\n"
                f"📝 **Xabar:** {text_clean}"
            )
            await client.send_message("me", notify_text)
        return

    # 2. Golos va dumaloq video (krujok) - shaxsiy chatlarda
    if (m.voice or m.video_note) and event.is_private:
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

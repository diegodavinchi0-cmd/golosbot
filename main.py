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


def ovozni_matnga(path):
    with open(path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=("audio.ogg", f.read()),
            model="whisper-large-v3",
        )
    return r.text.strip()


@client.on(events.NewMessage(incoming=True))
async def handler(event):
    m = event.message
    if not (m.voice or m.video_note):
        return
    if not event.is_private:
        return
    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return
    dur = int(getattr(m.file, "duration", 0) or 0)
    if dur > MAX_SECONDS:
        return

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = await m.download_media(file=os.path.join(tmp, "a.ogg"))
            matn = await asyncio.to_thread(ovozni_matnga, path)
    except Exception as e:
        print("❌ xato:", e)
        return

    if not matn:
        return

    me = await client.get_me()
    if OUTPUT == "chat":
        await m.reply(f"__🤖 ai msg — transcribed for {me.first_name}__\n\n{matn}")
    else:
        kim = get_display_name(sender)
        await client.send_message("me", f"🎙 **{kim}** · {dur}s\n\n{matn}")
    print(f"✅ {get_display_name(sender)} → {matn[:60]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Telethon bot ishga tushmoqda...")
    await client.start()
    print("Telethon bot muvaffaqiyatli ulandi!")
    yield
    print("Telethon bot to'xtatilmoqda...")
    await client.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def home():
    return {"status": "ok", "message": "Golosbot 24/7 ishlab turibdi"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

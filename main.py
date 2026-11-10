"""
Diego AI — Master Main Application (Unified, Modular, 24/7 Production-Ready).
Integrates:
- Fast API Web Server (Health Check & Render Keep-Alive)
- Telethon Userbot Event Router
- StorageManager (SQLite WAL + FTS5)
- AIEngine (3-Layer Memory + Anti-Hallucination Guardrails)
- MemoryManager (Obsidian Sync & Deduplication)
- CommandHandler (/voice, /status, /remember, /forget, /brain, /sync)
- Full preservation of @diegohelp, Hadichaxon rules, urgent notifications, and voice-to-text.
"""

import os
import sys
import tempfile
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.utils import get_display_name
from groq import Groq

# Encoding sozlash (Windows uchun)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("diego_main")

# Modullarni import qilish
from modules.storage import StorageManager
from modules.memory_manager import MemoryManager
from modules.ai_engine import AIEngine
from modules.commands import CommandHandler

# Konfiguratsiya va kalitlar
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
GROQ_KEY = os.getenv("GROQ_KEY", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
OUTPUT = os.getenv("OUTPUT", "chat")
MAX_SECONDS = int(os.getenv("MAX_SECONDS", "600"))

# Yadro komponentlarni ishga tushirish
storage = StorageManager()
memory_mgr = MemoryManager(storage)
ai_engine = AIEngine(groq_key=GROQ_KEY, storage=storage, model="qwen/qwen3.8-27b")
command_handler = CommandHandler(storage, memory_mgr)

# Boshlang'ich Obsidian sinxronizatsiyasi
memory_mgr.sync_from_obsidian()

# Telethon client yaratish (StringSession bo'lsa shuni, bo'lmasa file-session ishlatadi)
if SESSION_STRING:
    logger.info("StringSession orqali ulanmoqda (Render / Cloud rejimi)...")
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    logger.info("File session orqali ulanmoqda (Lokal rejim)...")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    client = TelegramClient(os.path.join(BASE_DIR, "golosbot"), API_ID, API_HASH)

groq = Groq(api_key=GROQ_KEY)


def ovozni_matnga(path: str) -> str:
    """Whisper orqali ovozli xabarni matnga o'girish."""
    with open(path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=("audio.ogg", f.read()),
            model="whisper-large-v3",
        )
    return r.text.strip()


# ==========================================
# 1. "Избранное" (Saqlangan xabarlar) BUYRUQLARI
# ==========================================
@client.on(events.NewMessage(chats="me"))
async def me_commands_router(event):
    m = event.message
    if not m.text:
        return

    # Buyruq bo'lsa ishlov beramiz
    if m.text.startswith("/"):
        reply = command_handler.handle_command(m.text)
        if reply:
            await m.reply(reply)
            logger.info("Buyruq bajarildi: %s", m.text)


# ==========================================
# 2. KIRUVCHI XABARLAR (Guruhlar va Shaxsiy chatlar)
# ==========================================
@client.on(events.NewMessage(incoming=True))
async def incoming_messages_router(event):
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
    chat_id = event.chat_id
    chat_title = getattr(event.chat, "title", "") or sender_name

    # Xabarni L1 xotiraga (SQLite) yozib qo'yish
    if m.text:
        storage.add_message(
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_title=chat_title,
            message_text=m.text,
            is_from_me=False
        )

    # --- A. @diegohelp TRIGGERS (AI Javob berishi) ---
    if m.text and "@diegohelp" in m.text.lower():
        text_clean = m.text.replace("@diegohelp", "").replace("@Diegohelp", "").strip()
        logger.info("@diegohelp chaqirildi (%s): %s", sender_name, text_clean)

        # Agar biror golosga reply qilib @diegohelp yozilgan bo'lsa
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
                    logger.error("Reply golos xatosi: %s", e)

        if not text_clean:
            # Hadichaxon tekshiruvi
            greeting = "Hadichaxon" if (sender_username.lower() == "soim_h" or sender_id == 7795903945) else sender_name
            await m.reply(f"🤖 **Diego AI:** Salom {greeting}! Men Diegoning shaxsiy yordamchisiman. Sizga qanday yordam bera olaman?")
            return

        # AI Engine orqali 3-qatlamli kontekst asosida javob olish
        javob = await asyncio.to_thread(
            ai_engine.generate_response,
            chat_id, sender_id, sender_name, sender_username, text_clean, False
        )
        await m.reply(f"🤖 **Diego AI:**\n\n{javob}")

        # AI javobini ham suhbatlar tarixiga qo'shish (L1 Context)
        storage.add_message(
            chat_id=chat_id,
            sender_id=me.id,
            sender_name="Diego AI",
            chat_title=chat_title,
            message_text=javob,
            is_from_me=True
        )

        # Shoshilinch bildirishnoma ("Diegoni chaqir", "shoshilinch")
        urgent_keywords = ["chaqir", "shoshilinch", "срочно", "позови", "urgent", "call"]
        if any(w in text_clean.lower() for w in urgent_keywords):
            notify_text = (
                f"🚨 **SHOSHILINCH BILDIRISHNOMA!**\n\n"
                f"👤 **Kimdan:** {sender_name} (@{sender_username})\n"
                f"💬 **Qayerda:** {chat_title}\n"
                f"📝 **Xabar:** {text_clean}"
            )
            await client.send_message("me", notify_text)
            logger.info("Shoshilinch bildirishnoma Diegoga yuborildi.")
        return

    # --- B. OVOZLI XABARLAR (Faqat voice_enabled=true bo'lganda) ---
    voice_state = storage.get_setting("voice_enabled", "false")
    if (m.voice or m.video_note) and event.is_private and (voice_state == "true"):
        dur = int(getattr(m.file, "duration", 0) or 0)
        if dur > MAX_SECONDS:
            return

        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = await m.download_media(file=os.path.join(tmp, "a.ogg"))
                matn = await asyncio.to_thread(ovozni_matnga, path)
        except Exception as e:
            logger.error("Golos transkripsiyasida xatolik: %s", e)
            return

        if not matn:
            return

        my_name = (getattr(me, "first_name", "") or "Diego").strip()
        if OUTPUT == "chat":
            await m.reply(f"__🤖 ai msg — transcribed for {my_name}__\n\n{matn}")
        else:
            await client.send_message("me", f"🎙 **{sender_name}** · {dur}s\n\n{matn}")


# ==========================================
# 3. FASTAPI SERVER LIFESPAN (Render 24/7)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Diego AI Core ishga tushmoqda...")
    await client.start()
    me = await client.get_me()
    logger.info("Telegram muvaffaqiyatli ulandi: %s (@%s)", me.first_name, me.username)
    yield
    logger.info("Diego AI Core to'xtatilmoqda...")
    await client.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def health_check():
    curr_status = storage.get_setting("status", "Active")
    v_state = storage.get_setting("voice_enabled", "false")
    return {
        "status": "ok",
        "service": "Diego AI 24/7 Master",
        "current_status": curr_status,
        "voice_transcription": "enabled" if v_state == "true" else "disabled"
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

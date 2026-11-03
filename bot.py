import os
import sys
import tempfile
import asyncio

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from telethon import TelegramClient, events
from telethon.utils import get_display_name
from groq import Groq
from config import API_ID, API_HASH, GROQ_KEY, OUTPUT, MAX_SECONDS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
client = TelegramClient(os.path.join(BASE_DIR, "golosbot"), API_ID, API_HASH)
groq = Groq(api_key=GROQ_KEY)


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
    if not (m.voice or m.video_note):        # faqat golos yoki dumaloq video
        return
    if not event.is_private:                 # faqat shaxsiy chatlar
        return
    sender = await event.get_sender()
    if getattr(sender, "bot", False):        # botlarning goloslariga javob bermaymiz
        return
    dur = int(getattr(m.file, "duration", 0) or 0)
    if dur > MAX_SECONDS:                    # juda uzun — o'tkazib yuboramiz
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


if __name__ == "__main__":
    client.start()
    print("Bot ishlayapti... (to'xtatish: Ctrl+C)")
    client.run_until_disconnected()

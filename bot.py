import os
import sys
import glob
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
OBSIDIAN_DIR = r"C:\Users\hp\Desktop\Obsidian_Brain"

client = TelegramClient(os.path.join(BASE_DIR, "golosbot"), API_ID, API_HASH)
groq = Groq(api_key=GROQ_KEY)


def load_obsidian_context() -> str:
    """Obsidian_Brain dagi fayllarni o'qib, AI ga bilim (kontekst) tayyorlaydi."""
    parts = []
    
    # 1. AI_Profile.md
    profile_path = os.path.join(OBSIDIAN_DIR, "AI_Profile.md")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                parts.append("### Profil va Qoidalar:\n" + f.read())
        except Exception:
            pass

    # 2. status.md
    status_path = os.path.join(OBSIDIAN_DIR, "status.md")
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                parts.append("### Hozirgi Status va Bandlik:\n" + f.read())
        except Exception:
            pass

    # 3. TASKS.md (agar bor bo'lsa qisqacha)
    tasks_path = os.path.join(OBSIDIAN_DIR, "TASKS.md")
    if os.path.exists(tasks_path):
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                content = f.read()[:1000] # Birinchi 1000 belgisi
                parts.append("### Diego rejalari (qisqacha):\n" + content)
        except Exception:
            pass

    return "\n\n".join(parts)


def ovozni_matnga(path):
    with open(path, "rb") as f:
        r = groq.audio.transcriptions.create(
            file=("audio.ogg", f.read()),
            model="whisper-large-v3",
        )
    return r.text.strip()


def ai_javob(savol: str, sender_name: str, is_me: bool) -> str:
    obsidian_context = load_obsidian_context()
    
    system_prompt = (
        "Sen Diego'ning (Zulfiqor) shaxsiy sun'iy intellekt yordamchisisan (Diego AI).\n"
        "Sening miyang Obsidian_Brain dagi qaydlarga ulangan.\n\n"
        f"--- OBSIDIAN MIYA MA'LUMOTLARI ---\n{obsidian_context}\n-----------------------------------\n\n"
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
    m = event.message
    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return

    me = await client.get_me()
    sender_name = get_display_name(sender) if sender else "Do'stim"
    is_me = (sender and sender.id == me.id)

    # 1. @diegohelp orqali murojaat
    if m.text and "@diegohelp" in m.text.lower():
        text_clean = m.text.replace("@diegohelp", "").replace("@Diegohelp", "").strip()
        print(f"📩 @diegohelp chaqirildi ({sender_name}): {text_clean}")
        
        if not text_clean:
            await m.reply(f"🤖 **Diego AI:** Salom {sender_name}! Men Diegoning shaxsiy yordamchisiman. Sizga qanday yordam bera olaman?")
            return

        javob = await asyncio.to_thread(ai_javob, text_clean, sender_name, is_me)
        await m.reply(f"🤖 **Diego AI:**\n\n{javob}")
        print(f"✅ Javob yuborildi: {javob[:60]}...")

        # Agar kimdir "chaqir" yoki "shoshilinch" deb yozsa, o'zingizning "Saqlangan xabarlar"ga xabar tashlaydi
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
            print(f"🔔 Diegoga shoshilinch signal yuborildi!")
        return

    # 2. Golos va dumaloq video (krujok) - faqat shaxsiy chatlarda
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
        print(f"✅ Golos ({sender_name}) → {matn[:60]}")


if __name__ == "__main__":
    client.start()
    print("🧠 Diego AI (Obsidian Brain ulandi) ishlayapti...")
    client.run_until_disconnected()

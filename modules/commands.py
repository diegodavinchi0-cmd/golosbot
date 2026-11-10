"""
Diego AI — Telegram Commands Processor.
Handles commands sent from "Saved Messages" (chats="me") and authorized users.
"""

import logging
from typing import Optional
from modules.storage import StorageManager
from modules.memory_manager import MemoryManager

logger = logging.getLogger("diego_commands")
logger.setLevel(logging.INFO)


class CommandHandler:
    """Telegram buyruqlarini qabul qilish va boshqarish."""

    def __init__(self, storage: StorageManager, memory_mgr: MemoryManager):
        self.storage = storage
        self.memory_mgr = memory_mgr

    def handle_command(self, cmd_text: str) -> Optional[str]:
        """Buyruqni tahlil qilib natija matnini qaytarish."""
        text = cmd_text.strip()
        cmd_lower = text.lower()

        # 1. /voice on / /voice off
        if cmd_lower == "/voice on":
            self.storage.set_setting("voice_enabled", "true")
            return "🎙 **Goloslarni matnga o'girish YOQILDI!**\nEndi kelgan ovozli xabarlar avtomatik matnga aylanadi."
        
        elif cmd_lower == "/voice off":
            self.storage.set_setting("voice_enabled", "false")
            return "⏸ **Goloslarni matnga o'girish O'CHIRILDI!**\nOvozli xabarlar avtomatik o'girilmaydi."

        # 2. /status
        elif cmd_lower.startswith("/status"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                new_status = parts[1].strip()
                self.storage.set_setting("status", new_status)
                # Obsidian'ga ham sinxron yozish
                self.memory_mgr.sync_status_to_obsidian(new_status)
                return f"✅ **Status yangilandi:**\n_{new_status}_"
            else:
                curr_status = self.storage.get_setting("status", "Ko'rsatilmagan")
                v_state = "YOQILGAN" if self.storage.get_setting("voice_enabled", "false") == "true" else "O'CHIRILGAN"
                return (
                    f"📍 **Hozirgi status:**\n_{curr_status}_\n"
                    f"🎙 Goloslar: **{v_state}**\n\n"
                    f"Boshqarish:\n• `/status [yangi status]`\n• `/voice on` yoki `/voice off`"
                )

        # 3. /remember [fakt]
        elif cmd_lower.startswith("/remember"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                return self.memory_mgr.remember_fact(parts[1])
            return "Iltimos, eslab qolish kerak bo'lgan ma'lumotni yozing.\nMisol: `/remember Chorshanba kuni imtihon bor`"

        # 4. /forget [qidiruv]
        elif cmd_lower.startswith("/forget"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                return self.memory_mgr.forget_fact(parts[1])
            return "O'chirish uchun biror kalit so'z yozing.\nMisol: `/forget imtihon`"

        # 5. /brain [qidiruv]
        elif cmd_lower.startswith("/brain"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                facts = self.storage.search_facts(parts[1], limit=5)
                if not facts:
                    return f"🧠 '{parts[1]}' bo'yicha xotirada hech narsa topilmadi."
                res = [f"• **{f['subject']}:** {f['fact']}" for f in facts]
                return f"🧠 **Topilgan xotiralar:**\n\n" + "\n".join(res)
            return "Xotiradan qidirish uchun so'z yozing.\nMisol: `/brain RestoFlow`"

        # 6. /sync (Obsidian sinxronlash)
        elif cmd_lower == "/sync":
            res = self.memory_mgr.sync_from_obsidian()
            return f"🔄 **Obsidian sinxronlandi:** {res.get('synced_files', 0)} ta fayl yangilandi."

        return None

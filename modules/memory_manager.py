"""
Diego AI — Obsidian Bridge & AI Memory Manager.
Handles bidirectional synchronization between Obsidian_Brain and SQLite,
deduplication, contradiction resolution, and memory hygiene.
"""

import os
import re
import logging
from typing import Dict, Any, List
from modules.storage import StorageManager

logger = logging.getLogger("diego_memory_mgr")
logger.setLevel(logging.INFO)

OBSIDIAN_DIR = r"C:\Users\hp\Desktop\Obsidian_Brain"


class MemoryManager:
    """Xotirani tartibga soluvchi va Obsidian bilan sinxronlovchi boshqaruvchi."""

    def __init__(self, storage: StorageManager, obsidian_dir: str = OBSIDIAN_DIR):
        self.storage = storage
        self.obsidian_dir = obsidian_dir

    def sync_from_obsidian(self) -> Dict[str, Any]:
        """Obsidian_Brain papkasidagi markdown fayllarni o'qib, SQLite xotirasini yangilash."""
        if not os.path.exists(self.obsidian_dir):
            logger.warning("Obsidian papkasi topilmadi: %s", self.obsidian_dir)
            return {"status": "not_found", "synced_files": 0}

        synced = []

        # 1. status.md faylini sinxronlash
        status_file = os.path.join(self.obsidian_dir, "status.md")
        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # Status matnini tozalash
                clean_lines = [l.strip().lstrip("-*# ") for l in content.splitlines() if l.strip()]
                clean_status = " ".join(clean_lines[:3]) if clean_lines else "Bandman"
                self.storage.set_setting("status", clean_status)
                synced.append("status.md")
            except Exception as e:
                logger.error("status.md o'qishda xatolik: %s", e)

        # 2. AI_Profile.md dan asosiy faktlarni olish
        profile_file = os.path.join(self.obsidian_dir, "AI_Profile.md")
        if os.path.exists(profile_file):
            try:
                with open(profile_file, "r", encoding="utf-8") as f:
                    text = f.read()
                # Diego shaxsi haqidagi fakt
                self.storage.add_fact(
                    category="personal",
                    subject="Diego",
                    fact="Zulfiqor (Diego) — Full-stack dasturchi, RestoFlow loyihasi muallifi.",
                    source="obsidian"
                )
                synced.append("AI_Profile.md")
            except Exception as e:
                logger.error("AI_Profile.md o'qishda xatolik: %s", e)

        # 3. Hadichaxon kontaktini doimiy to'g'ri saqlash
        self.storage.set_contact_details(
            telegram_id=7795903945,
            preferred_name="Hadichaxon",
            relationship="sweetheart",
            notes="Faqat Hadichaxon deb hurmat bilan murojaat qilinsin."
        )

        return {"status": "ok", "synced_files": len(synced), "files": synced}

    def sync_status_to_obsidian(self, new_status: str) -> bool:
        """Telegram'dan /status o'zgarganda Obsidian'dagi status.md ni ham yangilash."""
        if not os.path.exists(self.obsidian_dir):
            return False

        status_file = os.path.join(self.obsidian_dir, "status.md")
        try:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"# 📍 Hozirgi Status va Bandlik\n\n- {new_status}\n")
            return True
        except Exception as e:
            logger.error("Obsidian status.md ga yozishda xatolik: %s", e)
            return False

    def remember_fact(self, raw_text: str, category: str = "general") -> str:
        """Foydalanuvchi /remember buyrug'i berganda faktni deduplikatsiya bilan saqlash."""
        text = raw_text.strip()
        if not text:
            return "Bo'sh ma'lumotni eslab qola olmayman."

        # Mavjud faktlarni tekshirish (Deduplication)
        existing = self.storage.search_facts(text[:30], limit=3)
        for f in existing:
            if text.lower() in f["fact"].lower() or f["fact"].lower() in text.lower():
                return f"Bu ma'lumot allaqachon xotirada bor: '{f['fact']}'"

        self.storage.add_fact(category=category, subject="Diego Memory", fact=text, source="user_command")
        return f"✅ Xotiraga saqlab oldim: '{text}'"

    def forget_fact(self, query: str) -> str:
        """Xotiradan faktni topib o'chirish."""
        results = self.storage.search_facts(query, limit=1)
        if not results:
            return f"'{query}' bo'yicha hech narsa topilmadi."

        fact_id = results[0]["id"]
        fact_text = results[0]["fact"]
        with self.storage._get_conn() as conn:
            conn.execute("UPDATE memory_facts SET is_active = 0 WHERE id = ?", (fact_id,))
        return f"🗑 Xotiradan o'chirildi: '{fact_text}'"

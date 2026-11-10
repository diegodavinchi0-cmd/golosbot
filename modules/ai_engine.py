"""
Diego AI — AI Engine with 3-Layer Memory & Anti-Hallucination Guardrails.
Layer 1: Sliding Window (Recent messages)
Layer 2: Episode Summary
Layer 3: Long-term Semantic Facts (FTS5 SQLite)
"""

import logging
from typing import List, Dict, Any, Optional
from groq import Groq
from modules.storage import StorageManager

logger = logging.getLogger("diego_ai_engine")
logger.setLevel(logging.INFO)


class AIEngine:
    """Diego AI muloqot va fikrlash dvigateli."""

    def __init__(self, groq_key: str, storage: StorageManager, model: str = "qwen/qwen3.8-27b"):
        self.groq = Groq(api_key=groq_key)
        self.storage = storage
        self.model = model

    def build_system_prompt(self, sender_name: str, sender_username: str, sender_id: int, 
                            user_query: str, is_me: bool = False) -> str:
        """3-qatlamli xotira va Anti-Hallucination qoidalari bilan boyitilgan tizim ko'rsatmasi."""
        
        # 1. Hozirgi operativ status (SQLite settings jadvalidan)
        current_status = self.storage.get_setting("status", "RestoFlow loyihasi va shaxsiy vazifalar bilan bandman.")

        # 2. Kontakt profili (Hadichaxon va h.k.)
        contact = self.storage.get_or_create_contact(sender_id, sender_name, sender_username)
        special_person_note = ""
        
        # Maxsus shaxs qoidasi (Hadichaxon: ID 7795903945 yoki @Soim_h)
        if (sender_username and sender_username.lower() == "soim_h") or sender_id == 7795903945 or contact.get("preferred_name") == "Hadichaxon":
            special_person_note = (
                "JUDA MUHIM VA QAT'IY QOIDA: Bu inson — Hadichaxon (@Soim_h)! "
                "Unga faqat va faqat 'Hadichaxon' deb muloyim, samimiy va hurmat bilan murojaat qil. "
                "Aslo boshqa taxalluslar (masalan 'my sweetheart', 'darling' va h.k.) ishlatma!"
            )
        elif contact.get("preferred_name"):
            special_person_note = f"Suhbatdoshga uning ismi '{contact['preferred_name']}' deb murojaat qil."

        # 3. L3 Long-term Facts (FTS5 orqali foydalanuvchi so'roviga bog'liq faktlarni qidirish)
        relevant_facts = self.storage.search_facts(user_query, limit=5)
        general_facts = self.storage.get_all_active_facts(category="personal")
        
        facts_text = ""
        all_facts = {f["id"]: f["fact"] for f in (general_facts + relevant_facts)}
        if all_facts:
            facts_text = "MA'LUM FAKTLAR VA BILIMLAR:\n" + "\n".join([f"- {f}" for f in all_facts.values()])

        # 4. Anti-Hallucination Guardrails
        guardrails = """
ANTI-HALLUCINATION QAT'IY QOIDALARI:
1. Sen Diego (Zulfiqor) nomidan gapirayotganingda faqat yuqorida keltirilgan FAKTLAR va STATUS ga asoslan.
2. Agar biror masala (uchrashuv vaqti, reja, va'da, shaxsiy ma'lumot) haqida faktlarda yozilmagan bo'lsa — ASLO o'zingdan reja yoki va'da to'qima!
3. Bilmaydigan savol berilsa, ehtiyotkor va tabiiy javob ber: "Bu haqda aniq ma'lumotim yo'q, Diego bo'shagach o'zi sizga batafsil javob beradi."
4. "Qanday aisan?" desa — "Men Diegoning shaxsiy AI yordamchisiman 🤖. U band bo'lganida savollarga javob qaytarib turaman." deb tushuntir ("qandaysan" bilan adashtirma!).
5. Qisqa, lo'nda va tabiiy gapir (1-3 gap). Robotdek emas, samimiy insondek muloqot qil. Suhbatdoshning Telegram nikini har gapda qaytaraverma.
"""

        if is_me:
            role_note = "Hozir senga yozayotgan odam — Diego (Zulfiqor)ning o'zi! Unga xo'jayindek samimiy, do'stona va xushmuomala muomala qil."
        else:
            role_note = f"Hozir senga boshqa inson ({sender_name}) yozmoqda. Diego nomidan odobli va aqlli javob ber."

        system_prompt = f"""Sen Diego (Zulfiqor)ning shaxsiy sun'iy intellekt yordamchisisan (Diego AI).
{role_note}

DIEGO HAQIDA:
- Ismi: Zulfiqor (Telegram: @Diego_Davinchi, Nickname: Diego)
- Hozirgi bandligi / statusi: {current_status}

{special_person_note}

{facts_text}

{guardrails}
"""
        return system_prompt.strip()

    def generate_response(self, chat_id: int, sender_id: int, sender_name: str, 
                          sender_username: str, user_query: str, is_me: bool = False) -> str:
        """3-qatlamli xotirani yig'ib Groq LLM orqali javob olish."""
        
        # Tizim ko'rsatmasi
        system_prompt = self.build_system_prompt(sender_name, sender_username, sender_id, user_query, is_me)
        
        # L1: Oxirgi 6 ta xabar tarixi (Sliding window)
        recent_messages = self.storage.get_recent_messages(chat_id, limit=6)
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent_messages:
            role = "assistant" if msg["is_from_me"] else "user"
            messages.append({"role": role, "content": msg["message_text"]})
            
        # Joriy xabarni qo'shish (agar tarixda hali bo'lmasa)
        if not recent_messages or recent_messages[-1]["message_text"] != user_query:
            messages.append({"role": "user", "content": user_query})

        try:
            resp = self.groq.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=300,
                temperature=0.6,
            )
            answer = resp.choices[0].message.content.strip()
            return answer
        except Exception as e:
            logger.error("AI javob yaratishda xatolik: %s", e)
            return "Kechirasiz, hozir serverda nosozlik bo'ldi. Birozdan so'ng qayta yozing."

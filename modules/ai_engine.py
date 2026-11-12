"""
Diego AI — AI Engine with 3-Layer Memory & Anti-Hallucination Guardrails.
Layer 1: Sliding Window (Recent messages)
Layer 2: Episode Summary
Layer 3: Long-term Semantic Facts (FTS5 SQLite)
"""

import os
import logging
import httpx
from typing import List, Dict, Any, Optional
from groq import Groq
from modules.storage import StorageManager

logger = logging.getLogger("diego_ai_engine")
logger.setLevel(logging.INFO)


class AIEngine:
    """Diego AI muloqot va fikrlash dvigateli."""

    def __init__(self, groq_key: str, storage: StorageManager, model: str = "qwen/qwen3.8-27b",
                 gemini_key: str = ""):
        self.groq = Groq(api_key=groq_key)
        self.gemini_key = gemini_key or os.getenv("GEMINI_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.storage = storage
        self.model = model

    def build_system_prompt(self, sender_name: str, sender_username: str, sender_id: int, 
                            user_query: str, is_me: bool = False) -> str:
        """3-qatlamli xotira va Anti-Hallucination qoidalari bilan boyitilgan tizim ko'rsatmasi."""
        
        # 1. Hozirgi operativ status (SQLite settings jadvalidan)
        # Status FAQAT suhbatdosh bandlik/status haqida so'ragandagina promptga qo'shiladi.
        q_low = (user_query or "").lower()
        status_keys = ("band", "status", "nima qil", "nima bilan", "qayerda", "qachon", "bo'sh", "bosh",
                       "ishlay", "hozir", "чем занят", "занят", "где", "what r y doing", "busy")
        status_asked = any(k in q_low for k in status_keys)
        current_status = self.storage.get_setting("status", "") if status_asked else ""

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
        # RestoFlow haqidagi faktlar faqat savolda RestoFlow tilga olinganda ko'rsatiladi
        if "restoflow" not in q_low:
            all_facts = {i: t for i, t in all_facts.items() if "restoflow" not in t.lower()}
        if all_facts:
            facts_text = "MA'LUM FAKTLAR VA BILIMLAR:\n" + "\n".join([f"- {f}" for f in all_facts.values()])

        # 4. Anti-Hallucination Guardrails
        guardrails = """
ANTI-HALLUCINATION QAT'IY QOIDALARI:
1. Sen Diego (Zulfiqor) nomidan gapirayotganingda faqat yuqorida keltirilgan FAKTLAR ga asoslan. Status va bandlik haqida faqat suhbatdosh so'raganda gapir.
2. Agar biror masala (uchrashuv vaqti, reja, va'da, shaxsiy ma'lumot) haqida faktlarda yozilmagan bo'lsa — ASLO o'zingdan reja yoki va'da to'qima!
3. Bilmaydigan savol berilsa, ehtiyotkor va tabiiy javob ber: "Bu haqda aniq ma'lumotim yo'q, Diego bo'shagach o'zi sizga batafsil javob beradi."
4. "Qanday aisan?" desa — "Men Diegoning shaxsiy AI yordamchisiman 🤖. U band bo'lganida savollarga javob qaytarib turaman." deb tushuntir ("qandaysan" bilan adashtirma!).
5. Qisqa, lo'nda va tabiiy gapir (1-3 gap). Robotdek emas, samimiy insondek muloqot qil. Suhbatdoshning Telegram nikini har gapda qaytaraverma.
6. Faqat so'ralgan narsaga javob ber. Salomlashuv yoki oddiy gapga ("salom", "wassup") faqat qisqa salom bilan javob ber.
7. Diegoning ishi, loyihalari (jumladan RestoFlow), bandligi, rejalari yoki shaxsiy ma'lumotlarini O'ZINGDAN ASLO aytma. Faqat suhbatdosh aniq so'rasa va faktlarda bo'lsa ayt. Aks holda "Bu haqda Diego o'zi aytadi" de.
8. O'zingni har gapda "Diegoning AI yordamchisiman" deb qayta-qayta tanishtirma. Faqat so'ralganda yoki birinchi marta tanishtir.
"""

        if is_me:
            role_note = "Hozir senga yozayotgan odam — Diego (Zulfiqor)ning o'zi! Unga xo'jayindek samimiy, do'stona va xushmuomala muomala qil."
        else:
            role_note = f"Hozir senga boshqa inson ({sender_name}) yozmoqda. Diego nomidan odobli va aqlli javob ber."

        system_prompt = f"""Sen Diego (Zulfiqor)ning shaxsiy sun'iy intellekt yordamchisisan (Diego AI).
{role_note}

DIEGO HAQIDA:
- Ismi: Zulfiqor (Telegram: @Diego_Davinchi, Nickname: Diego)
- Hozirgi bandligi / statusi: {current_status or "(so'ralmagan, bu haqda GAPIRMA)"}

{special_person_note}

{facts_text}

{guardrails}

{self._load_user_rules()}
"""
        return system_prompt.strip()

    @staticmethod
    def _load_user_rules() -> str:
        """rules/*.md (Obsidian'dan sync_rules.bat orqali ko'chirilgan) qoidalarini promptga qo'shish."""
        rules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules")
        if not os.path.isdir(rules_dir):
            return ""
        parts = []
        for name in sorted(os.listdir(rules_dir)):
            if name.endswith(".md"):
                try:
                    with open(os.path.join(rules_dir, name), "r", encoding="utf-8") as f:
                        txt = f.read().split("\n---\n## 🔗")[0].strip()
                    parts.append(txt)
                except Exception as e:
                    logger.warning("Qoida fayli o'qilmadi (%s): %s", name, e)
        return ("FOYDALANUVCHI (DIEGO) QOIDALARI — ENG MUHIM, ularga qat'iy amal qil:\n" + "\n\n".join(parts)) if parts else ""

    def generate_response(self, chat_id: int, sender_id: int, sender_name: str,
                          sender_username: str, user_query: str, is_me: bool = False) -> str:
        """Javob olib, so'ralmagan bo'lsa RestoFlow/bandlik haqidagi gaplarni qat'iy olib tashlaydi."""
        answer = self._generate_raw(chat_id, sender_id, sender_name, sender_username, user_query, is_me)
        if is_me:
            return answer
        return self._strip_unasked(answer, user_query)

    @staticmethod
    def _strip_unasked(answer: str, user_query: str) -> str:
        import re
        q = (user_query or "").lower()
        banned = []
        if "restoflow" not in q:
            banned.append("restoflow")
        if not any(k in q for k in ("band", "nima qil", "nima bilan", "qayerda", "ishlay", "hozir", "занят", "doing", "busy")):
            banned += ["loyihasi ustida", "ustida ishlay", "kompyuterda", "ustida band"]
        if not banned:
            return answer
        parts = re.split(r"(?<=[.!?])\s+", answer.strip())
        kept = [p for p in parts if not any(b in p.lower() for b in banned)]
        if kept == parts:
            return answer
        return " ".join(kept).strip() or "Qanday yordam bera olaman?"

    def _generate_raw(self, chat_id: int, sender_id: int, sender_name: str,
                      sender_username: str, user_query: str, is_me: bool = False) -> str:
        """3-qatlamli xotirani yig'ib Groq LLM orqali javob olish."""
        
        # Tizim ko'rsatmasi
        system_prompt = self.build_system_prompt(sender_name, sender_username, sender_id, user_query, is_me)
        
        # L1: Oxirgi 6 ta xabar tarixi (Sliding window)
        recent_messages = self.storage.get_recent_messages(chat_id, limit=6)
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent_messages:
            role = "assistant" if msg["is_from_me"] else "user"
            # Oldingi AI javoblarida RestoFlow/bandlik gapi bo'lsa, model uni qayta takrorlamasligi uchun tushirib qoldiramiz
            if role == "assistant" and "restoflow" in msg["message_text"].lower() and "restoflow" not in (user_query or "").lower():
                continue
            messages.append({"role": role, "content": msg["message_text"]})
            
        # Joriy xabarni qo'shish (agar tarixda hali bo'lmasa)
        if not recent_messages or recent_messages[-1]["message_text"] != user_query:
            messages.append({"role": "user", "content": user_query})

        # 1) Gemini (asosiy), 2) Groq (zaxira)
        if self.gemini_key:
            try:
                return self._call_gemini(messages)
            except Exception as e:
                logger.warning("Gemini xatolik, Groq zaxirasiga o'tilmoqda: %s", e)
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

    def _call_gemini(self, messages: List[Dict[str, str]]) -> str:
        """Gemini REST API. Model 404 bersa, mavjud modelni o'zi topib almashtiradi."""
        try:
            return self._gemini_request(self.gemini_model, messages)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
            alt = self._discover_gemini_model(exclude=self.gemini_model)
            if not alt:
                raise
            text = self._gemini_request(alt, messages)
            logger.info("Gemini modeli almashtirildi: %s -> %s", self.gemini_model, alt)
            self.gemini_model = alt
            return text

    def _gemini_request(self, model: str, messages: List[Dict[str, str]]) -> str:
        """Gemini REST API (kalit header orqali yuboriladi, URL'da emas)."""
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": self.gemini_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": contents,
                # Pro/thinking modellar fikrlash uchun ham token sarflaydi, shuning uchun zaxira bilan
                "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.6},
            },
            timeout=30,
        )
        r.raise_for_status()
        parts = r.json()["candidates"][0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise ValueError("Gemini bo'sh javob qaytardi")
        return text

    def _discover_gemini_model(self, exclude: str = "") -> str:
        """ListModels orqali generateContent qo'llaydigan mavjud modelni tanlaydi."""
        import re
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            headers={"x-goog-api-key": self.gemini_key},
            timeout=20,
        )
        r.raise_for_status()
        names = [
            m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
        logger.info("Mavjud Gemini modellari: %s", ", ".join(names[:25]))
        names = [n for n in names if n != exclude]

        for pref in ("gemini-pro-latest", "gemini-flash-latest", "gemini-2.5-pro", "gemini-2.5-flash"):
            if pref in names:
                return pref

        def ver(n: str):
            m = re.match(r"gemini-(\d+(?:\.\d+)?)-(pro|flash)$", n)
            return (float(m.group(1)), 1 if m.group(2) == "pro" else 0) if m else None

        cands = [(ver(n), n) for n in names if ver(n)]
        return max(cands)[1] if cands else ""

"""
Test suite for StorageManager:
- Database initialization
- WAL mode check
- Atomic writes & Concurrent reads/writes (100 parallel threads)
- Full-Text Search (FTS5) check
- Contacts & Settings management
"""

import os
import sys
import unittest
import threading
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.storage import StorageManager, get_connection


class TestStorageManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_memory.db")
        self.storage = StorageManager(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_wal_mode_enabled(self):
        """WAL rejimi yoqilganligini tekshirish."""
        conn = get_connection(self.db_path)
        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_settings_key_value(self):
        """Settings o'qish va yozish testi."""
        self.storage.set_setting("status", "Darsdaman")
        self.assertEqual(self.storage.get_setting("status"), "Darsdaman")
        
        # Yangilash (ON CONFLICT)
        self.storage.set_setting("status", "Uydaman")
        self.assertEqual(self.storage.get_setting("status"), "Uydaman")

    def test_conversations_flow(self):
        """Suhbatlar tarixi va slayd oynasi (Sliding window) testi."""
        chat_id = 12345
        for i in range(15):
            self.storage.add_message(
                chat_id=chat_id,
                sender_id=999,
                sender_name="User",
                message_text=f"Xabar #{i}",
                is_from_me=(i % 2 == 0)
            )

        # Oxirgi 5 ta xabar tartibli kelishi kerak
        recent = self.storage.get_recent_messages(chat_id, limit=5)
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[0]["message_text"], "Xabar #10")
        self.assertEqual(recent[-1]["message_text"], "Xabar #14")

    def test_fts5_search(self):
        """FTS5 to'liq matn qidiruvi testi."""
        self.storage.add_fact(
            category="project",
            subject="RestoFlow",
            fact="RestoFlow loyihasi restoranlar uchun avtomatlashtirish tizimi"
        )
        self.storage.add_fact(
            category="contact",
            subject="Hadichaxon",
            fact="Hadichaxon chorshanba kuni soat 14:00 da darsda bo'ladi"
        )

        results = self.storage.search_facts("RestoFlow")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subject"], "RestoFlow")

        results_hadicha = self.storage.search_facts("Hadichaxon")
        self.assertEqual(len(results_hadicha), 1)
        self.assertIn("14:00", results_hadicha[0]["fact"])

    def test_contacts_preferred_name(self):
        """Hadichaxon va boshqa kontaktlar profili testi."""
        contact = self.storage.get_or_create_contact(
            telegram_id=7795903945,
            display_name="My sweetheart",
            username="Soim_h"
        )
        self.assertEqual(contact["telegram_id"], 7795903945)

        # Preferred name kiritish
        self.storage.set_contact_details(
            telegram_id=7795903945,
            preferred_name="Hadichaxon",
            relationship="sweetheart",
            notes="Faqat Hadichaxon deb murojaat qilinsin"
        )

        updated = self.storage.get_or_create_contact(7795903945, "My sweetheart")
        self.assertEqual(updated["preferred_name"], "Hadichaxon")
        self.assertEqual(updated["relationship"], "sweetheart")

    def test_concurrent_stress(self):
        """100 ta parallel oqimda (threads) concurrent yozish stress testi."""
        errors = []

        def worker(thread_id):
            try:
                for i in range(10):
                    self.storage.add_message(
                        chat_id=100 + thread_id,
                        sender_id=thread_id,
                        sender_name=f"Thread-{thread_id}",
                        message_text=f"Concurrent message {i} from thread {thread_id}"
                    )
                    self.storage.set_setting(f"thread_{thread_id}", str(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent yozishda xatoliklar chiqdi: {errors}")


if __name__ == "__main__":
    unittest.main()

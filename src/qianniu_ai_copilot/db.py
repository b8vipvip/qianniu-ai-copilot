from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import settings


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


def _join_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if str(v).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


class Database:
    def __init__(self, path: Path = settings.db_path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    brand TEXT DEFAULT '',
                    price TEXT DEFAULT '',
                    sku_info TEXT DEFAULT '',
                    specs_json TEXT DEFAULT '{}',
                    selling_points TEXT DEFAULT '',
                    shipping_info TEXT DEFAULT '',
                    after_sale_info TEXT DEFAULT '',
                    faq_json TEXT DEFAULT '[]',
                    raw_json TEXT DEFAULT '{}',
                    source_image_path TEXT DEFAULT '',
                    confidence REAL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    buyer_name TEXT DEFAULT '',
                    window_title TEXT DEFAULT '',
                    product_id TEXT DEFAULT '',
                    product_title_hint TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT DEFAULT '',
                    product_id TEXT DEFAULT '',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    message_hash TEXT DEFAULT '',
                    raw_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qa_pairs (
                    id TEXT PRIMARY KEY,
                    product_id TEXT DEFAULT '',
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    quality_score REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replies (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT DEFAULT '',
                    product_id TEXT DEFAULT '',
                    buyer_message TEXT DEFAULT '',
                    answer TEXT NOT NULL,
                    confidence REAL DEFAULT 0,
                    needs_human INTEGER DEFAULT 0,
                    should_auto_send INTEGER DEFAULT 0,
                    reason TEXT DEFAULT '',
                    raw_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    reply_id TEXT DEFAULT '',
                    product_id TEXT DEFAULT '',
                    original_answer TEXT DEFAULT '',
                    final_answer TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return None if row is None else {key: row[key] for key in row.keys()}

    @staticmethod
    def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [{key: row[key] for key in row.keys()} for row in rows]

    def upsert_product_from_ai(self, data: dict[str, Any], source_image_path: str = "") -> dict[str, Any]:
        title = str(data.get("title") or data.get("product_title") or "").strip()
        if not title:
            raise ValueError("AI 没有识别到商品标题，请重新截取商品详情页。")
        url = str(data.get("url") or data.get("product_url") or "").strip()
        specs = data.get("specs") or data.get("specs_json") or {}
        faq = data.get("faq_candidates") or data.get("faq") or []
        sku = data.get("sku_options") or data.get("sku_info") or ""
        ts = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM products WHERE title=? OR (url<>'' AND url=?) LIMIT 1", (title, url)
            ).fetchone()
            if existing:
                product_id = existing["id"]
                conn.execute(
                    """
                    UPDATE products SET title=?,url=?,category=?,brand=?,price=?,sku_info=?,specs_json=?,
                    selling_points=?,shipping_info=?,after_sale_info=?,faq_json=?,raw_json=?,source_image_path=?,confidence=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        title, url, str(data.get("category", "")), str(data.get("brand", "")), str(data.get("price", "")),
                        json.dumps(sku, ensure_ascii=False) if not isinstance(sku, str) else sku,
                        json.dumps(specs, ensure_ascii=False), _join_text(data.get("selling_points")),
                        _join_text(data.get("shipping_info")), _join_text(data.get("after_sale_info")),
                        json.dumps(faq, ensure_ascii=False), json.dumps(data, ensure_ascii=False), source_image_path,
                        float(data.get("confidence") or 0), ts, product_id,
                    ),
                )
            else:
                product_id = new_id()
                conn.execute(
                    """
                    INSERT INTO products
                    (id,title,url,category,brand,price,sku_info,specs_json,selling_points,shipping_info,after_sale_info,faq_json,raw_json,source_image_path,confidence,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        product_id, title, url, str(data.get("category", "")), str(data.get("brand", "")), str(data.get("price", "")),
                        json.dumps(sku, ensure_ascii=False) if not isinstance(sku, str) else sku,
                        json.dumps(specs, ensure_ascii=False), _join_text(data.get("selling_points")),
                        _join_text(data.get("shipping_info")), _join_text(data.get("after_sale_info")),
                        json.dumps(faq, ensure_ascii=False), json.dumps(data, ensure_ascii=False), source_image_path,
                        float(data.get("confidence") or 0), ts, ts,
                    ),
                )
            self._insert_faqs(conn, product_id, faq)
            row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            return self.row_to_dict(row) or {}

    def _insert_faqs(self, conn: sqlite3.Connection, product_id: str, faq: Any) -> None:
        if isinstance(faq, str):
            try:
                faq = json.loads(faq)
            except Exception:
                faq = []
        if not isinstance(faq, list):
            return
        for item in faq:
            q = str((item or {}).get("question") or (item or {}).get("q") or "").strip() if isinstance(item, dict) else str(item).strip()
            a = str((item or {}).get("answer") or (item or {}).get("a") or "").strip() if isinstance(item, dict) else "请根据商品资料确认后回复。"
            if not q or not a:
                continue
            exists = conn.execute("SELECT id FROM qa_pairs WHERE product_id=? AND question=? LIMIT 1", (product_id, q)).fetchone()
            if exists:
                continue
            ts = now_iso()
            conn.execute(
                "INSERT INTO qa_pairs (id,product_id,question,answer,source,quality_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id(), product_id, q, a, "product_page_ai", 0.7, ts, ts),
            )

    def list_products(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM products ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return self.rows_to_dicts(rows)

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self.row_to_dict(conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())

    def find_product_by_hint(self, hint: str) -> dict[str, Any] | None:
        hint = (hint or "").strip()
        if not hint:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE title LIKE ? OR url LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"%{hint[:30]}%", f"%{hint}%"),
            ).fetchone()
            return self.row_to_dict(row)

    def save_conversation_and_messages(self, data: dict[str, Any], source_image_path: str = "") -> dict[str, Any]:
        buyer_name = str(data.get("buyer_name") or "").strip()
        window_title = str(data.get("window_title") or "").strip()
        product_hint = ""
        product_info = data.get("product_hint") or {}
        if isinstance(product_info, dict):
            product_hint = str(product_info.get("title") or product_info.get("url") or "").strip()
        elif isinstance(product_info, str):
            product_hint = product_info.strip()
        product = self.find_product_by_hint(product_hint)
        product_id = product["id"] if product else ""
        conv_key = buyer_name or window_title or "current"
        ts = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE buyer_name=? OR window_title=? ORDER BY updated_at DESC LIMIT 1",
                (buyer_name, window_title),
            ).fetchone()
            if row:
                conversation_id = row["id"]
                conn.execute(
                    "UPDATE conversations SET buyer_name=?,window_title=?,product_id=?,product_title_hint=?,updated_at=? WHERE id=?",
                    (buyer_name, window_title, product_id, product_hint, ts, conversation_id),
                )
            else:
                conversation_id = new_id()
                conn.execute(
                    "INSERT INTO conversations (id,buyer_name,window_title,product_id,product_title_hint,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (conversation_id, conv_key, window_title, product_id, product_hint, ts, ts),
                )
            recent_dialog = data.get("recent_dialog") or []
            if not isinstance(recent_dialog, list):
                recent_dialog = []
            if data.get("last_buyer_message"):
                recent_dialog.append({"role": "buyer", "text": data.get("last_buyer_message")})
            for item in recent_dialog[-30:]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "buyer").lower()
                content = str(item.get("text") or item.get("content") or "").strip()
                if not content:
                    continue
                msg_hash = f"{conversation_id}:{role}:{content[-100:]}"
                if conn.execute("SELECT id FROM messages WHERE message_hash=? LIMIT 1", (msg_hash,)).fetchone():
                    continue
                conn.execute(
                    "INSERT INTO messages (id,conversation_id,product_id,role,content,source,message_hash,raw_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (new_id(), conversation_id, product_id, role, content, f"chat_screenshot:{source_image_path}", msg_hash, json.dumps(item, ensure_ascii=False), ts),
                )
            conv = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            latest = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 20", (conversation_id,)).fetchall()
            return {"conversation": self.row_to_dict(conv), "messages": self.rows_to_dicts(latest)}

    def latest_buyer_message(self, conversation_id: str | None = None) -> dict[str, Any] | None:
        with self.connect() as conn:
            if conversation_id:
                row = conn.execute("SELECT * FROM messages WHERE conversation_id=? AND role='buyer' ORDER BY created_at DESC LIMIT 1", (conversation_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM messages WHERE role='buyer' ORDER BY created_at DESC LIMIT 1").fetchone()
            return self.row_to_dict(row)

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self.row_to_dict(conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone())

    def get_recent_messages(self, conversation_id: str, limit: int = 12) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?", (conversation_id, limit)).fetchall()
            return list(reversed(self.rows_to_dicts(rows)))

    def search_qa(self, query: str, product_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        terms = [t.strip() for t in query.replace("？", " ").replace("?", " ").split() if t.strip()]
        where, params = [], []
        if product_id:
            where.append("product_id=?")
            params.append(product_id)
        if terms:
            clauses = []
            for term in terms[:5]:
                clauses.append("(question LIKE ? OR answer LIKE ?)")
                params.extend([f"%{term}%", f"%{term}%"])
            where.append("(" + " OR ".join(clauses) + ")")
        sql = "SELECT * FROM qa_pairs" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY quality_score DESC,updated_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return self.rows_to_dicts(conn.execute(sql, params).fetchall())

    def save_reply(self, data: dict[str, Any]) -> dict[str, Any]:
        ts, reply_id = now_iso(), new_id()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO replies (id,conversation_id,product_id,buyer_message,answer,confidence,needs_human,should_auto_send,reason,raw_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (reply_id, data.get("conversation_id", ""), data.get("product_id", ""), data.get("buyer_message", ""), data.get("answer", ""), float(data.get("confidence") or 0), 1 if data.get("needs_human") else 0, 1 if data.get("should_auto_send") else 0, data.get("reason", ""), json.dumps(data, ensure_ascii=False), ts),
            )
            conn.execute(
                "INSERT INTO messages (id,conversation_id,product_id,role,content,source,message_hash,raw_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id(), data.get("conversation_id", ""), data.get("product_id", ""), "ai", data.get("answer", ""), "ai_reply", f"{reply_id}:ai", json.dumps(data, ensure_ascii=False), ts),
            )
            return self.row_to_dict(conn.execute("SELECT * FROM replies WHERE id=?", (reply_id,)).fetchone()) or {}

    def save_feedback(self, reply_id: str, final_answer: str, note: str = "") -> dict[str, Any]:
        ts = now_iso()
        with self.connect() as conn:
            reply = conn.execute("SELECT * FROM replies WHERE id=?", (reply_id,)).fetchone()
            if not reply:
                raise ValueError("reply_id 不存在")
            fb_id = new_id()
            conn.execute("INSERT INTO feedback (id,reply_id,product_id,original_answer,final_answer,note,created_at) VALUES (?,?,?,?,?,?,?)", (fb_id, reply_id, reply["product_id"], reply["answer"], final_answer, note, ts))
            conn.execute("INSERT INTO qa_pairs (id,product_id,question,answer,source,quality_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", (new_id(), reply["product_id"], reply["buyer_message"] or "用户追问", final_answer, "human_feedback", 0.95, ts, ts))
            return self.row_to_dict(conn.execute("SELECT * FROM feedback WHERE id=?", (fb_id,)).fetchone()) or {}

    def insert_qa_pairs_from_history(self, pairs: Any, source: str = "history_screenshot") -> dict[str, Any]:
        if not isinstance(pairs, list):
            return {"created": 0, "skipped": 0, "items": []}
        created, skipped, items, ts = 0, 0, [], now_iso()
        with self.connect() as conn:
            for item in pairs:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                q = str(item.get("question") or item.get("q") or "").strip()
                a = str(item.get("answer") or item.get("a") or "").strip()
                if not q or not a:
                    skipped += 1
                    continue
                product_hint = str(item.get("product_hint") or "").strip()
                product = self.find_product_by_hint(product_hint) if product_hint else None
                product_id = product["id"] if product else ""
                if conn.execute("SELECT id FROM qa_pairs WHERE question=? AND answer=? LIMIT 1", (q, a)).fetchone():
                    skipped += 1
                    continue
                qa_id = new_id()
                quality = float(item.get("confidence") or 0.65)
                conn.execute("INSERT INTO qa_pairs (id,product_id,question,answer,source,quality_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", (qa_id, product_id, q, a, source, quality, ts, ts))
                created += 1
                items.append({"id": qa_id, "product_id": product_id, "question": q, "answer": a, "quality_score": quality})
        return {"created": created, "skipped": skipped, "items": items}


db = Database()

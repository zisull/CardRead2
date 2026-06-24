"""数据库存储模块

使用 SQLite 存储书籍、书签、阅读进度、便签等业务数据。
基础配置（设置项）仍使用 TOML 存储。
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from loguru import logger


class DbStore:
    """数据库存储管理器

    统一管理书籍、书签、阅读进度、便签的数据库读写。
    使用 threading.RLock 保护共享数据，支持多线程并发访问。

    Attributes:
        db_path: 数据库文件路径
    """

    def __init__(self, db_path: str):
        """初始化数据库存储

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        with self._lock:
            conn = self._get_conn()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS books (
                    name TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    original_encoding TEXT DEFAULT 'utf-8',
                    total_chapters INTEGER DEFAULT 0,
                    file_size INTEGER DEFAULT 0,
                    word_count INTEGER DEFAULT 0,
                    added_time TEXT,
                    last_modified TEXT,
                    current_encoding TEXT,
                    display_name TEXT
                );

                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_name TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    description TEXT DEFAULT '',
                    time TEXT,
                    FOREIGN KEY (book_name) REFERENCES books(name) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_bookmarks_book ON bookmarks(book_name);

                CREATE TABLE IF NOT EXISTS reading_progress (
                    book_name TEXT PRIMARY KEY,
                    chapter INTEGER DEFAULT 0,
                    scroll_percent INTEGER DEFAULT 0,
                    last_read TEXT,
                    FOREIGN KEY (book_name) REFERENCES books(name) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    color TEXT DEFAULT '',
                    `group` TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
            """)
            conn.commit()

    def close(self) -> None:
        """关闭当前线程的数据库连接"""
        with self._lock:
            if hasattr(self._local, 'conn') and self._local.conn:
                try:
                    self._local.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                except Exception:
                    pass
                self._local.conn.close()
                self._local.conn = None

    # ==================== 书籍操作 ====================

    def get_books(self) -> List[Dict[str, Any]]:
        """获取所有书籍"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute("SELECT * FROM books ORDER BY added_time DESC").fetchall()
            return [dict(row) for row in rows]

    def get_book(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定书籍"""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute("SELECT * FROM books WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def add_book(self, book_data: Dict[str, Any]) -> bool:
        """添加书籍

        Args:
            book_data: 书籍数据字典，必须包含 name 字段
        """
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("""
                    INSERT OR REPLACE INTO books 
                    (name, file_path, original_encoding, total_chapters, file_size, 
                     word_count, added_time, last_modified, current_encoding, display_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    book_data.get('name'),
                    book_data.get('file_path', ''),
                    book_data.get('original_encoding', 'utf-8'),
                    book_data.get('total_chapters', 0),
                    book_data.get('file_size', 0),
                    book_data.get('word_count', 0),
                    book_data.get('added_time', datetime.now().isoformat()),
                    book_data.get('last_modified'),
                    book_data.get('current_encoding'),
                    book_data.get('display_name')
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"添加书籍失败: {e}")
                return False

    def update_book(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新书籍信息

        Args:
            name: 书籍名称
            updates: 要更新的字段字典
        """
        with self._lock:
            try:
                allowed_fields = {'file_path', 'original_encoding', 'total_chapters', 
                                  'file_size', 'word_count', 'added_time', 'last_modified',
                                  'current_encoding', 'display_name'}
                filtered = {k: v for k, v in updates.items() if k in allowed_fields}
                if not filtered:
                    return False
                
                set_clause = ', '.join(f"{k} = ?" for k in filtered)
                values = list(filtered.values()) + [name]
                
                conn = self._get_conn()
                conn.execute(f"UPDATE books SET {set_clause} WHERE name = ?", values)
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"更新书籍失败: {e}")
                return False

    def remove_book(self, name: str) -> bool:
        """移除书籍及其相关数据"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM books WHERE name = ?", (name,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"移除书籍失败: {e}")
                return False

    def has_book(self, name: str) -> bool:
        """检查书籍是否存在"""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute("SELECT 1 FROM books WHERE name = ?", (name,)).fetchone()
            return row is not None

    # ==================== 书签操作 ====================

    def get_bookmarks(self, book_name: str) -> List[Dict[str, Any]]:
        """获取书籍的所有书签"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE book_name = ? ORDER BY chapter, position",
                (book_name,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_bookmarks(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有书签，按书籍分组"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM bookmarks ORDER BY book_name, chapter, position"
            ).fetchall()
            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                row_dict = dict(row)
                book_name = row_dict.pop('book_name')
                if book_name not in result:
                    result[book_name] = []
                result[book_name].append(row_dict)
            return result

    def add_bookmark(self, book_name: str, bookmark_data: Dict[str, Any]) -> bool:
        """添加书签"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("""
                    INSERT INTO bookmarks (book_name, chapter, position, description, time)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    book_name,
                    bookmark_data.get('chapter', 0),
                    bookmark_data.get('position', 0),
                    bookmark_data.get('description', ''),
                    bookmark_data.get('time', datetime.now().isoformat())
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"添加书签失败: {e}")
                return False

    def update_bookmark(self, book_name: str, index: int, description: str) -> bool:
        """更新书签描述"""
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute("""
                    SELECT id FROM bookmarks 
                    WHERE book_name = ? 
                    ORDER BY chapter, position 
                    LIMIT 1 OFFSET ?
                """, (book_name, index)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE bookmarks SET description = ? WHERE id = ?",
                        (description, row['id'])
                    )
                    conn.commit()
                    return True
                return False
            except Exception as e:
                logger.error(f"更新书签失败: {e}")
                return False

    def remove_bookmark(self, book_name: str, index: int) -> bool:
        """移除书签"""
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute("""
                    SELECT id FROM bookmarks 
                    WHERE book_name = ? 
                    ORDER BY chapter, position 
                    LIMIT 1 OFFSET ?
                """, (book_name, index)).fetchone()
                if row:
                    conn.execute("DELETE FROM bookmarks WHERE id = ?", (row['id'],))
                    conn.commit()
                    return True
                return False
            except Exception as e:
                logger.error(f"移除书签失败: {e}")
                return False

    def remove_book_bookmarks(self, book_name: str) -> bool:
        """移除书籍的所有书签"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM bookmarks WHERE book_name = ?", (book_name,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"移除书籍书签失败: {e}")
                return False

    def count_bookmarks(self, book_name: Optional[str] = None) -> int:
        """统计书签数量"""
        with self._lock:
            conn = self._get_conn()
            if book_name:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM bookmarks WHERE book_name = ?",
                    (book_name,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as cnt FROM bookmarks").fetchone()
            return row['cnt'] if row else 0

    def get_bookmark_book_names(self) -> List[str]:
        """获取有书签的书籍名称"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT DISTINCT book_name FROM bookmarks"
            ).fetchall()
            return [row['book_name'] for row in rows]

    # ==================== 阅读进度操作 ====================

    def get_progress(self, book_name: str) -> Optional[Dict[str, Any]]:
        """获取书籍的阅读进度"""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM reading_progress WHERE book_name = ?",
                (book_name,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_progress(self) -> Dict[str, Dict[str, Any]]:
        """获取所有阅读进度"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute("SELECT * FROM reading_progress").fetchall()
            return {row['book_name']: dict(row) for row in rows}

    def update_progress(self, book_name: str, chapter: int, scroll_percent: int) -> bool:
        """更新阅读进度"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("""
                    INSERT OR REPLACE INTO reading_progress 
                    (book_name, chapter, scroll_percent, last_read)
                    VALUES (?, ?, ?, ?)
                """, (book_name, chapter, scroll_percent, datetime.now().isoformat()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"更新阅读进度失败: {e}")
                return False

    def remove_progress(self, book_name: str) -> bool:
        """移除阅读进度"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "DELETE FROM reading_progress WHERE book_name = ?",
                    (book_name,)
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"移除阅读进度失败: {e}")
                return False

    def get_last_read_book(self) -> Optional[str]:
        """获取最近阅读的书籍"""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute("""
                SELECT book_name FROM reading_progress 
                ORDER BY last_read DESC LIMIT 1
            """).fetchone()
            return row['book_name'] if row else None

    # ==================== 便签操作 ====================

    def get_notes(self) -> List[Dict[str, Any]]:
        """获取所有便签"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取指定便签"""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            return dict(row) if row else None

    def add_note(self, note_data: Dict[str, Any]) -> bool:
        """添加便签"""
        with self._lock:
            try:
                conn = self._get_conn()
                now = datetime.now().isoformat(timespec='seconds')
                conn.execute("""
                    INSERT INTO notes (id, title, content, color, `group`, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    note_data.get('id'),
                    note_data.get('title', ''),
                    note_data.get('content', ''),
                    note_data.get('color', ''),
                    note_data.get('group', ''),
                    note_data.get('created_at', now),
                    note_data.get('updated_at', now)
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"添加便签失败: {e}")
                return False

    def update_note(self, note_id: str, updates: Dict[str, Any]) -> bool:
        """更新便签"""
        with self._lock:
            try:
                allowed_fields = {'title', 'content', 'color', 'group', 'updated_at'}
                filtered = {k: v for k, v in updates.items() if k in allowed_fields}
                if not filtered:
                    return False
                
                if 'updated_at' not in filtered:
                    filtered['updated_at'] = datetime.now().isoformat(timespec='seconds')
                
                set_parts = []
                values = []
                for k, v in filtered.items():
                    if k == 'group':
                        set_parts.append("`group` = ?")
                    else:
                        set_parts.append(f"{k} = ?")
                    values.append(v)
                
                set_clause = ', '.join(set_parts)
                values.append(note_id)
                
                conn = self._get_conn()
                conn.execute(f"UPDATE notes SET {set_clause} WHERE id = ?", values)
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"更新便签失败: {e}")
                return False

    def remove_note(self, note_id: str) -> bool:
        """移除便签"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"移除便签失败: {e}")
                return False

    def remove_notes(self, note_ids: List[str]) -> int:
        """批量移除便签

        Returns:
            成功移除的数量
        """
        with self._lock:
            try:
                conn = self._get_conn()
                placeholders = ','.join('?' * len(note_ids))
                cursor = conn.execute(
                    f"DELETE FROM notes WHERE id IN ({placeholders})",
                    note_ids
                )
                conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"批量移除便签失败: {e}")
                return 0

    def clear_notes(self) -> bool:
        """清空所有便签"""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM notes")
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"清空便签失败: {e}")
                return False

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        """搜索便签"""
        with self._lock:
            conn = self._get_conn()
            pattern = f"%{query}%"
            rows = conn.execute("""
                SELECT * FROM notes 
                WHERE title LIKE ? OR content LIKE ? OR `group` LIKE ?
                ORDER BY updated_at DESC
            """, (pattern, pattern, pattern)).fetchall()
            return [dict(row) for row in rows]

    # ==================== 数据迁移 ====================

    def migrate_from_toml(self, toml_data: Dict[str, Any]) -> bool:
        """从 TOML 数据迁移到数据库

        Args:
            toml_data: TOML 配置文件的数据字典
        """
        with self._lock:
            try:
                conn = self._get_conn()
                
                # 迁移书籍数据
                bookshelf = toml_data.get('bookshelf', {})
                books = bookshelf.get('books', {})
                for name, book_data in books.items():
                    book_data['name'] = name
                    self.add_book(book_data)
                
                # 迁移书签数据
                bookmarks = toml_data.get('bookmarks', {})
                for book_name, bm_list in bookmarks.items():
                    for bm_data in bm_list:
                        self.add_bookmark(book_name, bm_data)
                
                # 迁移阅读进度
                progress = toml_data.get('reading_progress', {})
                for book_name, prog_data in progress.items():
                    self.update_progress(
                        book_name,
                        prog_data.get('chapter', 0),
                        prog_data.get('scroll_percent', prog_data.get('position', 0))
                    )
                
                # 迁移便签
                notes = toml_data.get('notes', [])
                if isinstance(notes, list):
                    for note_data in notes:
                        if isinstance(note_data, dict) and note_data.get('id'):
                            self.add_note(note_data)
                
                logger.info(f"数据迁移完成: {len(books)} 本书, {len(notes)} 条便签")
                return True
            except Exception as e:
                logger.error(f"数据迁移失败: {e}")
                return False

    def has_data(self) -> bool:
        """检查数据库是否有数据"""
        with self._lock:
            conn = self._get_conn()
            book_count = conn.execute("SELECT COUNT(*) as cnt FROM books").fetchone()['cnt']
            return book_count > 0

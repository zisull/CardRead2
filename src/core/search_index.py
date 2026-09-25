"""全文搜索索引模块

使用 SQLite FTS5 实现高效的全文搜索。
支持中英文混合搜索，提供增量索引更新。
线程安全：支持跨线程使用。
"""
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.config import FTS5_MAX_RESULTS_DEFAULT

# 索引内容里汉字之间插入空格分隔符，让每个汉字成为独立 token；
# FTS5 的 unicode61 会把一整串中文当作一个词，「杨过」这类词永远匹配不到
_CJK = '\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff'
_CJK_BOUNDARY_RE = re.compile(f'(?<=[{_CJK}])(?=[{_CJK}])')
_CJK_SPACED_RE = re.compile(f'(?<=[{_CJK}]) (?=[{_CJK}])')


def _split_cjk(text: str) -> str:
    """索引前处理：汉字之间插入分隔符"""
    return _CJK_BOUNDARY_RE.sub(' ', text)


def _join_cjk(text: str) -> str:
    """结果后处理：还原 _split_cjk 插入的分隔符"""
    return _CJK_SPACED_RE.sub('', text)


class SearchIndex:
    """全文搜索索引
    
    使用 SQLite FTS5 实现高效的全文搜索。
    
    特性:
    - 支持中英文混合搜索（汉字按单字建 token，短语查询等价于子串匹配）
    - 增量索引更新
    - 高效的全文检索
    - 线程安全：支持跨线程使用
    
    Attributes:
        db_path: 数据库文件路径
    """

    # 分词方案版本；变更后旧索引会给出错误结果，启动时整体废弃并按需重建
    INDEX_VERSION = 'cjk-split-v1'
    
    def __init__(self, db_path: str):
        """初始化搜索索引
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        try:
            # 使用 check_same_thread=False 允许跨线程使用
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            
            # 创建 FTS5 虚拟表
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS book_content USING fts5(
                    book_name,
                    chapter_index,
                    content,
                    tokenize='unicode61'
                )
            """)
            
            # 创建元数据表
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS index_metadata (
                    book_name TEXT PRIMARY KEY,
                    chapter_count INTEGER,
                    indexed_at REAL
                )
            """)

            # 分词版本变更（例如从不支持的整词切分改为逐字切分）会让旧索引静默给出错误结果，
            # 这里直接废弃旧索引；书籍下次打开时会自动重建
            self._conn.execute("CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT)")
            row = self._conn.execute(
                "SELECT value FROM index_meta WHERE key = 'index_version'"
            ).fetchone()
            if not row or row[0] != self.INDEX_VERSION:
                self._conn.execute("DELETE FROM book_content")
                self._conn.execute("DELETE FROM index_metadata")
                self._conn.execute(
                    "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('index_version', ?)",
                    (self.INDEX_VERSION,)
                )
                logger.info(f"搜索索引分词版本已升级，旧索引作废: {self.db_path}")

            self._conn.commit()
            logger.debug(f"搜索索引初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"搜索索引初始化失败: {e}")
            self._conn = None
    
    def close(self):
        """关闭数据库连接
        
        使用 self._lock 确保与 index_book/search 等持锁方法互斥，
        避免 app 退出时索引线程仍在使用 _conn 时被关闭导致 AttributeError/WAL 损坏。
        """
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
    
    def is_indexed(self, book_name: str) -> bool:
        """检查书籍是否已索引
        
        Args:
            book_name: 书籍名称
            
        Returns:
            是否已索引
        """
        if not self._conn:
            return False
        
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT 1 FROM index_metadata WHERE book_name = ?",
                    (book_name,)
                )
                return cursor.fetchone() is not None
        except Exception:
            return False
    
    def get_indexed_chapter_count(self, book_name: str) -> int:
        """获取已索引的章节数量
        
        Args:
            book_name: 书籍名称
            
        Returns:
            已索引的章节数量
        """
        if not self._conn:
            return 0
        
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT chapter_count FROM index_metadata WHERE book_name = ?",
                    (book_name,)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
    
    def index_book(self, book_name: str, chapters: List[str], force: bool = False) -> bool:
        """为书籍创建索引
        
        Args:
            book_name: 书籍名称
            chapters: 章节内容列表
            force: 是否强制重建索引
            
        Returns:
            是否成功
        """
        if not self._conn:
            return False
        
        try:
            with self._lock:
                # 检查是否需要更新
                if not force:
                    cursor = self._conn.execute(
                        "SELECT chapter_count FROM index_metadata WHERE book_name = ?",
                        (book_name,)
                    )
                    row = cursor.fetchone()
                    if row and row[0] == len(chapters):
                        logger.debug(f"索引已是最新: {book_name}")
                        return True
                
                start_time = time.time()
                
                try:
                    # 删除旧索引
                    self._conn.execute(
                        "DELETE FROM book_content WHERE book_name = ?",
                        (book_name,)
                    )
                    self._conn.execute(
                        "DELETE FROM index_metadata WHERE book_name = ?",
                        (book_name,)
                    )
                    
                    # 插入新索引（批量 executemany，见 2.5 优化）
                    rows = [(book_name, i, _split_cjk(c)) for i, c in enumerate(chapters) if c]
                    if rows:
                        self._conn.executemany(
                            "INSERT INTO book_content (book_name, chapter_index, content) VALUES (?, ?, ?)",
                            rows
                        )
                    
                    # 更新元数据
                    self._conn.execute(
                        "INSERT OR REPLACE INTO index_metadata (book_name, chapter_count, indexed_at) VALUES (?, ?, ?)",
                        (book_name, len(chapters), time.time())
                    )
                    
                    self._conn.commit()
                except Exception:
                    # 事务失败必须回滚，否则 DELETE 已执行未提交，事务保持 OPEN
                    # 后续 commit 会提交半量数据，VACUUM 也会报 "cannot VACUUM from within a transaction"
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    raise
            
            elapsed = time.time() - start_time
            logger.info(f"索引创建完成: {book_name}, {len(chapters)} 章节, 耗时 {elapsed:.2f}s")
            return True
        
        except Exception as e:
            logger.error(f"索引创建失败: {book_name}: {e}")
            return False
    
    def search(self, query: str, book_name: str = None, max_results: int = FTS5_MAX_RESULTS_DEFAULT) -> List[Dict]:
        """搜索内容
        
        Args:
            query: 搜索关键词
            book_name: 书籍名称（可选，为 None 时搜索所有书籍）
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        if not self._conn or not query or not query.strip():
            return []
        
        try:
            start_time = time.time()

            # 转义为 FTS5 短语查询，避免特殊字符（"*"/"/AND"/OR 等）触发语法错误；
            # 查询与索引同样做逐字切分，短语的相邻 token 即等价于子串匹配
            fts5_query = '"' + _split_cjk(query).replace('"', '""').replace('\n', ' ').strip() + '"'

            with self._lock:
                # 构建查询
                if book_name:
                    sql = """
                        SELECT book_name, chapter_index, 
                               snippet(book_content, 2, '<<<', '>>>', '...', 32) as snippet,
                               rank
                        FROM book_content
                        WHERE book_name = ? AND content MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """
                    cursor = self._conn.execute(sql, (book_name, fts5_query, max_results))
                else:
                    sql = """
                        SELECT book_name, chapter_index, 
                               snippet(book_content, 2, '<<<', '>>>', '...', 32) as snippet,
                               rank
                        FROM book_content
                        WHERE content MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """
                    cursor = self._conn.execute(sql, (fts5_query, max_results))
                
                results = []
                for row in cursor.fetchall():
                    result_book_name, chapter_index, snippet, rank = row
                    results.append({
                        'book_name': result_book_name,
                        'chapter': chapter_index,
                        'context': _join_cjk(snippet.replace('<<<', '').replace('>>>', '')),
                    })
            
            elapsed = time.time() - start_time
            logger.debug(f"搜索完成: '{query}', {len(results)} 结果, 耗时 {elapsed:.3f}s")
            
            return results
        
        except Exception as e:
            logger.error(f"搜索失败: '{query}': {e}")
            return []
    
    def count(self, query: str, book_name: str = None) -> int:
        """统计关键词的命中条数（用于结果被 max_results 截断时给出真实总数）"""
        if not self._conn or not query or not query.strip():
            return 0
        try:
            fts5_query = '"' + _split_cjk(query).replace('"', '""').replace('\n', ' ').strip() + '"'
            with self._lock:
                if book_name:
                    row = self._conn.execute(
                        "SELECT count(*) FROM book_content WHERE book_name = ? AND content MATCH ?",
                        (book_name, fts5_query)
                    ).fetchone()
                else:
                    row = self._conn.execute(
                        "SELECT count(*) FROM book_content WHERE content MATCH ?",
                        (fts5_query,)
                    ).fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            logger.error(f"统计匹配数失败: '{query}': {e}")
            return 0

    def remove_book(self, book_name: str) -> bool:
        """删除书籍索引
        
        Args:
            book_name: 书籍名称
            
        Returns:
            是否成功
        """
        if not self._conn:
            return False
        
        try:
            with self._lock:
                try:
                    self._conn.execute(
                        "DELETE FROM book_content WHERE book_name = ?",
                        (book_name,)
                    )
                    self._conn.execute(
                        "DELETE FROM index_metadata WHERE book_name = ?",
                        (book_name,)
                    )
                    self._conn.commit()
                except Exception:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    raise
            logger.debug(f"索引已删除: {book_name}")
            return True
        except Exception as e:
            logger.error(f"索引删除失败: {book_name}: {e}")
            return False

    def clear_all(self) -> bool:
        """清空所有书籍索引"""
        if not self._conn:
            return False
        try:
            with self._lock:
                try:
                    self._conn.execute("DELETE FROM book_content")
                    self._conn.execute("DELETE FROM index_metadata")
                    self._conn.commit()
                except Exception:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    raise
            logger.debug("所有索引已清空")
            return True
        except Exception as e:
            logger.error(f"清空索引失败: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """获取索引统计信息
        
        Returns:
            统计信息字典
        """
        if not self._conn:
            return {'books': 0, 'chapters': 0, 'db_size': 0}
        
        try:
            with self._lock:
                cursor = self._conn.execute("SELECT COUNT(*) FROM index_metadata")
                book_count = cursor.fetchone()[0]
                
                cursor = self._conn.execute("SELECT SUM(chapter_count) FROM index_metadata")
                chapter_count = cursor.fetchone()[0] or 0
            
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            return {
                'books': book_count,
                'chapters': chapter_count,
                'db_size': db_size,
            }
        except Exception as e:
            logger.error(f"获取索引统计失败: {e}")
            return {'books': 0, 'chapters': 0, 'db_size': 0}
    
    def vacuum(self):
        """压缩数据库"""
        if not self._conn:
            return
        
        try:
            with self._lock:
                self._conn.execute("VACUUM")
            logger.debug("索引数据库已压缩")
        except Exception as e:
            logger.error(f"索引数据库压缩失败: {e}")

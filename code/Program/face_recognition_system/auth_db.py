"""用户、机器人与绑定关系的 SQLite 存储"""
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

_lock = threading.Lock()


def _db_path(base_dir: str) -> str:
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'auth.db')


def get_connection(base_dir: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(base_dir), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db(base_dir: str) -> None:
    with _lock:
        conn = get_connection(base_dir)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                );

                CREATE TABLE IF NOT EXISTS robots (
                    robot_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                );

                CREATE TABLE IF NOT EXISTS user_robots (
                    user_id INTEGER NOT NULL,
                    robot_id TEXT NOT NULL,
                    bound_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                    PRIMARY KEY (user_id, robot_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (robot_id) REFERENCES robots(robot_id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row else {}


class AuthDatabase:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        init_db(base_dir)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            row = conn.execute(
                'SELECT * FROM users WHERE id = ?', (user_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            row = conn.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def count_users(self) -> int:
        conn = get_connection(self.base_dir)
        try:
            return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        finally:
            conn.close()

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = 'user',
    ) -> Dict[str, Any]:
        with _lock:
            conn = get_connection(self.base_dir)
            try:
                cur = conn.execute(
                    'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                    (username, password_hash, role),
                )
                conn.commit()
                return self.get_user_by_id(cur.lastrowid)
            finally:
                conn.close()

    def list_users(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            rows = conn.execute(
                'SELECT id, username, role, is_active, created_at FROM users ORDER BY id'
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def set_user_active(self, user_id: int, is_active: bool) -> bool:
        conn = get_connection(self.base_dir)
        try:
            cur = conn.execute(
                'UPDATE users SET is_active = ? WHERE id = ?',
                (1 if is_active else 0, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_password(self, user_id: int, password_hash: str) -> bool:
        conn = get_connection(self.base_dir)
        try:
            cur = conn.execute(
                'UPDATE users SET password_hash = ? WHERE id = ?',
                (password_hash, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_user(
        self,
        user_id: int,
        username: str,
        role: str,
        is_active: bool,
        password_hash: Optional[str] = None,
    ) -> bool:
        conn = get_connection(self.base_dir)
        try:
            if password_hash:
                cur = conn.execute(
                    """
                    UPDATE users
                    SET username = ?, role = ?, is_active = ?, password_hash = ?
                    WHERE id = ?
                    """,
                    (username.strip(), role, 1 if is_active else 0, password_hash, user_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE users
                    SET username = ?, role = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (username.strip(), role, 1 if is_active else 0, user_id),
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def create_robot(self, robot_id: str, display_name: str, notes: str = '') -> Dict[str, Any]:
        with _lock:
            conn = get_connection(self.base_dir)
            try:
                conn.execute(
                    'INSERT INTO robots (robot_id, display_name, notes) VALUES (?, ?, ?)',
                    (robot_id.strip(), display_name.strip(), notes.strip()),
                )
                conn.commit()
                return self.get_robot(robot_id.strip())
            finally:
                conn.close()

    def get_robot(self, robot_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            row = conn.execute(
                'SELECT * FROM robots WHERE robot_id = ?', (robot_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_robots(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            rows = conn.execute(
                'SELECT * FROM robots ORDER BY created_at DESC'
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def delete_robot(self, robot_id: str) -> bool:
        conn = get_connection(self.base_dir)
        try:
            cur = conn.execute('DELETE FROM robots WHERE robot_id = ?', (robot_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_robot(self, robot_id: str, display_name: str, notes: str = '') -> bool:
        conn = get_connection(self.base_dir)
        try:
            cur = conn.execute(
                'UPDATE robots SET display_name = ?, notes = ? WHERE robot_id = ?',
                (display_name.strip(), notes.strip(), robot_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def bind_robot(self, user_id: int, robot_id: str) -> bool:
        if not self.get_robot(robot_id):
            return False
        conn = get_connection(self.base_dir)
        try:
            conn.execute(
                'INSERT OR IGNORE INTO user_robots (user_id, robot_id) VALUES (?, ?)',
                (user_id, robot_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def unbind_robot(self, user_id: int, robot_id: str) -> bool:
        conn = get_connection(self.base_dir)
        try:
            cur = conn.execute(
                'DELETE FROM user_robots WHERE user_id = ? AND robot_id = ?',
                (user_id, robot_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_binding(
        self,
        old_user_id: int,
        old_robot_id: str,
        new_user_id: int,
        new_robot_id: str,
    ) -> bool:
        if not self.get_user_by_id(new_user_id) or not self.get_robot(new_robot_id):
            return False

        with _lock:
            conn = get_connection(self.base_dir)
            try:
                existing = conn.execute(
                    'SELECT bound_at FROM user_robots WHERE user_id = ? AND robot_id = ?',
                    (old_user_id, old_robot_id),
                ).fetchone()
                if not existing:
                    return False

                conn.execute(
                    'DELETE FROM user_robots WHERE user_id = ? AND robot_id = ?',
                    (old_user_id, old_robot_id),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_robots (user_id, robot_id, bound_at)
                    VALUES (?, ?, ?)
                    """,
                    (new_user_id, new_robot_id, existing['bound_at']),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def list_robots_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            rows = conn.execute(
                """
                SELECT r.robot_id, r.display_name, r.notes, ur.bound_at
                FROM user_robots ur
                JOIN robots r ON r.robot_id = ur.robot_id
                WHERE ur.user_id = ?
                ORDER BY r.display_name
                """,
                (user_id,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_bindings(self) -> List[Dict[str, Any]]:
        conn = get_connection(self.base_dir)
        try:
            rows = conn.execute(
                """
                SELECT ur.user_id, u.username, ur.robot_id, r.display_name, ur.bound_at
                FROM user_robots ur
                JOIN users u ON u.id = ur.user_id
                JOIN robots r ON r.robot_id = ur.robot_id
                ORDER BY ur.bound_at DESC
                """
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def user_owns_robot(self, user_id: int, robot_id: str) -> bool:
        conn = get_connection(self.base_dir)
        try:
            row = conn.execute(
                'SELECT 1 FROM user_robots WHERE user_id = ? AND robot_id = ?',
                (user_id, robot_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

"""
database.py - SQLite database operations for 词语闯关平台 + 阅读理解侦探闯关

设计原则：
- 用 WAL 模式提高并发性能
- 短事务，避免长时间锁表
- 软删除，避免学生数据丢失
- 用 (class_name + student_id) 作为学生主键，不依赖姓名

v2 新增：阅读理解侦探闯关相关功能(reading_lessons + detective_completions)
"""

import sqlite3
import json
import hashlib
import os
from datetime import datetime
from contextlib import contextmanager

# 数据库文件路径 - Streamlit Cloud 持久化目录
DB_PATH = os.environ.get("CILANG_DB_PATH", "cilang.db")


@contextmanager
def get_conn():
    """获取数据库连接（自动关闭）"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表结构"""
    with get_conn() as conn:
        c = conn.cursor()

        # 老师表
        c.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 课文表（层级：年级 → 单元 → 第N课）
        c.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id INTEGER PRIMARY KEY AUTOINCREMENT,
                grade TEXT NOT NULL,
                unit TEXT NOT NULL,
                lesson_no TEXT NOT NULL,
                title TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (created_by) REFERENCES teachers(teacher_id)
            )
        """)

        # 题库表（JSON格式存储题目）
        c.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                lesson_id INTEGER PRIMARY KEY,
                questions_json TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                step_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by INTEGER,
                FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
                FOREIGN KEY (updated_by) REFERENCES teachers(teacher_id)
            )
        """)

        # 答题记录表
        c.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                teacher_id INTEGER,
                word TEXT NOT NULL,
                step_type TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                chosen_idx INTEGER,
                correct_idx INTEGER,
                chosen_content TEXT DEFAULT '',
                correct_content TEXT DEFAULT '',
                answered_at TEXT NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            )
        """)

        # 兼容旧数据库：如果表已存在但没新字段，添加新字段
        try:
            c.execute("ALTER TABLE attempts ADD COLUMN chosen_content TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE attempts ADD COLUMN correct_content TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        # 预习流程：词语课文关联到哪篇阅读理解课文（reading_lessons.id）。
        # NULL = 未关联，学生做完词语闯关不出现"继续做课文理解"按钮。
        try:
            c.execute("ALTER TABLE lessons ADD COLUMN linked_reading_id INTEGER")
        except sqlite3.OperationalError:
            pass

        # 学生会话总结表（一次完整闯关的总结）
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                teacher_id INTEGER,
                total_steps INTEGER NOT NULL,
                correct_steps INTEGER NOT NULL,
                stars_earned INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            )
        """)

        # 老师-班级映射
        c.execute("""
            CREATE TABLE IF NOT EXISTS teacher_classes (
                teacher_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                PRIMARY KEY (teacher_id, class_name),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            )
        """)

        # 创建索引加速查询
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_lesson ON attempts(lesson_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_class ON attempts(class_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_teacher ON attempts(teacher_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_teacher ON sessions(teacher_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lessons_grade ON lessons(grade, unit, lesson_no)")

    # 初始化阅读理解相关的表(v2 新增)
    init_reading_lessons_tables()


# ==================== 老师相关 ====================

def hash_password(password: str) -> str:
    """密码哈希 - 使用 PBKDF2"""
    salt = b"cilang_2026_salt_v1"
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000).hex()


def verify_password(password: str, hash_str: str) -> bool:
    return hash_password(password) == hash_str


def register_teacher(username: str, password: str, display_name: str) -> tuple[bool, str]:
    """老师注册。返回 (成功, 消息)"""
    username = username.strip()
    display_name = display_name.strip()
    if not username or not password or not display_name:
        return False, "用户名、密码、显示名称都不能为空"
    if len(password) < 6:
        return False, "密码至少6位"

    try:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT teacher_id FROM teachers WHERE username = ?", (username,))
            if c.fetchone():
                return False, "用户名已被注册"

            c.execute(
                "INSERT INTO teachers (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), display_name, datetime.now().isoformat())
            )
            return True, "注册成功"
    except Exception as e:
        return False, f"注册失败：{str(e)}"


def login_teacher(username: str, password: str) -> dict | None:
    """老师登录。返回 teacher 字典或 None"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT teacher_id, username, password_hash, display_name FROM teachers WHERE username = ? AND is_active = 1",
            (username.strip(),)
        )
        row = c.fetchone()
        if not row:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return dict(row)


def get_teacher_classes(teacher_id: int) -> list[str]:
    """获取老师负责的班级列表"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT class_name FROM teacher_classes WHERE teacher_id = ?", (teacher_id,))
        return [r["class_name"] for r in c.fetchall()]


def add_teacher_class(teacher_id: int, class_name: str) -> bool:
    class_name = class_name.strip()
    if not class_name:
        return False
    try:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO teacher_classes (teacher_id, class_name) VALUES (?, ?)",
                (teacher_id, class_name)
            )
            return True
    except Exception:
        return False


def remove_teacher_class(teacher_id: int, class_name: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM teacher_classes WHERE teacher_id = ? AND class_name = ?",
            (teacher_id, class_name)
        )


# ==================== 课文相关 ====================

def list_grades_units_lessons() -> dict:
    """返回完整的层级结构 {grade: {unit: [(lesson_id, lesson_no, title), ...]}}"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT lesson_id, grade, unit, lesson_no, title
            FROM lessons
            WHERE is_active = 1
            ORDER BY grade, unit, lesson_no
        """)
        rows = c.fetchall()
        result = {}
        for r in rows:
            result.setdefault(r["grade"], {}).setdefault(r["unit"], []).append(
                (r["lesson_id"], r["lesson_no"], r["title"])
            )
        return result


def create_lesson(grade: str, unit: str, lesson_no: str, title: str, teacher_id: int) -> int | None:
    """创建新课文。返回 lesson_id"""
    grade = grade.strip()
    unit = unit.strip()
    lesson_no = lesson_no.strip()
    title = title.strip()
    if not all([grade, unit, lesson_no, title]):
        return None
    try:
        with get_conn() as conn:
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute(
                """INSERT INTO lessons (grade, unit, lesson_no, title, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (grade, unit, lesson_no, title, teacher_id, now, now)
            )
            return c.lastrowid
    except Exception:
        return None


def update_lesson(lesson_id: int, title: str):
    """更新课文标题"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE lessons SET title = ?, updated_at = ? WHERE lesson_id = ?",
            (title.strip(), datetime.now().isoformat(), lesson_id)
        )


def delete_lesson(lesson_id: int):
    """软删除课文"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE lessons SET is_active = 0, updated_at = ? WHERE lesson_id = ?",
            (datetime.now().isoformat(), lesson_id)
        )


def get_lesson(lesson_id: int) -> dict | None:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT lesson_id, grade, unit, lesson_no, title, linked_reading_id FROM lessons WHERE lesson_id = ? AND is_active = 1",
            (lesson_id,)
        )
        row = c.fetchone()
        return dict(row) if row else None


def set_lesson_linked_reading(lesson_id: int, reading_lesson_id):
    """设置/清除词语课文关联的阅读理解课文。reading_lesson_id 传 None 表示解除关联。"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE lessons SET linked_reading_id = ?, updated_at = ? WHERE lesson_id = ?",
            (reading_lesson_id, datetime.now().isoformat(), lesson_id)
        )


def get_lesson_linked_reading(lesson_id: int):
    """取词语课文关联的阅读理解课文 id；未关联或关联的阅读课文已删除则返回 None。"""
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute(
            "SELECT linked_reading_id FROM lessons WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
        if not row or row["linked_reading_id"] is None:
            return None
        rid = row["linked_reading_id"]
        # 校验关联的阅读课文还在（老师可能删过），避免跳转到不存在的课文
        exists = c.execute(
            "SELECT 1 FROM reading_lessons WHERE id = ?", (rid,)
        ).fetchone()
        return rid if exists else None


# ==================== 题库相关 ====================

def save_questions(lesson_id: int, questions: list, teacher_id: int) -> tuple[bool, str]:
    """保存题库。questions 是符合规范的列表"""
    if not questions:
        return False, "题库不能为空"

    word_count = len(questions)
    step_count = 0
    for q in questions:
        difficulty = q.get("difficulty", "hard")
        step_count += 3 if difficulty == "hard" else 1

    try:
        with get_conn() as conn:
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute(
                """INSERT OR REPLACE INTO questions
                   (lesson_id, questions_json, word_count, step_count, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (lesson_id, json.dumps(questions, ensure_ascii=False), word_count, step_count, now, teacher_id)
            )
            c.execute(
                "UPDATE lessons SET updated_at = ? WHERE lesson_id = ?",
                (now, lesson_id)
            )
            return True, f"已保存 {word_count} 个词语，共 {step_count} 关"
    except Exception as e:
        return False, f"保存失败：{str(e)}"


def get_questions(lesson_id: int) -> list | None:
    """获取课文的题库"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT questions_json FROM questions WHERE lesson_id = ?", (lesson_id,))
        row = c.fetchone()
        if not row:
            return None
        try:
            return json.loads(row["questions_json"])
        except json.JSONDecodeError:
            return None


def get_questions_meta(lesson_id: int) -> dict | None:
    """获取题库元信息（不返回完整题库）"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT word_count, step_count, updated_at FROM questions WHERE lesson_id = ?",
            (lesson_id,)
        )
        row = c.fetchone()
        return dict(row) if row else None


# ==================== 答题数据 ====================

def record_attempt(class_name: str, student_id: str, student_name: str,
                   lesson_id: int, teacher_id,
                   word: str, step_type: str, is_correct: bool,
                   chosen_idx: int, correct_idx: int,
                   chosen_content: str = '', correct_content: str = ''):
    """记录一次答题（含原始选项内容）"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO attempts
               (class_name, student_id, student_name, lesson_id, teacher_id,
                word, step_type, is_correct, chosen_idx, correct_idx,
                chosen_content, correct_content, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (class_name, student_id, student_name, lesson_id, teacher_id,
             word, step_type, 1 if is_correct else 0, chosen_idx, correct_idx,
             chosen_content, correct_content,
             datetime.now().isoformat())
        )


def record_session(class_name: str, student_id: str, student_name: str,
                   lesson_id: int, teacher_id: int | None,
                   total_steps: int, correct_steps: int, stars_earned: int):
    """记录完整闯关会话"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO sessions
               (class_name, student_id, student_name, lesson_id, teacher_id,
                total_steps, correct_steps, stars_earned, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (class_name, student_id, student_name, lesson_id, teacher_id,
             total_steps, correct_steps, stars_earned, datetime.now().isoformat())
        )


def get_class_summary(teacher_id: int, class_name: str = None, lesson_id: int = None) -> list[dict]:
    """获取班级学生表现汇总（按老师 class 过滤）"""
    with get_conn() as conn:
        c = conn.cursor()
        teacher_classes = get_teacher_classes(teacher_id)
        if not teacher_classes:
            return []

        placeholders = ",".join(["?"] * len(teacher_classes))
        params = list(teacher_classes)

        where_extra = ""
        if class_name:
            where_extra += " AND s.class_name = ?"
            params.append(class_name)
        if lesson_id:
            where_extra += " AND s.lesson_id = ?"
            params.append(lesson_id)

        query = f"""
            SELECT
                s.class_name,
                s.student_id,
                s.student_name,
                s.lesson_id,
                l.grade || ' · ' || l.unit || ' · ' || l.lesson_no || ' 《' || l.title || '》' as lesson_label,
                s.total_steps,
                s.correct_steps,
                s.stars_earned,
                s.completed_at,
                ROUND(s.correct_steps * 100.0 / s.total_steps, 1) as accuracy
            FROM sessions s
            JOIN lessons l ON s.lesson_id = l.lesson_id
            WHERE s.class_name IN ({placeholders}) {where_extra}
            ORDER BY s.completed_at DESC
        """
        c.execute(query, params)
        return [dict(r) for r in c.fetchall()]


def get_word_error_stats(teacher_id: int, lesson_id: int = None) -> list[dict]:
    """获取词语错误率统计（班级维度，哪些词全班错得多）"""
    with get_conn() as conn:
        c = conn.cursor()
        teacher_classes = get_teacher_classes(teacher_id)
        if not teacher_classes:
            return []

        placeholders = ",".join(["?"] * len(teacher_classes))
        params = list(teacher_classes)

        where_extra = ""
        if lesson_id:
            where_extra = " AND a.lesson_id = ?"
            params.append(lesson_id)

        query = f"""
            SELECT
                a.word,
                a.step_type,
                COUNT(*) as total_attempts,
                SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) as wrong_attempts,
                ROUND(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as error_rate
            FROM attempts a
            WHERE a.class_name IN ({placeholders}) {where_extra}
            GROUP BY a.word, a.step_type
            ORDER BY error_rate DESC, total_attempts DESC
        """
        c.execute(query, params)
        return [dict(r) for r in c.fetchall()]


def get_all_classes_for_teacher(teacher_id: int) -> list[str]:
    """获取老师的所有班级"""
    return get_teacher_classes(teacher_id)


# ==================== 竞争机制相关 ====================

def get_week_range(reference_date=None):
    """获取周一 00:00 到周日 23:59:59 的范围（新加坡时间）"""
    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))

    if reference_date is None:
        reference_date = datetime.now(sg_tz)
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=sg_tz)

    monday = reference_date - timedelta(days=reference_date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def get_last_week_range():
    """上周一到上周日"""
    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))
    now = datetime.now(sg_tz)
    last_week_ref = now - timedelta(days=7)
    return get_week_range(last_week_ref)


def init_awards_table():
    """初始化周冠军归档表"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS weekly_awards (
                award_id INTEGER PRIMARY KEY AUTOINCREMENT,
                year_week TEXT NOT NULL,
                class_name TEXT NOT NULL,
                award_type TEXT NOT NULL,
                winner_class TEXT NOT NULL,
                winner_student_id TEXT NOT NULL,
                winner_name TEXT NOT NULL,
                winner_value TEXT NOT NULL,
                archived_at TEXT NOT NULL,
                UNIQUE(year_week, class_name, award_type)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_awards_class ON weekly_awards(class_name, year_week)")


def get_student_weekly_stats(class_name: str, student_id: str, ref_date=None) -> dict:
    """获取学生本周的统计数据"""
    week_start, week_end = get_week_range(ref_date)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(DISTINCT lesson_id) as lessons_completed,
                   SUM(stars_earned) as total_stars,
                   SUM(correct_steps) as total_correct,
                   SUM(total_steps) as total_steps,
                   COUNT(DISTINCT DATE(completed_at)) as active_days
            FROM sessions
            WHERE class_name = ? AND student_id = ?
              AND completed_at >= ? AND completed_at <= ?
        """, (class_name, student_id, week_start.isoformat(), week_end.isoformat()))
        row = c.fetchone()

        if not row or row["total_steps"] is None or row["total_steps"] == 0:
            return {
                "lessons_completed": 0,
                "total_stars": 0,
                "accuracy": 0,
                "active_days": 0
            }

        accuracy = round(row["total_correct"] * 100.0 / row["total_steps"], 1)
        return {
            "lessons_completed": row["lessons_completed"] or 0,
            "total_stars": row["total_stars"] or 0,
            "accuracy": accuracy,
            "active_days": row["active_days"] or 0
        }


def get_student_progress_vs_last_week(class_name: str, student_id: str) -> dict:
    """对比本周和上周的进步"""
    this_week = get_student_weekly_stats(class_name, student_id)

    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))
    last_week_ref = datetime.now(sg_tz) - timedelta(days=7)
    last_week = get_student_weekly_stats(class_name, student_id, last_week_ref)

    return {
        "this_week": this_week,
        "last_week": last_week,
        "stars_delta": this_week["total_stars"] - last_week["total_stars"],
        "accuracy_delta": round(this_week["accuracy"] - last_week["accuracy"], 1),
        "lessons_delta": this_week["lessons_completed"] - last_week["lessons_completed"]
    }


def get_class_leaderboard(class_name: str) -> dict:
    """获取班级 5 个奖项的本周排行榜"""
    week_start, week_end = get_week_range()

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT class_name, student_id, student_name,
                   COUNT(DISTINCT lesson_id) as lessons_completed,
                   SUM(stars_earned) as total_stars,
                   SUM(correct_steps) as total_correct,
                   SUM(total_steps) as total_steps,
                   COUNT(DISTINCT DATE(completed_at)) as active_days
            FROM sessions
            WHERE class_name = ?
              AND completed_at >= ? AND completed_at <= ?
            GROUP BY class_name, student_id, student_name
            HAVING lessons_completed >= 1
        """, (class_name, week_start.isoformat(), week_end.isoformat()))

        students = []
        for row in c.fetchall():
            accuracy = round(row["total_correct"] * 100.0 / row["total_steps"], 1) if row["total_steps"] > 0 else 0
            students.append({
                "name": row["student_name"],
                "student_id": row["student_id"],
                "lessons": row["lessons_completed"],
                "stars": row["total_stars"],
                "accuracy": accuracy,
                "days": row["active_days"]
            })

        c.execute("""
            SELECT a.class_name, a.student_id, a.student_name,
                   COUNT(DISTINCT a.word) as hard_words
            FROM attempts a
            JOIN questions q ON a.lesson_id = q.lesson_id
            WHERE a.class_name = ?
              AND a.answered_at >= ? AND a.answered_at <= ?
              AND a.is_correct = 1
              AND a.step_type = 'trap'
            GROUP BY a.class_name, a.student_id, a.student_name
        """, (class_name, week_start.isoformat(), week_end.isoformat()))
        hard_word_map = {}
        for row in c.fetchall():
            key = (row["class_name"], row["student_id"])
            hard_word_map[key] = (row["student_name"], row["hard_words"])

        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        progress_list = []
        for s in students:
            last_week_stats = get_student_weekly_stats(
                class_name, s["student_id"],
                ref_date=_dt.now(_tz(_td(hours=8))) - _td(days=7)
            )
            delta = s["accuracy"] - last_week_stats["accuracy"]
            if last_week_stats["lessons_completed"] >= 1:
                progress_list.append({"name": s["name"], "delta": round(delta, 1)})

        result = {}
        result["wang"] = [(s["name"], f"{s['lessons']} 课")
                          for s in sorted(students, key=lambda x: -x["lessons"])[:5]]
        result["zhun"] = [(s["name"], f"{s['accuracy']}%")
                          for s in sorted(students, key=lambda x: -x["accuracy"])[:5]]
        if progress_list:
            result["jinbu"] = [(p["name"], f"+{p['delta']}%" if p["delta"] >= 0 else f"{p['delta']}%")
                               for p in sorted(progress_list, key=lambda x: -x["delta"])[:5]
                               if p["delta"] > 0]
        else:
            result["jinbu"] = []
        result["jianchi"] = [(s["name"], f"{s['days']} 天")
                             for s in sorted(students, key=lambda x: -x["days"])[:5]]
        hard_list = [(name, count) for (_, _), (name, count) in hard_word_map.items()]
        result["tiaozhan"] = [(name, f"{count} 词")
                              for name, count in sorted(hard_list, key=lambda x: -x[1])[:5]]

        return result


def get_last_week_champions(class_name: str) -> dict:
    """获取上周冠军"""
    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))

    last_week_ref = datetime.now(sg_tz) - timedelta(days=7)
    year, week, _ = last_week_ref.isocalendar()
    year_week = f"{year}-W{week:02d}"

    init_awards_table()

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT award_type, winner_name, winner_value
            FROM weekly_awards
            WHERE class_name = ? AND year_week = ?
        """, (class_name, year_week))
        archived = {row["award_type"]: (row["winner_name"], row["winner_value"]) for row in c.fetchall()}

        if archived:
            return archived

        week_start, week_end = get_last_week_range()
        c.execute("""
            SELECT class_name, student_id, student_name,
                   COUNT(DISTINCT lesson_id) as lessons,
                   SUM(stars_earned) as stars,
                   SUM(correct_steps) as correct,
                   SUM(total_steps) as steps,
                   COUNT(DISTINCT DATE(completed_at)) as days
            FROM sessions
            WHERE class_name = ?
              AND completed_at >= ? AND completed_at <= ?
            GROUP BY class_name, student_id, student_name
            HAVING lessons >= 1
        """, (class_name, week_start.isoformat(), week_end.isoformat()))

        students = []
        for row in c.fetchall():
            acc = round(row["correct"] * 100.0 / row["steps"], 1) if row["steps"] > 0 else 0
            students.append({
                "class_name": row["class_name"],
                "student_id": row["student_id"],
                "name": row["student_name"],
                "lessons": row["lessons"],
                "stars": row["stars"],
                "accuracy": acc,
                "days": row["days"]
            })

        if not students:
            return {}

        result = {}
        # v7.1 调整：删除 zhun（答题最准），已升级为学生首页右上角龙虎榜 Top 5
        winners = {
            "wang": (max(students, key=lambda x: x["lessons"]), f"{max(students, key=lambda x: x['lessons'])['lessons']} 课"),
            "jianchi": (max(students, key=lambda x: x["days"]), f"{max(students, key=lambda x: x['days'])['days']} 天"),
        }

        now_str = datetime.now(sg_tz).isoformat()
        for award_type, (winner, value) in winners.items():
            c.execute("""
                INSERT OR IGNORE INTO weekly_awards
                (year_week, class_name, award_type, winner_class, winner_student_id, winner_name, winner_value, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (year_week, class_name, award_type, winner["class_name"], winner["student_id"], winner["name"], value, now_str))
            result[award_type] = (winner["name"], value)

        return result


def get_class_overall_stats(class_name: str) -> dict:
    """老师后台用：班级本周整体表现"""
    week_start, week_end = get_week_range()

    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(DISTINCT student_id) as completed_students,
                   COUNT(DISTINCT lesson_id) as covered_lessons,
                   SUM(correct_steps) as total_correct,
                   SUM(total_steps) as total_steps
            FROM sessions
            WHERE class_name = ?
              AND completed_at >= ? AND completed_at <= ?
        """, (class_name, week_start.isoformat(), week_end.isoformat()))
        row = c.fetchone()

        completed = row["completed_students"] or 0
        covered = row["covered_lessons"] or 0
        avg_acc = round(row["total_correct"] * 100.0 / row["total_steps"], 1) if row["total_steps"] else 0

        last_start, last_end = get_last_week_range()
        c.execute("""
            SELECT SUM(correct_steps) as c, SUM(total_steps) as s
            FROM sessions
            WHERE class_name = ?
              AND completed_at >= ? AND completed_at <= ?
        """, (class_name, last_start.isoformat(), last_end.isoformat()))
        last_row = c.fetchone()
        last_acc = round(last_row["c"] * 100.0 / last_row["s"], 1) if last_row and last_row["s"] else 0

        c.execute("""
            SELECT word,
                   COUNT(*) as attempts,
                   SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong
            FROM attempts
            WHERE class_name = ?
              AND answered_at >= ? AND answered_at <= ?
            GROUP BY word
            HAVING attempts >= 3
            ORDER BY (wrong * 1.0 / attempts) DESC
            LIMIT 5
        """, (class_name, week_start.isoformat(), week_end.isoformat()))

        difficult_words = []
        for row in c.fetchall():
            err_rate = round(row["wrong"] * 100.0 / row["attempts"], 1)
            difficult_words.append({
                "word": row["word"],
                "error_rate": err_rate,
                "attempts": row["attempts"]
            })

        return {
            "completed_students": completed,
            "covered_lessons": covered,
            "avg_accuracy": avg_acc,
            "last_week_accuracy": last_acc,
            "accuracy_delta": round(avg_acc - last_acc, 1),
            "difficult_words": difficult_words
        }


# ==================================================================
# v2 新增：阅读理解侦探闯关相关
# ==================================================================

def init_reading_lessons_tables():
    """初始化阅读理解相关的表(在 init_db 末尾自动调用)"""
    with get_conn() as conn:
        c = conn.cursor()
        # 阅读理解课文表(独立于词语闯关的 lessons 表)
        c.execute("""
            CREATE TABLE IF NOT EXISTS reading_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_cn TEXT NOT NULL,
                title_en TEXT,
                source TEXT,
                grade TEXT,
                unit TEXT,
                lesson_no TEXT,
                lesson_type TEXT,
                content_json TEXT NOT NULL,
                created_by_teacher_id INTEGER,
                is_published INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (created_by_teacher_id) REFERENCES teachers(teacher_id)
            )
        """)
        # 侦探闯关完成记录表
        c.execute("""
            CREATE TABLE IF NOT EXISTS detective_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                reading_lesson_id INTEGER NOT NULL,
                completion_code TEXT NOT NULL,
                badges_earned INTEGER,
                submitted_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (reading_lesson_id) REFERENCES reading_lessons(id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_completion_student ON detective_completions(class_name, student_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_lessons_grade ON reading_lessons(grade, unit, lesson_no)")

        # ===== 轻交互精读闯关：会话总表（一次完整闯关的总结）=====
        # 独立于词语闯关的 sessions 表，避免两套统计混在一起。
        c.execute("""
            CREATE TABLE IF NOT EXISTS reading_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                reading_lesson_id INTEGER NOT NULL,
                teacher_id INTEGER,
                total_graded INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY (reading_lesson_id) REFERENCES reading_lessons(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            )
        """)

        # ===== 轻交互精读闯关：逐题答题记录（选项级诊断的数据源）=====
        # chosen_content / correct_content 存"学生选了什么/正确是什么"的原文，
        # 老师后台配合题目解析即可定位偏误，无需题库带机器可读偏误标签。
        c.execute("""
            CREATE TABLE IF NOT EXISTS reading_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                student_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                reading_lesson_id INTEGER NOT NULL,
                teacher_id INTEGER,
                qid TEXT,
                qtype TEXT,
                tag TEXT,
                is_correct INTEGER NOT NULL,
                chosen_content TEXT DEFAULT '',
                correct_content TEXT DEFAULT '',
                answered_at TEXT NOT NULL,
                FOREIGN KEY (reading_lesson_id) REFERENCES reading_lessons(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_attempts_lesson ON reading_attempts(reading_lesson_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_attempts_class ON reading_attempts(class_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_sessions_class ON reading_sessions(class_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reading_sessions_teacher ON reading_sessions(teacher_id)")


def create_reading_lesson(title_cn: str, title_en: str, source: str,
                          grade: str, unit: str, lesson_no: str,
                          lesson_type: str, content_json: str,
                          teacher_id: int) -> int | None:
    """创建新阅读理解课文,返回 lesson_id"""
    try:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO reading_lessons
                (title_cn, title_en, source, grade, unit, lesson_no, lesson_type,
                 content_json, created_by_teacher_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title_cn, title_en, source, grade, unit, lesson_no, lesson_type,
                  content_json, teacher_id))
            return c.lastrowid
    except Exception:
        return None


def update_reading_lesson_content(lesson_id: int, content_json: str):
    """更新阅读理解课文的题目 JSON"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE reading_lessons
            SET content_json = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (content_json, lesson_id))


def update_reading_lesson_meta(lesson_id: int, title_cn: str, title_en: str,
                                source: str, grade: str, unit: str,
                                lesson_no: str, lesson_type: str):
    """更新阅读理解课文的元信息"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE reading_lessons
            SET title_cn = ?, title_en = ?, source = ?,
                grade = ?, unit = ?, lesson_no = ?, lesson_type = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (title_cn, title_en, source, grade, unit, lesson_no, lesson_type, lesson_id))


def list_reading_lessons(only_published: bool = True) -> list[dict]:
    """列出所有阅读理解课文"""
    with get_conn() as conn:
        c = conn.cursor()
        sql = """
            SELECT id, title_cn, title_en, source, grade, unit, lesson_no,
                   lesson_type, content_json, is_published, created_at
            FROM reading_lessons
        """
        if only_published:
            sql += " WHERE is_published = 1"
        sql += " ORDER BY grade, unit, lesson_no"

        rows = c.execute(sql).fetchall()
        results = []
        for r in rows:
            try:
                content = json.loads(r["content_json"])
                quiz = content.get('quiz', [])
                total_q = sum(len(p.get('questions', [])) for p in quiz)
            except Exception:
                total_q = 0
            results.append({
                'id': r['id'],
                'title_cn': r['title_cn'],
                'title_en': r['title_en'],
                'source': r['source'],
                'grade': r['grade'],
                'unit': r['unit'],
                'lesson_no': r['lesson_no'],
                'lesson_type': r['lesson_type'],
                'is_published': r['is_published'],
                'total_questions': total_q,
                'created_at': r['created_at']
            })
        return results


def get_reading_lesson(lesson_id: int) -> dict | None:
    """读取一个完整的阅读理解课文(用来注入 detective_template.html)"""
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute("""
            SELECT id, title_cn, title_en, source, grade, unit, lesson_no,
                   lesson_type, content_json
            FROM reading_lessons WHERE id = ?
        """, (lesson_id,)).fetchone()
        if not row:
            return None
        try:
            content = json.loads(row['content_json'])
        except (json.JSONDecodeError, TypeError):
            return None
        # 防御：阅读理解课文必须是字典 {lesson_meta, story, terms, quiz}。
        # 若存入的是数组（例如误把"词语闯关题库"存进阅读理解表），
        # 直接判定为损坏数据返回 None，避免对 list 赋值导致 TypeError 整页崩溃。
        if not isinstance(content, dict):
            return None
        # 确保 lesson_meta 字段存在
        if 'lesson_meta' not in content:
            content['lesson_meta'] = {}
        content['lesson_meta'].update({
            'lesson_id': row['id'],
            'title_cn': row['title_cn'],
            'title_en': row['title_en'] or '',
            'source': row['source'] or '',
            'grade': row['grade'] or '',
            'unit': row['unit'] or '',
            'lesson_no': row['lesson_no'] or '',
            'lesson_type': row['lesson_type'] or 'narrative'
        })
        return content


def delete_reading_lesson(lesson_id: int):
    """删除一篇阅读理解课文(同时删除完成记录)"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM detective_completions WHERE reading_lesson_id = ?", (lesson_id,))
        c.execute("DELETE FROM reading_lessons WHERE id = ?", (lesson_id,))


def toggle_reading_lesson_publish(lesson_id: int, is_published: bool):
    """切换课文的发布状态"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE reading_lessons SET is_published = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (1 if is_published else 0, lesson_id))


def record_detective_completion(class_name: str, student_id: str, student_name: str,
                                 lesson_id: int, completion_code: str,
                                 badges_earned: int = None):
    """记录学生完成侦探闯关"""
    if badges_earned is None:
        # 从完成码尾部解析徽章数(格式 DT-XXXX-N)
        try:
            badges_earned = int(completion_code.split('-')[-1])
        except (ValueError, IndexError):
            badges_earned = 0

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO detective_completions
            (class_name, student_id, student_name, reading_lesson_id,
             completion_code, badges_earned)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (class_name, student_id, student_name, lesson_id,
              completion_code, badges_earned))


def get_class_detective_progress(class_name: str) -> list[dict]:
    """老师查询班级里每个学生完成了哪些阅读理解课文"""
    with get_conn() as conn:
        c = conn.cursor()
        rows = c.execute("""
            SELECT
                dc.student_id, dc.student_name,
                rl.title_cn, rl.grade, rl.unit, rl.lesson_no,
                dc.badges_earned, dc.submitted_at
            FROM detective_completions dc
            JOIN reading_lessons rl ON dc.reading_lesson_id = rl.id
            WHERE dc.class_name = ?
            ORDER BY dc.submitted_at DESC
        """, (class_name,)).fetchall()
        return [dict(r) for r in rows]


def has_student_completed_reading(class_name: str, student_id: str, lesson_id: int) -> bool:
    """检查学生是否已完成某篇阅读理解(避免重复提交)"""
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute("""
            SELECT id FROM detective_completions
            WHERE class_name = ? AND student_id = ? AND reading_lesson_id = ?
            LIMIT 1
        """, (class_name, student_id, lesson_id)).fetchone()
        return row is not None


# ==================== 轻交互精读闯关 · 答题数据 ====================
# 与词语闯关的 record_session / record_attempt 一一对应，只是写入独立的
# reading_sessions / reading_attempts 表，互不干扰。

def find_teacher_id_for_class(class_name: str):
    """按班级名找负责老师的 teacher_id（标记答题归属用）。找不到返回 None。"""
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute(
            "SELECT teacher_id FROM teacher_classes WHERE class_name = ? LIMIT 1",
            (class_name,)
        ).fetchone()
        return row["teacher_id"] if row else None


def record_reading_session(class_name: str, student_id: str, student_name: str,
                           reading_lesson_id: int, teacher_id,
                           total_graded: int, correct_count: int):
    """记录一次完整精读闯关的总结"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO reading_sessions
               (class_name, student_id, student_name, reading_lesson_id, teacher_id,
                total_graded, correct_count, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (class_name, student_id, student_name, reading_lesson_id, teacher_id,
             int(total_graded), int(correct_count), datetime.now().isoformat())
        )


def record_reading_attempt(class_name: str, student_id: str, student_name: str,
                           reading_lesson_id: int, teacher_id,
                           qid: str, qtype: str, tag: str, is_correct: bool,
                           chosen_content: str = '', correct_content: str = ''):
    """记录精读闯关里的一道题（选项级诊断的原始数据）"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO reading_attempts
               (class_name, student_id, student_name, reading_lesson_id, teacher_id,
                qid, qtype, tag, is_correct, chosen_content, correct_content, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (class_name, student_id, student_name, reading_lesson_id, teacher_id,
             qid or '', qtype or '', tag or '', 1 if is_correct else 0,
             chosen_content or '', correct_content or '', datetime.now().isoformat())
        )


def save_reading_result(payload: dict) -> tuple:
    """一次性保存学生提交的精读闯关成绩（会话 + 每题）。
    payload 结构由 reading_light_template.html 生成：
      { class_name, student_id, student_name, reading_lesson_id,
        total_graded, correct_count, attempts:[{qid,qtype,tag,is_correct,chosen,correct}] }
    返回 (成功, 消息)。会话与逐题写入独立的 reading 表。
    """
    try:
        class_name = payload.get("class_name", "")
        student_id = payload.get("student_id", "")
        student_name = payload.get("student_name", "")
        reading_lesson_id = int(payload.get("reading_lesson_id"))

        # ===== 字段归一化：兼容两种模板的 payload 约定 =====
        # 轻交互模板：total_graded / correct_count；
        # 精读闯关模板（词灵卡）：total_blanks / first_try_correct。
        if "total_graded" in payload:
            total_graded = int(payload.get("total_graded", 0))
            correct_count = int(payload.get("correct_count", 0))
        else:
            total_graded = int(payload.get("total_blanks", 0))
            correct_count = int(payload.get("first_try_correct", 0))

        attempts = payload.get("attempts", []) or []
        # 逐题字段归一化：精读闯关用 word/chosen_content/correct_content/errtag，
        # 轻交互用 qid/chosen/correct/tag。统一成 save 需要的键。
        norm_attempts = []
        for a in attempts:
            norm_attempts.append({
                "qid": a.get("qid") or a.get("word", ""),
                "qtype": a.get("qtype") or ("fill_blank" if "word" in a else ""),
                "tag": a.get("tag") or a.get("errtag", ""),
                "is_correct": bool(a.get("is_correct", False)),
                "chosen": a.get("chosen") or a.get("chosen_content", ""),
                "correct": a.get("correct") or a.get("correct_content", ""),
            })
        attempts = norm_attempts

        teacher_id = find_teacher_id_for_class(class_name)

        record_reading_session(
            class_name=class_name, student_id=student_id, student_name=student_name,
            reading_lesson_id=reading_lesson_id, teacher_id=teacher_id,
            total_graded=total_graded, correct_count=correct_count
        )
        for a in attempts:
            record_reading_attempt(
                class_name=class_name, student_id=student_id, student_name=student_name,
                reading_lesson_id=reading_lesson_id, teacher_id=teacher_id,
                qid=a.get("qid", ""), qtype=a.get("qtype", ""), tag=a.get("tag", ""),
                is_correct=bool(a.get("is_correct", False)),
                chosen_content=a.get("chosen", ""), correct_content=a.get("correct", "")
            )
        acc = round(correct_count * 100 / total_graded, 1) if total_graded > 0 else 0
        return True, f"已记录：答对 {correct_count}/{total_graded}（{acc}%）"
    except Exception as e:
        return False, f"保存失败：{e}"


def get_reading_session_summary(teacher_id: int, class_name: str = None,
                                reading_lesson_id: int = None) -> list:
    """老师后台：精读闯关的学生完成情况汇总（只看自己班级）"""
    with get_conn() as conn:
        c = conn.cursor()
        teacher_classes = get_teacher_classes(teacher_id)
        if not teacher_classes:
            return []
        placeholders = ",".join(["?"] * len(teacher_classes))
        params = list(teacher_classes)
        where_extra = ""
        if class_name:
            where_extra += " AND rs.class_name = ?"
            params.append(class_name)
        if reading_lesson_id:
            where_extra += " AND rs.reading_lesson_id = ?"
            params.append(reading_lesson_id)
        query = f"""
            SELECT
                rs.class_name, rs.student_id, rs.student_name,
                rs.reading_lesson_id,
                rl.grade || ' · ' || rl.unit || ' · ' || rl.lesson_no
                    || ' 《' || rl.title_cn || '》' AS lesson_label,
                rs.total_graded, rs.correct_count, rs.completed_at,
                ROUND(rs.correct_count * 100.0 / rs.total_graded, 1) AS accuracy
            FROM reading_sessions rs
            JOIN reading_lessons rl ON rs.reading_lesson_id = rl.id
            WHERE rs.class_name IN ({placeholders}) {where_extra}
            ORDER BY rs.completed_at DESC
        """
        c.execute(query, params)
        return [dict(r) for r in c.fetchall()]


def get_reading_question_error_stats(teacher_id: int,
                                     reading_lesson_id: int = None) -> list:
    """老师后台：哪道题全班错得最多 + 学生最爱选的错误选项（选项级诊断核心）。
    返回按错误率降序的题目列表，含最常见错误答案，帮老师定位集体偏误。
    """
    with get_conn() as conn:
        c = conn.cursor()
        teacher_classes = get_teacher_classes(teacher_id)
        if not teacher_classes:
            return []
        placeholders = ",".join(["?"] * len(teacher_classes))
        params = list(teacher_classes)
        where_extra = ""
        if reading_lesson_id:
            where_extra = " AND ra.reading_lesson_id = ?"
            params.append(reading_lesson_id)
        # 每题总体错误率
        query = f"""
            SELECT
                ra.reading_lesson_id, ra.qid, ra.qtype, ra.tag,
                ra.correct_content,
                COUNT(*) AS total_attempts,
                SUM(CASE WHEN ra.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_attempts,
                ROUND(SUM(CASE WHEN ra.is_correct = 0 THEN 1 ELSE 0 END) * 100.0
                      / COUNT(*), 1) AS error_rate
            FROM reading_attempts ra
            WHERE ra.class_name IN ({placeholders}) {where_extra}
            GROUP BY ra.reading_lesson_id, ra.qid
            ORDER BY error_rate DESC, total_attempts DESC
        """
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]

        # 为每题补上"最常被选的错误答案"（选项级诊断）
        for row in rows:
            wp = list(params)  # 复用班级过滤
            top_wrong_sql = f"""
                SELECT ra.chosen_content, COUNT(*) AS cnt
                FROM reading_attempts ra
                WHERE ra.class_name IN ({placeholders}) {where_extra}
                  AND ra.reading_lesson_id = ? AND ra.qid = ?
                  AND ra.is_correct = 0
                GROUP BY ra.chosen_content
                ORDER BY cnt DESC
                LIMIT 1
            """
            wp2 = wp + [row["reading_lesson_id"], row["qid"]]
            tw = c.execute(top_wrong_sql, wp2).fetchone()
            row["top_wrong_answer"] = tw["chosen_content"] if tw else ""
            row["top_wrong_count"] = tw["cnt"] if tw else 0
        return rows

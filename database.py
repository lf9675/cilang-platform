"""
database.py - SQLite database operations for 词语闯关平台
设计原则：
- 用 WAL 模式提高并发性能
- 短事务，避免长时间锁表
- 软删除，避免学生数据丢失
- 用 (class_name + student_id) 作为学生主键，不依赖姓名
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
            grade TEXT NOT NULL,        -- 'Sec 1' / 'Sec 2'
            unit TEXT NOT NULL,         -- '单元一'
            lesson_no TEXT NOT NULL,    -- '第一课'
            title TEXT NOT NULL,        -- 《培养好习惯》
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
            pass  # 字段已存在
        try:
            c.execute("ALTER TABLE attempts ADD COLUMN correct_content TEXT DEFAULT ''")
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

        # 老师-班级映射（一个老师负责哪些班级）
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


# ==================== 老师相关 ====================

def hash_password(password: str) -> str:
    """密码哈希 - 使用 PBKDF2 (bcrypt 在某些 Streamlit Cloud 环境会有问题)"""
    salt = b"cilang_2026_salt_v1"  # 简单的固定盐，配合 PBKDF2
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
            # 检查是否已存在
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
    """老师添加自己负责的班级"""
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
            "SELECT lesson_id, grade, unit, lesson_no, title FROM lessons WHERE lesson_id = ? AND is_active = 1",
            (lesson_id,)
        )
        row = c.fetchone()
        return dict(row) if row else None


# ==================== 题库相关 ====================

def save_questions(lesson_id: int, questions: list, teacher_id: int) -> tuple[bool, str]:
    """保存题库。questions 是符合规范的列表"""
    if not questions:
        return False, "题库不能为空"

    # 计算 step_count
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
            # 更新课文的 updated_at
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

        # 构造 IN 子句
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
    """获取老师的所有班级（包括有学生答题但未在 teacher_classes 注册的）"""
    return get_teacher_classes(teacher_id)


# ==================== 竞争机制相关 ====================

def get_week_range(reference_date=None):
    """获取周一 00:00 到周日 23:59:59 的范围（新加坡时间）"""
    from datetime import datetime, timedelta, timezone
    # 新加坡 UTC+8
    sg_tz = timezone(timedelta(hours=8))
    if reference_date is None:
        reference_date = datetime.now(sg_tz)
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=sg_tz)
    
    # 周一是 weekday() == 0
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
        
        # 本周完成的课文数（去重）
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
    """获取班级 5 个奖项的本周排行榜
    
    返回：{
      "wang": [(name, value), ...],     # 闯关之王（完成课文最多）
      "zhun": [(name, value), ...],     # 答题最准（正确率最高）
      "jinbu": [(name, value), ...],    # 进步之星（正确率提升最多）
      "jianchi": [(name, value), ...],  # 坚持小达人（做题天数最多）
      "tiaozhan": [(name, value), ...], # 挑战大师（hard 词最多）
    }
    """
    week_start, week_end = get_week_range()
    
    with get_conn() as conn:
        c = conn.cursor()
        
        # 取所有本周完成至少 1 课的学生
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
        
        # 计算挑战大师（hard 词数量）
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
    
    # 计算上周数据用于"进步之星"
    progress_list = []
    for s in students:
        last_week_stats = get_student_weekly_stats(
            class_name, s["student_id"],
            ref_date=__import__('datetime').datetime.now(__import__('datetime').timezone(__import__('datetime').timedelta(hours=8))) - __import__('datetime').timedelta(days=7)
        )
        delta = s["accuracy"] - last_week_stats["accuracy"]
        # 只有上周也做过题的才算进步
        if last_week_stats["lessons_completed"] >= 1:
            progress_list.append({"name": s["name"], "delta": round(delta, 1)})
    
    # 排序生成 5 个榜单
    result = {}
    
    # 1. 闯关之王（完成课文最多）
    result["wang"] = [(s["name"], f"{s['lessons']} 课") 
                     for s in sorted(students, key=lambda x: -x["lessons"])[:5]]
    
    # 2. 答题最准（正确率最高，至少完成 1 课）
    result["zhun"] = [(s["name"], f"{s['accuracy']}%") 
                     for s in sorted(students, key=lambda x: -x["accuracy"])[:5]]
    
    # 3. 进步之星（正确率提升最多）
    if progress_list:
        result["jinbu"] = [(p["name"], f"+{p['delta']}%" if p["delta"] >= 0 else f"{p['delta']}%") 
                         for p in sorted(progress_list, key=lambda x: -x["delta"])[:5]
                         if p["delta"] > 0]  # 只显示正向进步
    else:
        result["jinbu"] = []
    
    # 4. 坚持小达人（做题天数最多）
    result["jianchi"] = [(s["name"], f"{s['days']} 天") 
                       for s in sorted(students, key=lambda x: -x["days"])[:5]]
    
    # 5. 挑战大师（答对的 hard 词陷阱关数量）
    hard_list = [(name, count) for (_, _), (name, count) in hard_word_map.items()]
    result["tiaozhan"] = [(name, f"{count} 词") 
                        for name, count in sorted(hard_list, key=lambda x: -x[1])[:5]]
    
    return result


def get_last_week_champions(class_name: str) -> dict:
    """获取上周冠军（如已归档，从归档表读；如未归档，实时计算并归档）"""
    from datetime import datetime, timedelta, timezone
    sg_tz = timezone(timedelta(hours=8))
    
    # 计算上周的 year_week 标识
    last_week_ref = datetime.now(sg_tz) - timedelta(days=7)
    year, week, _ = last_week_ref.isocalendar()
    year_week = f"{year}-W{week:02d}"
    
    init_awards_table()
    
    # 先查归档表
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
    
    # 没归档，实时计算并写入
    week_start, week_end = get_last_week_range()
    
    with get_conn() as conn:
        c = conn.cursor()
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
        winners = {
            "wang": (max(students, key=lambda x: x["lessons"]), f"{max(students, key=lambda x: x['lessons'])['lessons']} 课"),
            "zhun": (max(students, key=lambda x: x["accuracy"]), f"{max(students, key=lambda x: x['accuracy'])['accuracy']}%"),
            "jianchi": (max(students, key=lambda x: x["days"]), f"{max(students, key=lambda x: x['days'])['days']} 天"),
        }
        
        # 归档
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
        
        # 完成人数
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
        
        # 上周平均正确率（用于对比）
        last_start, last_end = get_last_week_range()
        c.execute("""
            SELECT SUM(correct_steps) as c, SUM(total_steps) as s
            FROM sessions
            WHERE class_name = ?
              AND completed_at >= ? AND completed_at <= ?
        """, (class_name, last_start.isoformat(), last_end.isoformat()))
        last_row = c.fetchone()
        last_acc = round(last_row["c"] * 100.0 / last_row["s"], 1) if last_row and last_row["s"] else 0
        
        # 错得最多的词（本周班级范围内）
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

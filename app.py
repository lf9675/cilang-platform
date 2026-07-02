"""
app.py - 词语闯关平台 学生入口
功能：登录 → 选课文 → 进入闯关 → 提交成绩

v7.1 路由规则：
- 默认（裸 URL）：学生身份，侧边栏只显示「课文词语闯关」+「课文理解」
- ?role=teacher：老师身份，自动跳转老师后台，侧边栏显示全部页面
"""
import streamlit as st
import streamlit.components.v1 as components
import database as db
import json
import uuid
import os
from pathlib import Path

# 初始化数据库（首次启动）
db.init_db()

# ====== v7.1：角色路由（必须在 set_page_config 之后才能用 query_params）======
# 先读 URL 参数判断角色
_role = st.query_params.get("role", "student")  # 默认学生
_is_teacher = (_role == "teacher")

st.set_page_config(
    page_title="词语闯关 · 培养好习惯",
    page_icon="📖",
    layout="centered",
    initial_sidebar_state="expanded" if _is_teacher else "collapsed"
)

# 老师身份 → 自动跳转老师后台
if _is_teacher:
    st.switch_page("pages/2_📊_老师后台.py")

# ====== 学生身份：用 CSS 隐藏老师页面的侧边栏链接 ======
# 侧边栏页面顺序：1.app(当前页) 2.老师后台 3.题库管理 4.课文理解 5.阅读理解管理
# 学生只能看到：app(词语闯关入口) 和 课文理解（侦探闯关）
# 老师页面（2、3、5）隐藏，学生即使硬闯也会被 auth.require_teacher() 拦住
st.markdown("""
<style>
/* 隐藏老师专属页面：老师后台(2)、题库管理(3)、阅读理解管理(5) */
[data-testid="stSidebarNav"] ul li:nth-child(2),
[data-testid="stSidebarNav"] ul li:nth-child(3),
[data-testid="stSidebarNav"] ul li:nth-child(5) {
    display: none !important;
}
/* v7.2 BUGFIX：移除「把 app 改名为 课文词语闯关」的 CSS hack。
   原写法 [stSidebarNav] li:first-child a span { font-size:0 } 在 iPad Safari
   上会连带命中 st.radio 的选项文字（年级/单元/课文），导致只显示红绿圆点、
   看不到文字。桌面 Chrome 的 DOM 层级不同所以没暴露。
   侧边栏默认 collapsed，学生看不到，第一项显示 "app" 不影响使用。
   如需美化导航名，后续用 st.navigation + st.Page 原生方案，不要再用 CSS hack。*/
</style>
""", unsafe_allow_html=True)

# 防止 Streamlit toolbar 遮挡（华文通经验）
st.markdown("""
<style>
.block-container { padding-top: 2.5rem !important; padding-bottom: 2rem !important; }
[data-testid="stHeader"] { background: transparent; }
.stApp { background: linear-gradient(135deg, #fafbf6 0%, #f0f7f4 100%); }
h1, h2, h3 { color: #34495e; }
.hero-title { font-size: 28px; font-weight: 700; color: #4a9bd1; letter-spacing: 4px; text-align: center; margin-bottom: 4px; }
.hero-sub { text-align: center; color: #7a8b9c; font-size: 14px; letter-spacing: 1px; margin-bottom: 28px; }
.stButton > button { border-radius: 10px; font-weight: 600; }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #6db8e8, #4a9bd1); border: none; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    defaults = {
        "student_info": None,        # {class_name, student_id, student_name}
        "selected_lesson_id": None,
        "session_token": None,
        "quiz_in_progress": False,
        "quiz_celebration": None,    # 提交成功后的结算态(修复按钮点击丢失)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()


def render_hero():
    st.markdown('<div class="hero-title">📖 词语闯关 ✨</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-sub">Higher Chinese Vocabulary Learning Platform</div>', unsafe_allow_html=True)


def render_student_login():
    """学生信息输入"""
    render_hero()

    with st.container(border=True):
        st.markdown("### 👋 同学，请先告诉我们你是谁")

        col1, col2 = st.columns(2)
        with col1:
            class_name = st.text_input("班级", placeholder="例如：1A、2E3", help="请按学校格式填写").strip()
        with col2:
            student_id = st.text_input("学号", placeholder="例如：12", help="不超过10位").strip()

        student_name = st.text_input("姓名", placeholder="请输入你的中文姓名").strip()

        if st.button("进入选课页面 →", type="primary", use_container_width=True):
            if not class_name or not student_id or not student_name:
                st.error("请把班级、学号、姓名都填好哦~")
            elif len(student_id) > 10:
                st.error("学号不要超过 10 位")
            else:
                st.session_state.student_info = {
                    "class_name": class_name,
                    "student_id": student_id,
                    "student_name": student_name
                }
                st.rerun()

    # 引导到老师后台（v7.1 改为弱化的小字提示，避免学生误点）
    st.markdown("---")
    st.caption("👩‍🏫 老师请使用专属链接：在网址后加 `?role=teacher` 进入老师后台")


def render_lesson_selector():
    """三级选课：年级 → 单元 → 课文 + 个人进步 + 班级冠军榜"""
    info = st.session_state.student_info
    render_hero()

    # 顶部欢迎 + 班级龙虎榜（左右两栏）
    top_left, top_right = st.columns([3, 2])

    with top_left:
        with st.container(border=True):
            st.markdown(f"### 👋 {info['student_name']} 同学，欢迎你！")
            st.caption(f"班级 {info['class_name']} · 学号 {info['student_id']}")
            if st.button("切换其他同学", help="如果你不是这位同学"):
                st.session_state.student_info = None
                st.rerun()

    with top_right:
        # 班级正确率龙虎榜 Top 5（v7.1 新增）
        with st.container(border=True):
            st.markdown(f"#### 🐲 班级龙虎榜 · {info['class_name']}")
            st.caption("本周正确率前 5 名")
            lb_preview = db.get_class_leaderboard(info["class_name"])
            top5 = lb_preview.get("zhun", [])
            if not top5:
                st.caption("📭 还没有数据，做题就有机会上榜~")
            else:
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                for rank, (name, value) in enumerate(top5):
                    is_me = name == info["student_name"]
                    if is_me:
                        st.markdown(f"**{medals[rank]} {name}** · {value} ← 是你！")
                    else:
                        st.markdown(f"{medals[rank]} {name} · {value}")

    # ====== 个人进步卡片 ======
    progress = db.get_student_progress_vs_last_week(info["class_name"], info["student_id"])
    this_week = progress["this_week"]

    with st.container(border=True):
        st.markdown("### 📊 我这周的表现")
        cols = st.columns(4)
        with cols[0]:
            stars = this_week["total_stars"]
            delta = progress["stars_delta"]
            delta_str = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "—")
            st.metric("⭐ 星星", stars, delta_str if delta != 0 else None)
        with cols[1]:
            acc = this_week["accuracy"]
            delta = progress["accuracy_delta"]
            delta_str = f"+{delta}%" if delta > 0 else (f"{delta}%" if delta < 0 else "—")
            st.metric("🎯 正确率", f"{acc}%", delta_str if delta != 0 else None)
        with cols[2]:
            lessons = this_week["lessons_completed"]
            st.metric("📚 完成课文", lessons)
        with cols[3]:
            days = this_week["active_days"]
            st.metric("📅 做题天数", days)

        if this_week["lessons_completed"] == 0:
            st.info("💡 这周还没开始呢，选一课开始闯关吧！")
        elif progress["stars_delta"] > 0 and progress["accuracy_delta"] > 0:
            st.success("🎉 又进步又有更多星星，很棒！")
        elif progress["stars_delta"] > 0:
            st.info("👍 做了更多题，继续加油！")

    # ====== 班级冠军榜 ======
    # v7.1 调整：删除「答题最准」奖项（已升级为右上角龙虎榜 Top 5），避免重复
    leaderboard = db.get_class_leaderboard(info["class_name"])
    
    has_any = any(leaderboard[k] for k in leaderboard if k != "zhun")
    if has_any:
        with st.container(border=True):
            st.markdown(f"### 🏆 本周班级冠军榜 · {info['class_name']}")
            st.caption("📅 每周一 00:00 重置，周日晚 11:59 公布冠军")
            
            tab_labels = ["🏆 闯关之王", "📈 进步之星", "🌟 坚持小达人", "⚡ 挑战大师"]
            tab_keys = ["wang", "jinbu", "jianchi", "tiaozhan"]
            tab_caption = {
                "wang": "完成不同课文最多",
                "jinbu": "比上周进步最多",
                "jianchi": "做题天数最多",
                "tiaozhan": "答对挑战关词语最多"
            }
            
            board_tabs = st.tabs(tab_labels)
            for i, key in enumerate(tab_keys):
                with board_tabs[i]:
                    st.caption(tab_caption[key])
                    items = leaderboard[key]
                    if not items:
                        st.info("还没有数据，做题就有机会上榜~")
                    else:
                        medals = ["🥇", "🥈", "🥉", "4.", "5."]
                        for rank, (name, value) in enumerate(items):
                            is_me = name == info["student_name"]
                            highlight = " ← 是你！" if is_me else ""
                            if is_me:
                                st.markdown(f"**{medals[rank]} {name}** · {value}**{highlight}**")
                            else:
                                st.markdown(f"{medals[rank]} {name} · {value}")
    
    # ====== 上周冠军墙（简化版）======
    # v7.1 调整：删除「答题最准」，因为已升级为右上角龙虎榜（Top 5 在本周已实时展示）
    last_champs = db.get_last_week_champions(info["class_name"])
    if last_champs:
        with st.expander("🏅 上周冠军墙", expanded=False):
            cols = st.columns(2)
            champ_labels = {
                "wang": ("🏆", "闯关之王"),
                "jianchi": ("🌟", "坚持小达人")
            }
            shown = 0
            for key, (emoji, label) in champ_labels.items():
                if key in last_champs:
                    name, value = last_champs[key]
                    with cols[shown % 2]:
                        st.markdown(f"**{emoji} {label}**")
                        st.markdown(f"{name}")
                        st.caption(value)
                    shown += 1

    st.markdown("### 📚 请选择你要学习的课文")

    # 取所有课文
    hierarchy = db.list_grades_units_lessons()

    if not hierarchy:
        st.warning("还没有任何课文哦，请告诉老师先添加课文～")
        return

    # 三级选择
    grades = sorted(hierarchy.keys())
    grade = st.radio("年级", grades, horizontal=True, key="sel_grade")

    units = sorted(hierarchy[grade].keys())
    unit = st.radio("单元", units, horizontal=True, key="sel_unit")

    lessons = hierarchy[grade][unit]
    if not lessons:
        st.info("这个单元还没有课文")
        return

    # 显示该单元的所有课文卡片
    st.markdown("**课文：**")
    for lesson_id, lesson_no, title in lessons:
        meta = db.get_questions_meta(lesson_id)

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{lesson_no} · 《{title}》**")
                if meta:
                    st.caption(f"📝 {meta['word_count']} 个词语 · 共 {meta['step_count']} 关")
                else:
                    st.caption("⚠️ 老师还没有添加题目")
            with col2:
                if meta:
                    if st.button("开始闯关", key=f"start_{lesson_id}", type="primary", use_container_width=True):
                        st.session_state.selected_lesson_id = lesson_id
                        st.session_state.session_token = str(uuid.uuid4())
                        st.session_state.quiz_in_progress = True
                        st.session_state.quiz_celebration = None
                        st.rerun()
                else:
                    st.button("暂不可用", key=f"na_{lesson_id}", disabled=True, use_container_width=True)


def find_teacher_for_class(class_name: str) -> int | None:
    """根据班级名找到负责的老师（用于标记答题归属）"""
    with db.get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT teacher_id FROM teacher_classes WHERE class_name = ? LIMIT 1", (class_name,))
        row = c.fetchone()
        return row["teacher_id"] if row else None


def render_quiz():
    """渲染闯关页面（嵌入HTML）"""
    # ===== 结算态拦截:提交成功后走稳定的结算屏,不再渲染闯关页 =====
    if st.session_state.get("quiz_celebration"):
        render_celebration()
        return

    info = st.session_state.student_info
    lesson_id = st.session_state.selected_lesson_id
    session_token = st.session_state.session_token

    # 取课文信息和题库
    lesson = db.get_lesson(lesson_id)
    questions = db.get_questions(lesson_id)

    if not lesson or not questions:
        st.error("课文不存在或题库未配置")
        if st.button("返回选课"):
            st.session_state.quiz_in_progress = False
            st.session_state.selected_lesson_id = None
            st.rerun()
        return

    # 顶部信息条
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if st.button("⬅ 返回", help="放弃本次闯关"):
            if st.session_state.get("confirm_quit"):
                st.session_state.quiz_in_progress = False
                st.session_state.selected_lesson_id = None
                st.session_state.session_token = None
                st.session_state.confirm_quit = False
                st.rerun()
            else:
                st.session_state.confirm_quit = True
                st.warning("再点一次「返回」就会放弃本次成绩哦！")
    with col2:
        st.markdown(f"<div style='text-align:center; padding-top:6px;'><strong>{lesson['grade']} · {lesson['unit']} · {lesson['lesson_no']}</strong> · 《{lesson['title']}》</div>", unsafe_allow_html=True)
    with col3:
        pass  # 占位

    # 找到该班级的负责老师
    teacher_id = find_teacher_for_class(info["class_name"])

    # 构造 QUIZ_CONTEXT
    quiz_context = {
        "session_token": session_token,
        "class_name": info["class_name"],
        "student_id": info["student_id"],
        "student_name": info["student_name"],
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "lesson_label": f"{lesson['grade']} · {lesson['unit']} · {lesson['lesson_no']} 《{lesson['title']}》"
    }

    # 加载 HTML 模板
    template_path = Path(__file__).parent / "templates" / "quiz_template.html"
    html_content = template_path.read_text(encoding="utf-8")

    # 注入数据（JSON 注入要严格，避免 XSS 和符号问题）
    html_content = html_content.replace(
        "__QUIZ_CONTEXT__",
        json.dumps(quiz_context, ensure_ascii=False)
    )
    html_content = html_content.replace(
        "__WORDS_DATA__",
        json.dumps(questions, ensure_ascii=False)
    )

    # 嵌入 HTML
    components.html(html_content, height=900, scrolling=True)

    # 提交成绩按钮（在 HTML 下方）
    st.markdown("---")
    st.info("📋 完成所有关卡后，点击下方按钮提交成绩给老师")

    with st.form("submit_result_form"):
        st.markdown("**提交成绩后才会记录到老师后台哦！**")
        # 用 JS 把 localStorage 的数据写到 hidden text input
        result_json = st.text_area(
            "（系统自动填充，无需修改）",
            value="",
            key="result_payload",
            height=68,
            help="点击下方按钮前，请先完成所有关卡"
        )
        submit = st.form_submit_button("✅ 我已完成，提交成绩", type="primary", use_container_width=True)

    # JS：把 localStorage 的结果写到 text area
    components.html(f"""
    <script>
    (function() {{
        const key = 'cilang_last_result_{session_token}';
        function tryFill() {{
            try {{
                const data = localStorage.getItem(key);
                if (data) {{
                    // 找到 streamlit 父页面的 textarea 并填入
                    const doc = window.parent.document;
                    const textareas = doc.querySelectorAll('textarea');
                    for (const ta of textareas) {{
                        if (ta.getAttribute('aria-label') && ta.getAttribute('aria-label').includes('系统自动填充')) {{
                            if (ta.value !== data) {{
                                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                                nativeInputValueSetter.call(ta, data);
                                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            return true;
                        }}
                    }}
                }}
            }} catch(e) {{ console.warn(e); }}
            return false;
        }}
        // 反复尝试，直到成功
        const interval = setInterval(() => {{
            if (tryFill()) clearInterval(interval);
        }}, 1000);
    }})();
    </script>
    """, height=0)

    if submit:
        if not result_json.strip():
            st.error("⚠️ 还没有检测到完成数据。请先在上方完成所有关卡，看到「词语图鉴」页面后再点提交。")
        else:
            try:
                payload = json.loads(result_json)
                process_submission(payload)
            except json.JSONDecodeError:
                st.error("数据格式错误，请重新闯关")
            except Exception as e:
                st.error(f"提交失败：{e}")


def process_submission(payload: dict):
    """处理学生提交的成绩"""
    info = st.session_state.student_info

    # 安全检查
    if payload.get("session_token") != st.session_state.session_token:
        st.error("会话不匹配，请重新闯关")
        return
    if payload.get("class_name") != info["class_name"] or payload.get("student_id") != info["student_id"]:
        st.error("学生信息不匹配")
        return

    lesson_id = int(payload["lesson_id"])
    teacher_id = payload.get("teacher_id")
    total_steps = int(payload.get("total_steps", 0))
    correct_steps = int(payload.get("correct_steps", 0))
    stars_earned = int(payload.get("stars_earned", 0))
    attempts = payload.get("attempts", [])

    # 写入数据库
    try:
        # 记录会话
        db.record_session(
            class_name=info["class_name"],
            student_id=info["student_id"],
            student_name=info["student_name"],
            lesson_id=lesson_id,
            teacher_id=teacher_id,
            total_steps=total_steps,
            correct_steps=correct_steps,
            stars_earned=stars_earned
        )
        # 记录每一题
        for att in attempts:
            db.record_attempt(
                class_name=info["class_name"],
                student_id=info["student_id"],
                student_name=info["student_name"],
                lesson_id=lesson_id,
                teacher_id=teacher_id,
                word=att.get("word", ""),
                step_type=att.get("step_type", ""),
                is_correct=bool(att.get("is_correct", False)),
                chosen_idx=int(att.get("chosen_idx", -1)),
                correct_idx=int(att.get("correct_idx", -1)),
                chosen_content=att.get("chosen_content", ""),
                correct_content=att.get("correct_content", "")
            )

        acc = round(correct_steps * 100 / total_steps, 1) if total_steps > 0 else 0
        # ===== 修复:结算画面不能渲染在这个一次性分支里 =====
        # 之前把「恭喜+继续做课文理解」按钮直接画在这里,导致点按钮后页面重跑、
        # 这段代码不再执行、点击被丢弃(页面停留在闯关页)。
        # 现在改为:把结算信息存进 session_state,立刻重跑,
        # 由 render_quiz 开头的稳定路径渲染结算屏,按钮点击才有效。
        st.session_state.quiz_celebration = {
            "lesson_id": lesson_id,
            "acc": acc,
            "stars": stars_earned,
            "balloons_shown": False,
        }
        st.rerun()

    except Exception as e:
        st.error(f"保存失败：{e}")


def render_celebration():
    """结算屏(稳定路径):提交成功后由 render_quiz 开头渲染。
    按钮画在这里,每次重跑都会重新渲染,点击不会丢失。"""
    cele = st.session_state.quiz_celebration
    lesson_id = cele["lesson_id"]

    st.success(f"🎉 成绩已提交！正确率 {cele['acc']}%，共获得 ⭐ {cele['stars']} 颗星")
    if not cele.get("balloons_shown"):
        st.balloons()
        cele["balloons_shown"] = True

    # ===== 预习流程：这篇课文若关联了阅读/精读，突出续做按钮 =====
    linked_reading_id = db.get_lesson_linked_reading(lesson_id)

    if linked_reading_id is not None:
        # 按关联课文的格式区分文案:精读闯关(reading_game)→ 拿精灵卡;其他 → 课文理解
        _linked = db.get_reading_lesson(linked_reading_id) or {}
        _is_rg = str(_linked.get('lesson_meta', {}).get('format', '')).lower() == 'reading_game'
        if _is_rg:
            st.markdown("#### ⚔️ 词语三关完成!第四关等你——精读故事,赢取精灵卡!")
            btn_label = "⚔️ 再战第四关 · 拿精灵卡 →"
        else:
            st.markdown("#### 🎯 词语闯关完成!这一课还有课文理解,一起做完就是完整预习～")
            btn_label = "📖 继续做课文理解 →"
        if st.button(btn_label, type="primary", use_container_width=True):
            # 直接把目标阅读理解课文选好，学生跳过去不用重新登录/选课
            st.session_state.selected_reading_lesson = linked_reading_id
            st.session_state.reading_session_token = str(uuid.uuid4())
            # 清掉词语闯关状态，避免返回时残留
            st.session_state.quiz_celebration = None
            st.session_state.quiz_in_progress = False
            st.session_state.selected_lesson_id = None
            st.session_state.session_token = None
            st.switch_page("pages/4_📖_课文理解.py")

        # 次要动作放小按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📚 先选其他课文", use_container_width=True):
                st.session_state.quiz_celebration = None
                st.session_state.quiz_in_progress = False
                st.session_state.selected_lesson_id = None
                st.session_state.session_token = None
                st.rerun()
        with col2:
            if st.button("🔄 重做词语这一课", use_container_width=True):
                st.session_state.quiz_celebration = None
                st.session_state.session_token = str(uuid.uuid4())
                st.rerun()
    else:
        # 没关联阅读理解：保持原有两个按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📚 再选其他课文", use_container_width=True):
                st.session_state.quiz_celebration = None
                st.session_state.quiz_in_progress = False
                st.session_state.selected_lesson_id = None
                st.session_state.session_token = None
                st.rerun()
        with col2:
            if st.button("🔄 重做这一课", use_container_width=True):
                st.session_state.quiz_celebration = None
                st.session_state.session_token = str(uuid.uuid4())
                st.rerun()


# ==================== 主流程 ====================
if not st.session_state.student_info:
    render_student_login()
elif not st.session_state.quiz_in_progress:
    render_lesson_selector()
else:
    render_quiz()

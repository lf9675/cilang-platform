"""
pages/4_📖_核心课文.py - 课文理解闯关页面(阅读理解)
功能:学生选课文 → 按课文格式注入对应模板 → 嵌入闯关页面
  - lesson_meta.format == 'light'  → reading_light_template.html（轻交互，整份 JSON 注入）
  - 其他（默认/detective）          → detective_template.html（原侦探闯关，逻辑不变）
"""

import streamlit as st
import streamlit.components.v1 as components
import database as db
import json
import uuid
from pathlib import Path

st.set_page_config(
    page_title="课文理解 · 精读闯关",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 防止 Streamlit toolbar 遮挡
st.markdown("""
<style>
.block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; }
[data-testid="stHeader"] { background: transparent; }

/* v7.1：在学生页面（课文理解）隐藏老师专属页面的侧栏链接 */
/* 顺序：1.app 2.老师后台 3.题库管理 4.课文理解(当前) 5.阅读理解管理 */
[data-testid="stSidebarNav"] ul li:nth-child(2),
[data-testid="stSidebarNav"] ul li:nth-child(3),
[data-testid="stSidebarNav"] ul li:nth-child(5) {
    display: none !important;
}

/* v7.1：把侧边栏第一个链接的文字「app」改成「课文词语闯关」 */
/* 用 font-size:0 隐藏原文字，::before 注入新文字（这种写法容器会自动撑开）*/
[data-testid="stSidebarNav"] ul li:first-child a span {
    font-size: 0;
}
[data-testid="stSidebarNav"] ul li:first-child a span::before {
    content: "课文词语闯关";
    font-size: 14px;
    white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)


def init_session():
    if "student_info" not in st.session_state:
        st.session_state.student_info = None
    if "selected_reading_lesson" not in st.session_state:
        st.session_state.selected_reading_lesson = None
    if "reading_session_token" not in st.session_state:
        st.session_state.reading_session_token = None
    if "reading_saved_tokens" not in st.session_state:
        # 已成功写库的 session_token 集合，防止重复写入
        st.session_state.reading_saved_tokens = set()


def render_login():
    """学生信息输入(简化版,可直接复用 app.py 的逻辑)"""
    st.markdown("## 📖 课文理解闯关")
    st.markdown("欢迎!请先告诉我们你是谁。")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            class_name = st.text_input("班级", placeholder="例如:1A").strip()
        with col2:
            student_id = st.text_input("学号", placeholder="例如:12").strip()
        student_name = st.text_input("姓名", placeholder="你的中文姓名").strip()

        if st.button("进入选课页面 →", type="primary", use_container_width=True):
            if not class_name or not student_id or not student_name:
                st.error("请把班级、学号、姓名都填好")
            else:
                st.session_state.student_info = {
                    "class_name": class_name,
                    "student_id": student_id,
                    "student_name": student_name
                }
                st.rerun()


def render_lesson_selector():
    """选课文 - 从 reading_lessons 表读取所有已发布的课文"""
    info = st.session_state.student_info

    st.markdown(f"### 👋 {info['student_name']} 同学,选一篇课文开始闯关")
    st.caption(f"班级 {info['class_name']} · 学号 {info['student_id']}")

    reading_lessons = db.list_reading_lessons()

    if not reading_lessons:
        st.warning("还没有任何阅读理解课文。请老师先在「📖 阅读理解管理」页面添加课文。")
        return

    for lesson in reading_lessons:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{lesson['grade']} · {lesson['unit']} · {lesson['lesson_no']} · 《{lesson['title_cn']}》**")
                st.caption(f"📝 文体:{lesson['lesson_type']} · 共 {lesson['total_questions']} 题")
            with col2:
                if st.button("开始闯关", key=f"start_{lesson['id']}", type="primary", use_container_width=True):
                    st.session_state.selected_reading_lesson = lesson['id']
                    st.session_state.reading_session_token = str(uuid.uuid4())
                    st.rerun()


def render_detective_quiz():
    """渲染课文闯关页面 - 按课文格式选择模板并注入数据"""
    info = st.session_state.student_info
    lesson_id = st.session_state.selected_reading_lesson

    # 从数据库读取完整的课文 JSON
    lesson_data = db.get_reading_lesson(lesson_id)
    if not lesson_data:
        st.error("课文不存在")
        return

    # ===== 数据完整性守卫 =====
    missing = [k for k in ('story', 'terms', 'quiz', 'lesson_meta') if k not in lesson_data]
    if missing:
        if st.button("⬅ 返回选课"):
            st.session_state.selected_reading_lesson = None
            st.rerun()
        st.error(f"❌ 这篇课文的数据不完整，缺少：{', '.join(missing)}")
        st.info(
            "💡 这篇课文可能导入了错误格式的 JSON（例如把词语闯关题库存了进来）。"
            "请老师到「📖 阅读理解管理」删除后，重新导入正确的课文闯关 JSON。"
        )
        return

    meta = lesson_data['lesson_meta']

    # ===== v8 新增：按 lesson_meta.format 选择引擎模板 =====
    # 'light' → 轻交互模板；其余（含旧课文，无 format 字段）→ 原侦探模板，行为完全不变。
    is_light = str(meta.get('format', '')).lower() == 'light'

    templates_dir = Path(__file__).parent.parent / "templates"

    # 返回按钮 + 标题（两种格式共用）
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("⬅ 返回选课"):
            st.session_state.selected_reading_lesson = None
            st.rerun()
    with col2:
        st.markdown(
            f"### {meta.get('grade','')} · {meta.get('unit','')} · "
            f"{meta.get('lesson_no','')} · 《{meta.get('title_cn','')}》"
        )

    # ========== 分支 1：轻交互模板 ==========
    if is_light:
        session_token = st.session_state.reading_session_token or str(uuid.uuid4())
        st.session_state.reading_session_token = session_token

        template_path = templates_dir / "reading_light_template.html"
        html_content = template_path.read_text(encoding="utf-8")

        # 学生身份上下文（自动回传成绩用）
        reading_ctx = {
            "session_token": session_token,
            "class_name": info["class_name"],
            "student_id": info["student_id"],
            "student_name": info["student_name"],
            "reading_lesson_id": lesson_id,
        }

        # 整份课文 JSON + 学生上下文，各注入一个占位符
        html_content = html_content.replace(
            '__LESSON_DATA__', json.dumps(lesson_data, ensure_ascii=False)
        )
        html_content = html_content.replace(
            '__READING_CONTEXT__', json.dumps(reading_ctx, ensure_ascii=False)
        )
        components.html(html_content, height=900, scrolling=True)

        # ===== 自动提交：父页面轮询 localStorage，读到成绩就写库 =====
        # 学生做完最后一关，引擎已把成绩写进 localStorage。这里用一个隐藏组件
        # 把它读出来、填进一个 text_area，Streamlit rerun 后本页读取并写库。
        # 学生无需点任何按钮（页面会自己刷一下，这是 Streamlit iframe 通信的固有限制）。
        result_json = st.text_area(
            "reading_result_payload",
            value="",
            key="reading_result_payload",
            height=68,
            label_visibility="collapsed",
        )

        # 隐藏这个中转 text_area（学生不该看到）
        st.markdown(
            "<style>div[data-testid='stTextArea']:has(textarea[aria-label='reading_result_payload'])"
            "{position:absolute;left:-99999px;height:0;overflow:hidden;}</style>",
            unsafe_allow_html=True,
        )

        # 轮询 JS：把 localStorage 的成绩写进上面的 text_area 并触发 input 事件
        components.html(f"""
        <script>
        (function() {{
            const key = 'cilang_reading_result_{session_token}';
            function tryFill() {{
                try {{
                    const data = localStorage.getItem(key);
                    if (!data) return false;
                    const doc = window.parent.document;
                    const tas = doc.querySelectorAll('textarea');
                    for (const ta of tas) {{
                        if (ta.getAttribute('aria-label') === 'reading_result_payload') {{
                            if (ta.value !== data) {{
                                const setter = Object.getOwnPropertyDescriptor(
                                    window.HTMLTextAreaElement.prototype, 'value').set;
                                setter.call(ta, data);
                                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            return true;
                        }}
                    }}
                }} catch(e) {{ console.warn(e); }}
                return false;
            }}
            const iv = setInterval(() => {{ if (tryFill()) clearInterval(iv); }}, 1200);
        }})();
        </script>
        """, height=0)

        # 读到成绩就写库（幂等：同一 session_token 只写一次）
        if result_json.strip():
            try:
                payload = json.loads(result_json)
                tok = payload.get("session_token", "")
                # 安全校验：token + 学生信息要对得上
                if (tok == session_token
                        and payload.get("class_name") == info["class_name"]
                        and payload.get("student_id") == info["student_id"]
                        and tok not in st.session_state.reading_saved_tokens):
                    ok, msg = db.save_reading_result(payload)
                    if ok:
                        st.session_state.reading_saved_tokens.add(tok)
                        st.success(f"🎉 {msg} · 已自动记录给老师")
                    else:
                        st.warning(f"成绩记录遇到问题：{msg}")
                elif tok in st.session_state.reading_saved_tokens:
                    st.caption("✅ 本次成绩已记录")
            except json.JSONDecodeError:
                pass  # 数据还没填好，静默等下一轮

        # 轻交互模板自带计分与「再挑战」，不需要侦探完成码流程
        return

    # ========== 分支 2：原侦探闯关（以下逻辑保持不变） ==========
    template_path = templates_dir / "detective_template.html"
    html_content = template_path.read_text(encoding="utf-8")

    # 5 处占位符替换 - 注入数据
    html_content = html_content.replace(
        '__STORY_DATA__', json.dumps(lesson_data['story'], ensure_ascii=False)
    )
    html_content = html_content.replace(
        '__TERMS_DATA__', json.dumps(lesson_data['terms'], ensure_ascii=False)
    )
    html_content = html_content.replace(
        '__QUIZ_DATA__', json.dumps(lesson_data['quiz'], ensure_ascii=False)
    )
    html_content = html_content.replace(
        '__LESSON_TITLE_CN__', meta['title_cn']
    )
    html_content = html_content.replace(
        '__LESSON_SOURCE__', meta.get('source', '')
    )

    # 通过全局 JS 变量把学生身份注入(原 HTML 已支持)
    student_inject = f"""
    <script>
    window.STREAMLIT_STUDENT_INFO = {{
        className: {json.dumps(info['class_name'])},
        studentId: {json.dumps(info['student_id'])},
        studentName: {json.dumps(info['student_name'])},
        lessonId: {lesson_id}
    }};
    </script>
    """
    html_content = html_content.replace('</body>', student_inject + '</body>')

    components.html(html_content, height=900, scrolling=True)

    # 提交完成码按钮(参照词语闯关的设计)
    st.markdown("---")
    st.info("📋 完成所有案件后,把完成码复制下来粘贴到下面:")

    with st.form("submit_detective_code"):
        completion_code = st.text_input(
            "完成码",
            placeholder="DT-XXXX-N",
            help="完成所有 24 个案件后,系统会显示完成码"
        )
        if st.form_submit_button("✅ 提交完成码", type="primary"):
            from detective_utils import verify_completion_code
            if verify_completion_code(
                completion_code,
                info['class_name'],
                info['student_id'],
                lesson_id
            ):
                db.record_detective_completion(
                    class_name=info['class_name'],
                    student_id=info['student_id'],
                    student_name=info['student_name'],
                    lesson_id=lesson_id,
                    completion_code=completion_code
                )
                st.success(f"🎉 完成码验证成功!成绩已上传给老师")
                st.balloons()
            else:
                st.error("完成码无效。请检查是否完整复制了 DT-XXXX-N 格式")


# ============ 主流程 ============
init_session()

if not st.session_state.student_info:
    render_login()
elif st.session_state.selected_reading_lesson is None:
    render_lesson_selector()
else:
    render_detective_quiz()

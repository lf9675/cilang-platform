"""
pages/4_📖_课文理解.py - 侦探闯关页面(阅读理解)
功能:学生选课文 → 注入 detective_template.html → 嵌入闯关页面

v7.2 更新（2026-05-19）：
- 新增 intro_finale 字段支持：mission/finale 文案从 JSON 读
- 增加 5 处占位符替换：__INTRO_TITLE_EN__、__MISSION_CN__、__MISSION_EN__、
  __FINALE_SUMMARY_CN__、__FINALE_SUMMARY_EN__
- 向后兼容：JSON 没有 intro_finale 字段时使用默认值（保持《恐怖事件》原文案）
"""

import streamlit as st
import streamlit.components.v1 as components
import database as db
import json
from pathlib import Path

st.set_page_config(
    page_title="课文理解 · 侦探闯关",
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


# ============ v7.2 默认 intro_finale 文案（向后兼容 / 旧 JSON 没有此字段时使用） ============
DEFAULT_INTRO_FINALE = {
    "title_subtitle_en": "CASE FILES",
    "mission_cn": "这篇课文藏着 <strong>5 大阅读能力点</strong>等你破解：人物反应、人物描写、修辞作用、言外之意、作者观点。",
    "mission_en": "This text hides <strong>5 reading skills</strong> for you to unlock: Character Reactions, Character Portrayal, Rhetoric, Hidden Meanings, Author's Viewpoint.",
    "finale_summary_cn": "🔍 <strong>结案陈词：</strong><br><br>恭喜你完成了 24 个案件！记得用今天学的 5 个能力点：看人物反应、看人物描写、看修辞作用、看言外之意、看作者观点。",
    "finale_summary_en": "🔍 <strong>FINAL SUMMARY:</strong><br><br>Congratulations on completing all 24 cases! Remember today's 5 skills: Character Reactions, Character Portrayal, Rhetoric, Hidden Meanings, Author's Viewpoint."
}


def init_session():
    if "student_info" not in st.session_state:
        st.session_state.student_info = None
    if "selected_reading_lesson" not in st.session_state:
        st.session_state.selected_reading_lesson = None


def render_login():
    """学生信息输入(简化版,可直接复用 app.py 的逻辑)"""
    st.markdown("## 📖 阅读理解侦探闯关")
    st.markdown("欢迎,侦探!请先告诉我们你是谁。")
    
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
    
    st.markdown(f"### 👋 {info['student_name']} 同学,选一篇课文开始侦探闯关")
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
                    st.rerun()


def render_detective_quiz():
    """渲染侦探闯关页面 - 注入数据到 detective_template.html"""
    info = st.session_state.student_info
    lesson_id = st.session_state.selected_reading_lesson
    
    lesson_data = db.get_reading_lesson(lesson_id)
    if not lesson_data:
        st.error("课文不存在")
        return
    
    # 返回按钮
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("⬅ 返回选课"):
            st.session_state.selected_reading_lesson = None
            st.rerun()
    with col2:
        meta = lesson_data['lesson_meta']
        st.markdown(f"### {meta['grade']} · {meta['unit']} · {meta['lesson_no']} · 《{meta['title_cn']}》")
    
    # 加载模板
    template_path = Path(__file__).parent.parent / "templates" / "detective_template.html"
    html_content = template_path.read_text(encoding="utf-8")
    
    # ============ 原有 5 处占位符替换 ============
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
        '__LESSON_SOURCE__', meta['source']
    )
    
    # ============ v7.2 新增 5 处 intro_finale 占位符替换 ============
    # 向后兼容：如果 JSON 没有 intro_finale 字段，用默认值
    intro_finale = lesson_data.get('intro_finale', DEFAULT_INTRO_FINALE)
    
    def _js_escape(s):
        r"""
        重要：mission/finale 文案会被注入到单引号包围的 JS 字符串里
        必须把 ' 和 \ 转义，否则单引号嵌套会导致 SyntaxError → 整页空白
        中文「」无需转义
        """
        return s.replace('\\', '\\\\').replace("'", "\\'")
    
    html_content = html_content.replace(
        '__INTRO_TITLE_EN__', _js_escape(intro_finale.get('title_subtitle_en', DEFAULT_INTRO_FINALE['title_subtitle_en']))
    )
    html_content = html_content.replace(
        '__MISSION_CN__', _js_escape(intro_finale.get('mission_cn', DEFAULT_INTRO_FINALE['mission_cn']))
    )
    html_content = html_content.replace(
        '__MISSION_EN__', _js_escape(intro_finale.get('mission_en', DEFAULT_INTRO_FINALE['mission_en']))
    )
    html_content = html_content.replace(
        '__FINALE_SUMMARY_CN__', _js_escape(intro_finale.get('finale_summary_cn', DEFAULT_INTRO_FINALE['finale_summary_cn']))
    )
    html_content = html_content.replace(
        '__FINALE_SUMMARY_EN__', _js_escape(intro_finale.get('finale_summary_en', DEFAULT_INTRO_FINALE['finale_summary_en']))
    )
    
    # 把学生信息注入到一个全局 JS 变量
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
    
    # 在 </body> 之前注入
    html_content = html_content.replace('</body>', student_inject + '</body>')
    
    # 嵌入 HTML
    components.html(html_content, height=900, scrolling=True)
    
    # 提交完成码按钮
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

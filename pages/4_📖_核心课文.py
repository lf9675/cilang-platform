"""
pages/4_📖_核心课文.py - 侦探闯关页面(阅读理解)
功能:学生选课文 → 注入 detective_template.html → 嵌入闯关页面
作者:仿照 app.py 的词语闯关嵌入方式
"""

import streamlit as st
import streamlit.components.v1 as components
import database as db
import json
from pathlib import Path

st.set_page_config(
    page_title="核心课文 · 阅读理解侦探闯关",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 防止 Streamlit toolbar 遮挡
st.markdown("""
<style>
.block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; }
[data-testid="stHeader"] { background: transparent; }

/* v7.1：在学生页面（核心课文）隐藏老师专属页面的侧栏链接 */
/* 顺序：1.app 2.老师后台 3.题库管理 4.核心课文(当前) 5.阅读理解管理 */
[data-testid="stSidebarNav"] ul li:nth-child(2),
[data-testid="stSidebarNav"] ul li:nth-child(3),
[data-testid="stSidebarNav"] ul li:nth-child(5) {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


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
    
    # 从数据库读取所有阅读理解课文
    # 这里假设你有一个 db.list_reading_lessons() 函数(需要新增)
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
    
    # 从数据库读取完整的课文 JSON
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
        '__LESSON_SOURCE__', meta['source']
    )
    
    # 通过 URL 参数把学生身份传进去(原 HTML 已经支持读 URL 参数)
    # 但 components.html 嵌入时,iframe 的 URL 不会带这些参数
    # 解决:把学生信息注入到一个全局 JS 变量,覆盖原有的 URL 读取逻辑
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
    
    # 嵌入 HTML(给足够高度,允许内部滚动)
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
            # 调用现有的 detective_utils.py 校验
            from detective_utils import verify_completion_code
            if verify_completion_code(
                completion_code,
                info['class_name'],
                info['student_id'],
                lesson_id
            ):
                # 记录到数据库
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

"""
pages/5_📖_阅读理解管理.py - 老师后台阅读理解管理
功能:老师创建、编辑、删除阅读理解课文(侦探闯关),支持手动 JSON 导入
"""

import streamlit as st
import database as db
import auth
import json

st.set_page_config(
    page_title="阅读理解管理 · 侦探闯关",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 防止 Streamlit toolbar 遮挡
st.markdown("""
<style>
.block-container { padding-top: 3.5rem !important; padding-bottom: 2rem !important; }
[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)

# 确保数据库初始化
db.init_db()


# ============ 登录检查 ============
def require_login():
    """老师登录守卫"""
    if "teacher" not in st.session_state or not st.session_state.teacher:
        st.warning("请先登录老师后台")
        st.markdown("👈 请点击左侧导航的「📊 老师后台」登录")
        st.stop()
    return st.session_state.teacher


teacher = require_login()


# ============ 页面头部 ============
st.markdown(f"# 📖 阅读理解管理(侦探闯关)")
st.caption(f"老师:{teacher['display_name']} · 管理阅读理解课文 + 侦探闯关题库")
st.markdown("---")


# ============ 主功能区 ============
tab_list, tab_create, tab_import = st.tabs([
    "📚 现有课文",
    "➕ 创建新课文",
    "📥 导入侦探闯关 JSON"
])


# ============ Tab 1:现有课文列表 ============
with tab_list:
    st.markdown("### 现有阅读理解课文")
    
    lessons = db.list_reading_lessons(only_published=False)
    
    if not lessons:
        st.info("还没有添加任何阅读理解课文。请到「➕ 创建新课文」或「📥 导入 JSON」添加。")
    else:
        st.caption(f"共 {len(lessons)} 篇课文")
        
        for lesson in lessons:
            with st.container(border=True):
                col1, col2, col3 = st.columns([5, 2, 2])
                
                with col1:
                    publish_status = "✅ 已发布" if lesson['is_published'] else "📝 草稿"
                    st.markdown(f"**《{lesson['title_cn']}》** · {publish_status}")
                    st.caption(
                        f"📚 {lesson['grade'] or '—'} · "
                        f"{lesson['unit'] or '—'} · "
                        f"{lesson['lesson_no'] or '—'}  |  "
                        f"文体:{lesson['lesson_type'] or '记叙文'}  |  "
                        f"📝 {lesson['total_questions']} 题"
                    )
                
                with col2:
                    if lesson['is_published']:
                        if st.button("📝 设为草稿", key=f"unpub_{lesson['id']}", use_container_width=True):
                            db.toggle_reading_lesson_publish(lesson['id'], False)
                            st.rerun()
                    else:
                        if st.button("✅ 发布", key=f"pub_{lesson['id']}", type="primary", use_container_width=True):
                            db.toggle_reading_lesson_publish(lesson['id'], True)
                            st.rerun()
                
                with col3:
                    if st.button("🗑️ 删除", key=f"del_{lesson['id']}", use_container_width=True):
                        if st.session_state.get(f"confirm_del_{lesson['id']}"):
                            db.delete_reading_lesson(lesson['id'])
                            st.success(f"已删除《{lesson['title_cn']}》")
                            st.session_state[f"confirm_del_{lesson['id']}"] = False
                            st.rerun()
                        else:
                            st.session_state[f"confirm_del_{lesson['id']}"] = True
                            st.warning("再点一次「删除」确认")
                
                # 展开查看完整内容
                with st.expander("📄 查看课文 JSON"):
                    full = db.get_reading_lesson(lesson['id'])
                    if full:
                        st.json(full, expanded=False)


# ============ Tab 2:创建新课文 ============
with tab_create:
    st.markdown("### 创建新阅读理解课文")
    st.caption("先填写基本信息和完整内容 JSON,即可创建一篇新课文")
    
    with st.form("create_reading_lesson"):
        col1, col2 = st.columns(2)
        with col1:
            title_cn = st.text_input("课文中文标题 *", placeholder="例如:恐怖事件")
            grade = st.text_input("年级", placeholder="例如:Sec 2")
            unit = st.text_input("单元", placeholder="例如:单元四")
        with col2:
            title_en = st.text_input("英文标题", placeholder="例如:The Horror Incident")
            lesson_no = st.text_input("第几课", placeholder="例如:第三课")
            lesson_type = st.selectbox(
                "文体",
                options=["记叙文", "说明文", "议论文", "散文"],
                index=0
            )
        
        source = st.text_input(
            "课文出处",
            placeholder="例如:原文｜《友谊前的恐怖事件》(改编) · Adapted"
        )
        
        st.markdown("---")
        st.markdown("**完整课文 JSON**(含 story / terms / quiz 三个部分)")
        st.caption("提示:可以先空着保存草稿,后续在「📥 导入 JSON」补充内容")
        
        content_json_text = st.text_area(
            "JSON 内容",
            height=300,
            placeholder='{\n  "story": {"title": "...", "paragraphs": [...]},\n  "terms": {...},\n  "quiz": [...]\n}',
            help="格式参考:detective_template.html 配套的 kongbushijian_complete.json"
        )
        
        submitted = st.form_submit_button("✅ 创建课文", type="primary", use_container_width=True)
        
        if submitted:
            if not title_cn:
                st.error("课文中文标题不能为空")
            else:
                # 校验 JSON
                content_dict = None
                if content_json_text.strip():
                    try:
                        content_dict = json.loads(content_json_text)
                    except json.JSONDecodeError as e:
                        st.error(f"❌ JSON 格式错误: {e}")
                        st.caption("提示:可以先空着创建,后续在「导入 JSON」补充")
                        st.stop()
                
                # 没有 JSON 就给个空壳
                if content_dict is None:
                    content_dict = {"story": {"title": title_cn, "paragraphs": []}, "terms": {}, "quiz": []}
                
                # 创建课文
                lesson_id = db.create_reading_lesson(
                    title_cn=title_cn,
                    title_en=title_en or "",
                    source=source or "",
                    grade=grade or "",
                    unit=unit or "",
                    lesson_no=lesson_no or "",
                    lesson_type=lesson_type,
                    content_json=json.dumps(content_dict, ensure_ascii=False),
                    teacher_id=teacher['teacher_id']
                )
                
                if lesson_id:
                    st.success(f"✅ 创建成功!课文 ID = {lesson_id}")
                    st.balloons()
                    st.info("回到「📚 现有课文」标签查看,或在「📥 导入 JSON」继续完善内容")
                else:
                    st.error("创建失败,请重试")


# ============ Tab 3:导入完整 JSON ============
with tab_import:
    st.markdown("### 导入侦探闯关完整 JSON")
    st.caption("把 Claude 给你的完整阅读理解课文 JSON 一次性粘贴进来,系统自动识别")
    
    st.markdown("---")
    
    # 选课文
    lessons = db.list_reading_lessons(only_published=False)
    if not lessons:
        st.warning("还没有课文。请先到「➕ 创建新课文」创建一个空课文,再来这里导入完整 JSON。")
    else:
        lesson_options = {
            f"{l['title_cn']} ({l['grade']} · {l['unit']} · {l['lesson_no']})": l['id']
            for l in lessons
        }
        selected_label = st.selectbox(
            "选择要导入到哪个课文",
            options=list(lesson_options.keys())
        )
        selected_lesson_id = lesson_options[selected_label]
        
        json_text = st.text_area(
            "粘贴完整 JSON 内容",
            height=400,
            placeholder='{\n  "lesson_meta": {...},\n  "story": {"title": "...", "paragraphs": [...]},\n  "terms": {...},\n  "quiz": [...]\n}',
            help="必须是合法 JSON,以 { 开头 } 结尾"
        )
        
        if st.button("📥 导入到上面选中的课文", type="primary", use_container_width=True):
            if not json_text.strip():
                st.error("请先粘贴 JSON 内容")
            else:
                # 4 层 JSON 容错解析(参考 cilang-platform 主程序的做法)
                content_dict = None
                error_msgs = []
                
                # 第 1 层:直接解析
                try:
                    content_dict = json.loads(json_text)
                except json.JSONDecodeError as e:
                    error_msgs.append(f"直接解析失败:{e}")
                
                # 第 2 层:去 markdown 代码块包裹
                if content_dict is None:
                    cleaned = json_text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                    if cleaned.endswith("```"):
                        cleaned = cleaned.rsplit("```", 1)[0]
                    try:
                        content_dict = json.loads(cleaned.strip())
                    except json.JSONDecodeError as e:
                        error_msgs.append(f"清理 markdown 后解析失败:{e}")
                
                # 第 3 层:正则提取最外层 {} 或 []
                if content_dict is None:
                    import re
                    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', json_text)
                    if match:
                        try:
                            content_dict = json.loads(match.group(1))
                        except json.JSONDecodeError as e:
                            error_msgs.append(f"正则提取后解析失败:{e}")
                
                if content_dict is None:
                    st.error("❌ JSON 格式错误,请检查:")
                    for msg in error_msgs:
                        st.caption(f"• {msg}")
                    st.info("💡 提示:常见错误是字符串里出现了英文双引号 \"...\",请改成中文 「...」")
                # ===== 格式守卫：阅读理解 JSON 必须是字典，且含 story/quiz =====
                # 拦住"词语闯关题库"（数组格式）被误导入到阅读理解，
                # 否则后面 content_dict.get(...) 会对 list 报 AttributeError 整页崩溃。
                elif not isinstance(content_dict, dict):
                    st.error("❌ 这不是阅读理解课文 JSON。")
                    st.info(
                        "💡 你粘贴的是一个**数组**（以 `[` 开头），这是「词语闯关题库」的格式，"
                        "应该到「📚 题库管理」导入。\n\n"
                        "阅读理解课文必须是**字典**（以 `{` 开头），包含 story / terms / quiz 三个部分。"
                    )
                elif 'story' not in content_dict and 'quiz' not in content_dict:
                    st.error("❌ JSON 里没有找到 story 或 quiz 字段，无法作为阅读理解课文导入。")
                    st.info(
                        "💡 阅读理解课文 JSON 必须包含 `story`（课文段落）和 `quiz`（闯关题目）。"
                        "请确认你粘贴的是「侦探闯关」课文，而不是词语闯关题库或其他内容。"
                    )
                else:
                    # 写入数据库
                    db.update_reading_lesson_content(
                        lesson_id=selected_lesson_id,
                        content_json=json.dumps(content_dict, ensure_ascii=False)
                    )
                    
                    # 统计
                    story_paragraphs = len(content_dict.get('story', {}).get('paragraphs', []))
                    terms_count = len(content_dict.get('terms', {}))
                    quiz = content_dict.get('quiz', [])
                    total_q = sum(len(p.get('questions', [])) for p in quiz)
                    
                    st.success(f"✅ 导入成功!")
                    st.caption(
                        f"课文段落:{story_paragraphs} 段 | "
                        f"术语词典:{terms_count} 个 | "
                        f"题目:{total_q} 道(分 {len(quiz)} 阶段)"
                    )
                    st.balloons()
                    
                    if not selected_label.endswith("(已发布)"):
                        st.info("💡 提示:课文还是草稿状态,记得在「📚 现有课文」标签把它发布给学生")


# ============ 底部说明 ============
st.markdown("---")
with st.expander("📘 怎么用?"):
    st.markdown("""
**典型工作流(以《恐怖事件》为例):**

1. **创建课文** - 在「➕ 创建新课文」填基本信息(标题、年级、单元),JSON 内容可以暂时空着
2. **导入题目** - 切到「📥 导入侦探闯关 JSON」,选刚创建的课文,粘贴完整 JSON
3. **发布课文** - 回到「📚 现有课文」,点「✅ 发布」让学生可见
4. **学生闯关** - 学生在「📖 核心课文」选课文,进入侦探闯关

**JSON 格式参考**:

```json
{
  "lesson_meta": {
    "title_cn": "课文标题",
    "title_en": "English Title",
    "source": "原文出处"
  },
  "story": {
    "title": "课文标题",
    "paragraphs": ["第1段...", "第2段..."]
  },
  "terms": {
    "诡异": {"en": "Strange, eerie"},
    "委婉": {"en": "Tactful, indirect"}
  },
  "quiz": [
    {
      "phase": "phase-1",
      "phaseName": "第一案:鸟瞰全局",
      "questions": [
        {"id": "Q1", "type": "choice", "prompt": "...", "options": [...], "correct": 1}
      ]
    }
  ]
}
```

**常见错误**:
- ❌ JSON 字符串里用英文双引号 `"..."` → 改用中文 `「...」`
- ❌ 中文逗号 `,` 误当英文 → JSON 结构必须用英文 `,`
- ❌ 末尾多了逗号 → JSON 不允许末尾逗号
""")

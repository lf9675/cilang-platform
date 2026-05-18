"""
pages/4_🕵️_核心课文.py - 学生侦探闯关入口（引导页 + 提交页）
"""

import streamlit as st
import database as db
from detective_utils import verify_completion_code

# ⚠️ 与 app.py 中的常量保持一致
HORROR_INCIDENT_LESSON_ID = 4
DETECTIVE_HTML_URL = "https://lf9675.github.io/cilang-platform/templates/%E6%81%90%E6%80%96%E4%BA%8B%E4%BB%B6-%E4%BE%A6%E6%8E%A2%E9%97%AF%E5%85%B3v7.html"

st.set_page_config(
    page_title="侦探闯关 · 恐怖事件",
    page_icon="🕵️",
    layout="centered"
)

st.markdown("""
<style>
.block-container { padding-top: 3.5rem !important; }
.stApp { background: linear-gradient(135deg, #fafbf6 0%, #f0f7f4 100%); }
</style>
""", unsafe_allow_html=True)

db.init_db()

# 检查学生是否已登录
if "student_info" not in st.session_state or not st.session_state.student_info:
    st.warning("⚠️ 请先回到首页登录。")
    if st.button("← 返回首页", type="primary"):
        st.switch_page("app.py")
    st.stop()

info = st.session_state.student_info
class_name = info["class_name"]
student_id = info["student_id"]
student_name = info["student_name"]

# 视图切换：guide / submit
view = st.session_state.get("detective_view", "guide")

# ==================== 引导页 ====================
if view == "guide":
    st.markdown("# 🕵️ 《恐怖事件》· 侦探闯关")
    st.caption(f"侦探 {student_name} · 班级 {class_name} · 学号 {student_id}")
    
    with st.container(border=True):
        st.markdown("""
        ### 你将进入独立的侦探闯关页面
        
        完成 **24 个案件**，争取集齐 **5 个能力徽章**：
        
        - 🎯 **鸟瞰全局** — 把握课文整体结构
        - 🧠 **人物心理** — 理解角色反应
        - 🎨 **描写洞察** — 看懂作者的笔法
        - 💬 **言外之意** — 读出字面下的意思
        - ✍️ **作者观点** — 抓住课文中心思想
        
        ⏱️ **预计用时**：30-40 分钟
        
        完成后会显示一个 **完成码**（格式 `DT-XXXX-N`），请复制回来提交。
        """)
    
    # 检查已提交记录
    try:
        existing = db.get_detective_record(class_name, student_id, HORROR_INCIDENT_LESSON_ID)
    except Exception:
        existing = None
    
    if existing:
        with st.container(border=True):
            st.success(f"✅ 你之前已完成 · 徽章 {existing['badges_earned']}/5 · 自评 {existing['self_rating']}/5")
            st.caption(f"📝 你的总结：{existing['one_line_summary']}")
            st.caption(f"📅 提交时间：{existing['submitted_at']}")
    
    col1, col2 = st.columns(2)
    with col1:
        launch_url = f"{DETECTIVE_HTML_URL}?cls={class_name}&sid={student_id}&lid={HORROR_INCIDENT_LESSON_ID}"
        st.link_button(
            "🚀 开始闯关（新窗口）",
            launch_url,
            use_container_width=True,
            type="primary"
        )
    with col2:
        if st.button("📝 已完成,提交完成码", use_container_width=True):
            st.session_state.detective_view = "submit"
            st.rerun()
    
    st.markdown("---")
    if st.button("← 返回首页"):
        st.session_state.detective_view = "guide"
        st.switch_page("app.py")

# ==================== 提交页 ====================
elif view == "submit":
    st.markdown("# ✅ 提交侦探闯关成绩")
    st.caption(f"侦探 {student_name} · 班级 {class_name} · 学号 {student_id}")
    
    # 先查是否已提交
    try:
        existing = db.get_detective_record(class_name, student_id, HORROR_INCIDENT_LESSON_ID)
    except Exception:
        existing = None
    
    if existing:
        st.info(f"📋 你已经提交过！徽章 {existing['badges_earned']}/5 · 自评 {existing['self_rating']}/5")
        st.caption(f"📅 提交时间：{existing['submitted_at']}")
        st.caption(f"💡 如需重新提交（例如重做后徽章更多），请填下面表单。")
    
    with st.container(border=True):
        code_input = st.text_input(
            "📋 你的完成码",
            placeholder="例如：DT-7A2K-5",
            help="从侦探闯关结案页复制"
        ).strip().upper()
        
        rating = st.radio(
            "🎯 自评：你对《恐怖事件》的理解程度？",
            options=[5, 4, 3, 2, 1],
            format_func=lambda x: {
                5: "5 — 完全读懂，能讲给同学听",
                4: "4 — 大部分懂，少数地方需要再想",
                3: "3 — 一半懂一半不懂",
                2: "2 — 大部分不太理解",
                1: "1 — 我需要老师重新讲"
            }[x],
            index=None
        )
        
        summary = st.text_area(
            "✍️ 用一句话总结课文（不超过 30 字）",
            max_chars=60,
            placeholder="例如：通过两个女孩从冷战到友谊，说明交流能化解误会。"
        )
        
        col_a, col_b = st.columns(2)
        with col_a:
            submitted = st.button("✅ 提交", type="primary", use_container_width=True)
        with col_b:
            if st.button("← 返回引导页", use_container_width=True):
                st.session_state.detective_view = "guide"
                st.rerun()
    
    if submitted:
        if not code_input:
            st.error("❌ 请输入完成码")
            st.stop()
        if rating is None:
            st.error("❌ 请选择自评等级")
            st.stop()
        if not summary or len(summary.strip()) < 5:
            st.error("❌ 请认真写下你的总结（至少 5 个字）")
            st.stop()
        
        # 校验完成码
        is_valid, badges = verify_completion_code(
            code_input, class_name, student_id, HORROR_INCIDENT_LESSON_ID
        )
        
        if not is_valid:
            st.error("❌ 完成码无效。可能的原因：")
            st.caption("1️⃣ 完成码不是你自己的（每人都不一样）")
            st.caption("2️⃣ 复制时缺字符或多空格")
            st.caption("3️⃣ 闯关时输入的班级或学号 和 你登录用的不一致")
            st.stop()
        
        # 入库
        success, msg = db.save_detective_record(
            class_name, student_id, student_name,
            HORROR_INCIDENT_LESSON_ID, badges, code_input,
            rating, summary.strip()
        )
        
        if success:
            st.success(f"🎉 提交成功！徽章 {badges}/5 · 自评 {rating}/5")
            st.balloons()
            st.caption("你的总结已保存：" + summary.strip())
            if st.button("返回首页", type="primary"):
                st.session_state.detective_view = "guide"
                st.switch_page("app.py")
        else:
            st.error(msg)

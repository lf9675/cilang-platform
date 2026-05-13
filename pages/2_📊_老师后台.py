"""
pages/2_📊_老师后台.py
老师后台：登录、班级管理、查看学生数据
"""
import streamlit as st
import pandas as pd
import database as db
import auth

st.set_page_config(
    page_title="老师后台 · 词语闯关",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 防toolbar遮挡
st.markdown("""
<style>
.block-container { padding-top: 3rem !important; }
[data-testid="stHeader"] { background: transparent; }
.metric-card { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #e8ecef; }
</style>
""", unsafe_allow_html=True)

db.init_db()

# 强制登录
teacher = auth.require_teacher()
auth.teacher_logout_button()

st.title("📊 老师后台")
st.caption(f"当前老师：{teacher['display_name']}")

# 侧边栏：班级管理
with st.sidebar:
    st.markdown("## 📋 班级管理")
    st.caption("管理你负责的班级")

    classes = db.get_teacher_classes(teacher["teacher_id"])

    if classes:
        st.markdown("**你的班级：**")
        for cn in classes:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"- `{cn}`")
            with col2:
                if st.button("🗑", key=f"del_class_{cn}", help=f"移除 {cn}"):
                    db.remove_teacher_class(teacher["teacher_id"], cn)
                    st.rerun()
    else:
        st.info("请先添加班级")

    with st.form("add_class_form"):
        new_class = st.text_input("添加新班级", placeholder="例如：1A、2E3")
        if st.form_submit_button("➕ 添加班级", use_container_width=True):
            if new_class.strip():
                if db.add_teacher_class(teacher["teacher_id"], new_class.strip()):
                    st.success(f"已添加：{new_class.strip()}")
                    st.rerun()
                else:
                    st.error("添加失败")

    st.markdown("---")
    st.markdown("### 🔗 快速跳转")
    if st.button("📚 题库管理", use_container_width=True):
        st.switch_page("pages/3_📚_题库管理.py")
    if st.button("🏠 返回学生页", use_container_width=True):
        st.switch_page("app.py")


# ==================== 主区域 ====================

if not classes:
    st.warning("⚠️ 你还没有添加任何班级。请在左侧侧边栏添加你负责的班级（如 1A、2E3），添加后学生用这个班级名登录，你才能看到他们的数据。")
    st.stop()

# 标签页
tab0, tab1, tab2, tab3 = st.tabs(["🎯 本周整体", "📈 学生总表", "📊 班级错词统计", "📋 详细答题记录"])

with tab0:
    st.markdown("### 🎯 本周班级整体表现")
    st.caption("📅 周一 00:00 ~ 周日 23:59（新加坡时间）")

    cls_select = st.selectbox("选择班级", classes, key="t0_class")
    
    overall = db.get_class_overall_stats(cls_select)
    
    cols = st.columns(4)
    with cols[0]:
        st.metric("✅ 完成人数", f"{overall['completed_students']} 人")
    with cols[1]:
        st.metric("📚 覆盖课文", f"{overall['covered_lessons']} 课")
    with cols[2]:
        delta = overall['accuracy_delta']
        delta_str = f"+{delta}%" if delta > 0 else (f"{delta}%" if delta < 0 else None)
        st.metric("🎯 平均正确率", f"{overall['avg_accuracy']}%", delta_str)
    with cols[3]:
        st.metric("📊 上周对比", f"{overall['last_week_accuracy']}%", help="上周班级平均正确率")
    
    st.markdown("---")
    st.markdown("#### 🔥 本周错得最多的词（建议课堂重点讲）")
    
    if not overall['difficult_words']:
        st.info("本周还没有足够数据（需要至少 3 次答题才进入统计）")
    else:
        for i, w in enumerate(overall['difficult_words'], 1):
            emoji = "🔴" if w['error_rate'] >= 50 else ("🟡" if w['error_rate'] >= 30 else "🟢")
            cols = st.columns([1, 3, 2, 2])
            with cols[0]:
                st.markdown(f"### {emoji}")
            with cols[1]:
                st.markdown(f"**{w['word']}**")
            with cols[2]:
                st.markdown(f"错误率 **{w['error_rate']}%**")
            with cols[3]:
                st.caption(f"{w['attempts']} 次答题")
    
    st.markdown("---")
    st.markdown("#### 🏆 本周班级冠军榜（实时）")
    leaderboard = db.get_class_leaderboard(cls_select)
    
    award_labels = [
        ("wang", "🏆 闯关之王", "完成不同课文最多"),
        ("zhun", "🎯 答题最准", "答题正确率最高"),
        ("jinbu", "📈 进步之星", "比上周进步最多"),
        ("jianchi", "🌟 坚持小达人", "做题天数最多"),
        ("tiaozhan", "⚡ 挑战大师", "答对挑战关词语最多")
    ]
    
    award_cols = st.columns(5)
    for i, (key, label, desc) in enumerate(award_labels):
        with award_cols[i]:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(desc)
                items = leaderboard[key]
                if items:
                    name, value = items[0]
                    st.markdown(f"🥇 **{name}**")
                    st.caption(value)
                else:
                    st.caption("—")


with tab1:
    st.markdown("### 学生闯关记录")
    st.caption("每行是一个学生完成一次课文的成绩")

    # 过滤器
    col1, col2 = st.columns(2)
    with col1:
        class_filter = st.selectbox("选择班级", ["全部"] + classes, key="t1_class")
    with col2:
        # 取所有课文
        hierarchy = db.list_grades_units_lessons()
        lesson_options = ["全部"]
        lesson_id_map = {}
        for g in sorted(hierarchy.keys()):
            for u in sorted(hierarchy[g].keys()):
                for lid, lno, title in hierarchy[g][u]:
                    label = f"{g} · {u} · {lno} 《{title}》"
                    lesson_options.append(label)
                    lesson_id_map[label] = lid
        lesson_filter = st.selectbox("选择课文", lesson_options, key="t1_lesson")

    # 获取数据
    summary = db.get_class_summary(
        teacher_id=teacher["teacher_id"],
        class_name=class_filter if class_filter != "全部" else None,
        lesson_id=lesson_id_map.get(lesson_filter) if lesson_filter != "全部" else None
    )

    if not summary:
        st.info("还没有学生答题记录")
    else:
        df = pd.DataFrame(summary)
        # 整理显示
        df_display = df[["class_name", "student_id", "student_name", "lesson_label",
                         "total_steps", "correct_steps", "accuracy", "stars_earned", "completed_at"]].copy()
        df_display.columns = ["班级", "学号", "姓名", "课文", "总关数", "答对关数", "正确率%", "星星", "完成时间"]

        # 总览
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总答题次数", len(df))
        c2.metric("覆盖学生数", df[["class_name", "student_id"]].drop_duplicates().shape[0])
        c3.metric("平均正确率", f"{df['accuracy'].mean():.1f}%")
        c4.metric("总星星数", int(df["stars_earned"].sum()))

        st.markdown("---")
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # 导出
        csv = df_display.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 下载 CSV", csv, file_name=f"学生成绩_{class_filter}.csv", mime="text/csv")


with tab2:
    st.markdown("### 哪些词全班错得最多？")
    st.caption("帮助你决定课堂重点讲哪些词")

    lesson_filter2 = st.selectbox("选择课文（必选）", ["请选择..."] + lesson_options[1:], key="t2_lesson")

    if lesson_filter2 != "请选择...":
        stats = db.get_word_error_stats(
            teacher_id=teacher["teacher_id"],
            lesson_id=lesson_id_map.get(lesson_filter2)
        )

        if not stats:
            st.info("还没有学生在这一课答题")
        else:
            df = pd.DataFrame(stats)

            # 按词聚合（合并三关）
            agg = df.groupby("word").agg({
                "total_attempts": "sum",
                "wrong_attempts": "sum"
            }).reset_index()
            agg["error_rate"] = round(agg["wrong_attempts"] * 100 / agg["total_attempts"], 1)
            agg = agg.sort_values("error_rate", ascending=False)
            agg.columns = ["词语", "总答题次数", "答错次数", "错误率%"]

            # 高亮错误率高的词
            st.markdown("**🔴 错误率最高的 5 个词（建议课堂重点讲解）：**")
            top5 = agg.head(5)
            for _, row in top5.iterrows():
                emoji = "🔴" if row["错误率%"] >= 50 else "🟡" if row["错误率%"] >= 30 else "🟢"
                st.markdown(f"{emoji} **{row['词语']}** — 错误率 **{row['错误率%']}%** （{row['答错次数']}/{row['总答题次数']}）")

            st.markdown("---")
            st.markdown("**完整词语统计表：**")
            st.dataframe(agg, use_container_width=True, hide_index=True)

            # 按 step_type 拆分
            with st.expander("🔍 查看更细：每关错误率（词义/用法/挑战）"):
                df_detail = df.copy()
                step_label_map = {"meaning": "1·词义", "usage": "2·用法", "trap": "3·挑战"}
                df_detail["step_type"] = df_detail["step_type"].map(step_label_map)
                df_detail = df_detail.sort_values("error_rate", ascending=False)
                df_detail.columns = ["词语", "关卡", "答题次数", "答错次数", "错误率%"]
                st.dataframe(df_detail, use_container_width=True, hide_index=True)


with tab3:
    st.markdown("### 详细答题记录")
    st.caption("每一道题、每一个学生的具体选择")

    col1, col2 = st.columns(2)
    with col1:
        class_filter3 = st.selectbox("班级", ["全部"] + classes, key="t3_class")
    with col2:
        lesson_filter3 = st.selectbox("课文", lesson_options, key="t3_lesson")

    # 直接查 attempts 表
    with db.get_conn() as conn:
        c = conn.cursor()
        teacher_classes = db.get_teacher_classes(teacher["teacher_id"])
        if not teacher_classes:
            st.info("没有班级")
        else:
            placeholders = ",".join(["?"] * len(teacher_classes))
            params = list(teacher_classes)
            where_extra = ""
            if class_filter3 != "全部":
                where_extra += " AND a.class_name = ?"
                params.append(class_filter3)
            if lesson_filter3 != "全部":
                where_extra += " AND a.lesson_id = ?"
                params.append(lesson_id_map.get(lesson_filter3))

            query = f"""
                SELECT a.class_name, a.student_id, a.student_name, a.word,
                       a.step_type, a.is_correct,
                       a.chosen_content, a.correct_content,
                       a.answered_at,
                       l.title as lesson_title
                FROM attempts a
                JOIN lessons l ON a.lesson_id = l.lesson_id
                WHERE a.class_name IN ({placeholders}) {where_extra}
                ORDER BY a.answered_at DESC
                LIMIT 2000
            """
            c.execute(query, params)
            rows = [dict(r) for r in c.fetchall()]

            if not rows:
                st.info("没有答题记录")
            else:
                df = pd.DataFrame(rows)
                step_label_map = {"meaning": "1·词义", "usage": "2·用法", "trap": "3·挑战"}
                df["step_type"] = df["step_type"].map(step_label_map)
                df["is_correct"] = df["is_correct"].map({1: "✓", 0: "✗"})
                df_display = df[["class_name", "student_id", "student_name", "lesson_title",
                                 "word", "step_type", "is_correct",
                                 "chosen_content", "correct_content", "answered_at"]]
                df_display.columns = ["班级", "学号", "姓名", "课文", "词语", "关卡",
                                       "对错", "学生选了", "正确答案", "时间"]
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                st.caption(f"显示最近 {len(df_display)} 条记录")

"""
pages/3_📚_题库管理.py
老师管理课文和题库：增加课文 / 粘贴JSON入库 / 手动编辑题目
"""
import streamlit as st
import database as db
import auth
import json

st.set_page_config(
    page_title="题库管理 · 词语闯关",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.block-container { padding-top: 3rem !important; }
[data-testid="stHeader"] { background: transparent; }
.lesson-card { background: #fff; border-radius: 10px; padding: 12px; margin-bottom: 8px; border: 1px solid #e8ecef; }
</style>
""", unsafe_allow_html=True)

db.init_db()

teacher = auth.require_teacher()
auth.teacher_logout_button()

st.title("📚 题库管理")
st.caption(f"当前老师：{teacher['display_name']}")

with st.sidebar:
    st.markdown("### 🔗 快速跳转")
    if st.button("📊 老师后台", use_container_width=True):
        st.switch_page("pages/2_📊_老师后台.py")
    if st.button("🏠 学生入口", use_container_width=True):
        st.switch_page("app.py")
    st.markdown("---")
    st.markdown("### 📖 操作流程")
    st.caption("""
    1. 在「创建课文」添加 课文
    2. 在 Claude.ai 用出题Prompt生成 JSON
    3. 在「导入题库」粘贴 JSON
    4. 学生即可在课文选择页看到
    """)

# 标签页
tab1, tab2, tab3 = st.tabs(["📝 课文列表", "➕ 创建课文", "📥 导入/编辑题库"])

# ==================== Tab 1: 课文列表 ====================
with tab1:
    st.markdown("### 已有课文")

    hierarchy = db.list_grades_units_lessons()
    if not hierarchy:
        st.info("还没有创建任何课文，请到「创建课文」添加")
    else:
        for grade in sorted(hierarchy.keys()):
            with st.expander(f"📂 {grade}", expanded=True):
                for unit in sorted(hierarchy[grade].keys()):
                    st.markdown(f"**{unit}**")
                    for lid, lno, title in hierarchy[grade][unit]:
                        meta = db.get_questions_meta(lid)
                        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                        with col1:
                            st.markdown(f"📖 **{lno} 《{title}》** (ID: {lid})")
                        with col2:
                            if meta:
                                st.caption(f"✅ {meta['word_count']} 词 · {meta['step_count']} 关")
                            else:
                                st.caption("⚠️ 无题库")
                        with col3:
                            if st.button("✏️ 编辑", key=f"edit_{lid}"):
                                st.session_state["editing_lesson_id"] = lid
                                st.session_state["edit_tab"] = "tab3"
                                st.rerun()
                        with col4:
                            if st.button("🗑 删除", key=f"del_{lid}"):
                                st.session_state["confirm_delete_lesson"] = lid
                                st.rerun()

                        # 二次确认
                        if st.session_state.get("confirm_delete_lesson") == lid:
                            st.warning(f"确定要删除 《{title}》 吗？删除后学生的历史成绩会保留，但学生看不到这一课了。")
                            cc1, cc2, _ = st.columns([1, 1, 3])
                            with cc1:
                                if st.button("✅ 确定删除", key=f"do_del_{lid}", type="primary"):
                                    db.delete_lesson(lid)
                                    st.session_state.pop("confirm_delete_lesson", None)
                                    st.success("已删除")
                                    st.rerun()
                            with cc2:
                                if st.button("取消", key=f"cancel_del_{lid}"):
                                    st.session_state.pop("confirm_delete_lesson", None)
                                    st.rerun()
                    st.markdown("")


# ==================== Tab 2: 创建课文 ====================
with tab2:
    st.markdown("### 创建新课文")
    st.caption("先创建课文，再去「导入题库」添加题目")

    with st.form("create_lesson_form"):
        col1, col2 = st.columns(2)
        with col1:
            grade = st.selectbox("年级", ["Sec 1", "Sec 2"])
        with col2:
            unit_options = ["单元一", "单元二", "单元三", "单元四", "单元五", "单元六", "单元七", "单元八",
                            "单元九", "单元十", "单元十一", "单元十二"]
            unit = st.selectbox("单元", unit_options)

        col3, col4 = st.columns(2)
        with col3:
            lesson_no_options = ["第一课", "第二课", "第三课", "第四课", "第五课", "第六课",
                                  "第七课", "第八课", "第九课", "第十课"]
            lesson_no = st.selectbox("第几课", lesson_no_options)
        with col4:
            title = st.text_input("课文标题", placeholder="例如：培养好习惯")

        if st.form_submit_button("📝 创建课文", type="primary", use_container_width=True):
            if not title.strip():
                st.error("请输入课文标题")
            else:
                lid = db.create_lesson(grade, unit, lesson_no, title, teacher["teacher_id"])
                if lid:
                    st.success(f"✅ 已创建：{grade} · {unit} · {lesson_no} 《{title.strip()}》（ID: {lid}）")
                    st.info("接下来到「导入题库」给这一课添加题目")
                else:
                    st.error("创建失败，请检查信息")


# ==================== Tab 3: 导入/编辑题库 ====================
with tab3:
    st.markdown("### 导入题库")

    # 选择要编辑的课文
    hierarchy = db.list_grades_units_lessons()
    if not hierarchy:
        st.warning("还没有创建任何课文，请先到「创建课文」添加")
    else:
        lesson_options = []
        lesson_id_map = {}
        for g in sorted(hierarchy.keys()):
            for u in sorted(hierarchy[g].keys()):
                for lid, lno, title in hierarchy[g][u]:
                    label = f"{g} · {u} · {lno} 《{title}》"
                    lesson_options.append(label)
                    lesson_id_map[label] = lid

        # 如果是从「编辑」按钮跳过来的，默认选中
        default_idx = 0
        if "editing_lesson_id" in st.session_state:
            target_lid = st.session_state["editing_lesson_id"]
            for i, label in enumerate(lesson_options):
                if lesson_id_map[label] == target_lid:
                    default_idx = i
                    break
            del st.session_state["editing_lesson_id"]

        selected_label = st.selectbox("选择要导入题库的课文", lesson_options, index=default_idx)
        selected_lid = lesson_id_map[selected_label]

        # 显示现有题库
        existing = db.get_questions(selected_lid)
        if existing:
            st.success(f"✅ 这一课已有 **{len(existing)}** 个词语的题库")
            with st.expander("📋 查看现有题库（JSON格式，可复制修改）"):
                st.code(json.dumps(existing, ensure_ascii=False, indent=2), language="json")
        else:
            st.info("📝 这一课还没有题库，请粘贴 JSON 导入")

        st.markdown("---")
        st.markdown("#### 📋 步骤 1：在 Claude.ai 生成题库")

        with st.expander("📌 点击查看「出题Prompt」（复制到 Claude.ai 用）", expanded=False):
            st.markdown("**请把下面整段复制到 Claude.ai，然后把课文和词语填进去：**")
            prompt_text = """我是新加坡中学华文教师。请按照以下规范，给我出一份词语闯关题库（JSON格式）。

## 出题规范

每个词语包含三关（如果是简单词，可只出第三关）：

**第1关 词义**：测试学生是否理解词语的意思。3 个选项，干扰项必须是「望文生义」或「邻近概念混淆」（不能完全不沾边）。
**第2关 用法**：测试学生是否知道该词用在什么场合。3 个选项，干扰项必须是相似但不准确的场合。
**第3关 陷阱**：给三个句子让学生判断哪句用得对/错，干扰项必须是学生真实可能犯的错误（如：大词小用、搭配错误、近义词混用），不能太弱智。

## JSON 格式

```json
[
  {
    "word": "尴尬",
    "pinyin": "gān gà",
    "difficulty": "hard",
    "meaning": {
      "scene": "😅 🙈",
      "caption": "「这下怎么办……」",
      "prompt": "「尴尬」是什么感觉？",
      "options": ["很委屈，想哭", "处境为难，不好处理", "很害羞，脸红"],
      "correct": 1,
      "tip": "尴尬是「进退两难」的感觉，跟「害羞」不一样。"
    },
    "usage": {
      "prompt": "下面哪个最容易让人「尴尬」？",
      "options": ["在大家面前喊错了老师的名字", "上台领奖时被同学拍照", "第一次和喜欢的人说话"],
      "correct": 0,
      "tip": "「尴尬」是「进退两难、不知如何收场」。"
    },
    "trap": {
      "prompt": "下面哪一句最恰当？",
      "options": [
        "他在大家面前喊错了老师的名字，场面非常<u>尴尬</u>。",
        "第一次上台演讲，我紧张得很<u>尴尬</u>。",
        "被老师夸奖时，我害羞地觉得很<u>尴尬</u>。"
      ],
      "correct": 0,
      "whyCorrect": "A 句的「尴尬」用在「人际场合不好收场」，完全贴合词义。",
      "whyWrong": "B 句应该用「紧张」；C 句应该用「害羞」。",
      "remember": "尴尬 ≠ 紧张 ≠ 害羞。尴尬是「进退两难、不知怎么收场」。"
    }
  }
]
```

## 字段说明

- `word`: 词语本身
- `pinyin`: 拼音（声调用 ā á ǎ à 这种符号）
- `difficulty`: "hard"（出3关）或 "easy"（只出陷阱关）
- `meaning.scene`: 2-3 个 emoji 组成的情境画（简单词不需要）
- `meaning.caption`: 情境说明，用「」包人物对话
- `correct`: 正确答案的索引（从 0 开始）
- 选项里要点出来的词用 <u>词</u> 包起来（HTML 下划线）

## 干扰项设计原则（重要！）

✅ 好的干扰项：
- 「新颖」干扰项「全新的、没用过的」（混淆"新"和"新颖"）
- 「有效」干扰项「做事动作很快，效率高」（混淆"有效"和"高效"）
- 「友谊」干扰项「我和妹妹的友谊」（混淆"友谊"和"亲情"）

❌ 不能用的干扰项：
- 「光线照在金子上」（完全不沾边，太弱智）
- 「很开心」（明显错误，学生靠常识就排除）

## 我的课文信息

**课文标题**：[在这里填课文标题]

**课文内容**：
[在这里贴课文]

**要出题的词语**（标注难度）：
- [词1]（hard）
- [词2]（hard）
- [词3]（easy）

请按以上规范生成完整 JSON，只输出 JSON，不要其他说明文字。"""
            st.code(prompt_text, language="markdown")

        st.markdown("#### 📥 步骤 2：粘贴 JSON 导入")

        with st.form("import_questions_form"):
            json_input = st.text_area(
                "粘贴 Claude.ai 生成的 JSON",
                height=300,
                placeholder='[\n  {\n    "word": "...",\n    ...\n  }\n]',
                help="必须是完整的 JSON 数组"
            )
            submit_import = st.form_submit_button("✅ 导入题库", type="primary", use_container_width=True)

        if submit_import:
            if not json_input.strip():
                st.error("请粘贴 JSON 内容")
            else:
                # JSON 4 层解析（吸取华文通经验）
                parsed = None
                error_msgs = []

                # 第1层：直接解析
                try:
                    parsed = json.loads(json_input.strip())
                except json.JSONDecodeError as e:
                    error_msgs.append(f"直接解析失败：{e}")

                    # 第2层：去除 markdown 代码块
                    cleaned = json_input.strip()
                    if cleaned.startswith("```"):
                        # 去除 ```json 和 ```
                        lines = cleaned.split("\n")
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        cleaned = "\n".join(lines)
                    try:
                        parsed = json.loads(cleaned)
                    except json.JSONDecodeError as e2:
                        error_msgs.append(f"清理后解析失败：{e2}")

                        # 第3层：提取第一个 [...] 块
                        import re
                        match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", json_input)
                        if match:
                            try:
                                parsed = json.loads(match.group(0))
                            except json.JSONDecodeError as e3:
                                error_msgs.append(f"正则提取失败：{e3}")

                if parsed is None:
                    st.error("❌ JSON 格式错误，请检查：")
                    for msg in error_msgs:
                        st.caption(f"• {msg}")
                    st.info("💡 提示：直接从 Claude.ai 复制完整 JSON，包括开头的 `[` 和结尾的 `]`")
                elif not isinstance(parsed, list):
                    st.error("❌ JSON 必须是数组（以 `[` 开头）")
                elif len(parsed) == 0:
                    st.error("❌ 题库不能为空")
                else:
                    # 验证基本字段
                    invalid = []
                    for i, q in enumerate(parsed):
                        if not isinstance(q, dict):
                            invalid.append(f"第 {i+1} 个不是对象")
                            continue
                        if "word" not in q or "trap" not in q:
                            invalid.append(f"第 {i+1} 个缺少 word 或 trap")
                            continue
                        # 检查 trap
                        trap = q["trap"]
                        if "options" not in trap or "correct" not in trap:
                            invalid.append(f"第 {i+1} 个 ({q.get('word', '?')}) 的 trap 不完整")
                        if "difficulty" not in q:
                            q["difficulty"] = "hard"
                        if q.get("difficulty") == "hard":
                            if "meaning" not in q or "usage" not in q:
                                invalid.append(f"第 {i+1} 个 ({q.get('word', '?')}) 是难词但缺少 meaning 或 usage")

                    if invalid:
                        st.error("❌ 题库格式不完整：")
                        for v in invalid:
                            st.caption(f"• {v}")
                    else:
                        ok, msg = db.save_questions(selected_lid, parsed, teacher["teacher_id"])
                        if ok:
                            st.success(f"✅ {msg}")
                            st.balloons()
                            # 显示预览
                            with st.expander("📋 预览导入的题库"):
                                for i, q in enumerate(parsed):
                                    diff = "🔴 难" if q.get("difficulty") == "hard" else "🟢 简"
                                    st.markdown(f"**{i+1}. {q['word']}** {diff}")
                        else:
                            st.error(msg)

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
                        with st.container(border=True):
                            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                            with col1:
                                st.markdown(f"📖 **{lno} 《{title}》** (ID: {lid})")
                            with col2:
                                if meta:
                                    st.caption(f"✅ {meta['word_count']} 词 · {meta['step_count']} 关")
                                else:
                                    st.caption("⚠️ 无题库")
                            with col3:
                                edit_key = f"editing_open_{lid}"
                                is_editing = st.session_state.get(edit_key, False)
                                btn_label = "❌ 关闭" if is_editing else "✏️ 编辑"
                                if st.button(btn_label, key=f"edit_{lid}", use_container_width=True):
                                    st.session_state[edit_key] = not is_editing
                                    st.rerun()
                            with col4:
                                if st.button("🗑 删除", key=f"del_{lid}", use_container_width=True):
                                    st.session_state["confirm_delete_lesson"] = lid
                                    st.rerun()

                            # 二次确认删除
                            if st.session_state.get("confirm_delete_lesson") == lid:
                                st.warning(f"确定要删除 《{title}》 吗？删除后学生的历史成绩会保留，但学生看不到这一课了。")
                                cc1, cc2, _ = st.columns([1, 1, 3])
                                with cc1:
                                    if st.button("✅ 确定删除", key=f"do_del_{lid}", type="primary"):
                                        db.delete_lesson(lid)
                                        st.session_state.pop("confirm_delete_lesson", None)
                                        st.session_state.pop(f"editing_open_{lid}", None)
                                        st.success("已删除")
                                        st.rerun()
                                with cc2:
                                    if st.button("取消", key=f"cancel_del_{lid}"):
                                        st.session_state.pop("confirm_delete_lesson", None)
                                        st.rerun()

                            # 内嵌编辑区
                            if st.session_state.get(f"editing_open_{lid}", False):
                                st.markdown("---")
                                st.markdown(f"### ✏️ 编辑 《{title}》 的题库")

                                existing = db.get_questions(lid)
                                if existing:
                                    import json as _json
                                    current_json = _json.dumps(existing, ensure_ascii=False, indent=2)
                                    st.success(f"✅ 当前题库有 **{len(existing)}** 个词语")
                                else:
                                    current_json = ""
                                    st.info("📝 这一课还没有题库，请在下方粘贴 JSON")

                                edit_text_key = f"edit_json_{lid}"
                                edited_json = st.text_area(
                                    "📋 直接修改下面的 JSON，然后点「💾 保存修改」",
                                    value=current_json,
                                    height=400,
                                    key=edit_text_key,
                                    help="可以直接在这里改题目、改解释、改正确答案等"
                                )

                                btn_cols = st.columns([1, 1, 2])
                                with btn_cols[0]:
                                    if st.button("💾 保存修改", key=f"save_{lid}", type="primary", use_container_width=True):
                                        if not edited_json.strip():
                                            st.error("❌ 内容不能为空")
                                        else:
                                            # 用同样的 4 层 JSON 解析逻辑
                                            import json as _json
                                            import re as _re
                                            parsed = None
                                            try:
                                                parsed = _json.loads(edited_json.strip())
                                            except _json.JSONDecodeError:
                                                cleaned = edited_json.strip()
                                                if cleaned.startswith("```"):
                                                    lines = cleaned.split("\n")
                                                    if lines[0].startswith("```"):
                                                        lines = lines[1:]
                                                    if lines and lines[-1].strip() == "```":
                                                        lines = lines[:-1]
                                                    cleaned = "\n".join(lines)
                                                try:
                                                    parsed = _json.loads(cleaned)
                                                except _json.JSONDecodeError:
                                                    match = _re.search(r"\[\s*\{[\s\S]*\}\s*\]", edited_json)
                                                    if match:
                                                        try:
                                                            parsed = _json.loads(match.group(0))
                                                        except _json.JSONDecodeError:
                                                            pass

                                            if parsed is None:
                                                st.error("❌ JSON 格式错误，请检查括号是否匹配、引号是否成对")
                                            elif not isinstance(parsed, list) or len(parsed) == 0:
                                                st.error("❌ JSON 必须是非空数组（以 `[` 开头）")
                                            else:
                                                ok, msg = db.save_questions(lid, parsed, teacher["teacher_id"])
                                                if ok:
                                                    st.success(f"✅ {msg}")
                                                    st.balloons()
                                                    # 不关闭编辑窗口，方便继续修改
                                                else:
                                                    st.error(msg)
                                with btn_cols[1]:
                                    if st.button("👁 预览当前", key=f"preview_{lid}", use_container_width=True):
                                        st.session_state[f"show_preview_{lid}"] = not st.session_state.get(f"show_preview_{lid}", False)
                                        st.rerun()

                                # 预览模式
                                if st.session_state.get(f"show_preview_{lid}", False) and existing:
                                    st.markdown("---")
                                    st.markdown("**📋 当前题库预览**")
                                    for i, q in enumerate(existing, 1):
                                        diff = "🔴 难" if q.get("difficulty") == "hard" else "🟢 简"
                                        st.markdown(f"**{i}. {q['word']}** {diff}")
                                        with st.expander(f"展开看 {q['word']} 的题目"):
                                            st.json(q)
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
            prompt_text = """我是新加坡中学华文教师。请根据我提供的课文，给我出一份词语闯关题库（JSON 格式）。

## 教学目标

让学生学会：
1. **从课文上下文推测词义**（培养真实阅读能力）
2. **从构词角度拆解词语**（培养举一反三能力）

学生**不是来背词义**的，是来学会**怎么自己猜词**的。

## 学生背景

- 新加坡中学华文 Higher Chinese 学生
- 中等及偏弱程度
- **不喜欢读长文字**，所以解释要短、要分块、要用图标
- 例句要贴近新加坡学生生活：MRT、组屋、食阁、邻里学校、华人新年
- 不要用中国大陆才有的事物（高铁、外卖小哥、双11、北京天津）
- 避免文言、太书面的表达
- 不讲古汉语字源（不要说"诲字从言从每"），只讲字面意思

## ⚠️ 四个最重要的原则

### 🎲 原则 1：正确答案必须随机分布

出完所有题后，请数一数 `correct` 字段的分布：
- A 选项（correct: 0）占比 25-40%
- B 选项（correct: 1）占比 25-40%
- C 选项（correct: 2）占比 25-40%

禁止：默认放 A、连续 3 题同位置、某位置 > 50%。

**方法**：每出一题，先想好正确选项内容，再随机选 0/1/2 决定位置。

### 📚 原则 2：选项情境要多样化

- 每个词的所有选项中，课文情境最多 1-2 个
- 其他来自：家庭、学校、邻里、节庆、兴趣
- 三关共 9 选项，课文情境占 2-3 个，课外占 6-7 个

### 🧩 原则 3：第 1 关「词义关」是构词推理或语境推理

#### 方式 A：构词推理（适合合成词：师恩、教诲、勤奋、慈祥）

```
课文里说：「[贴课文一句话]」

「[词语]」这个词，「[字1]」是 [字1意思]，「[字2]」是 [字2意思]。
两个字合起来，意思最接近：
A. [选项]
B. [选项]
C. [选项]
```

构词分析只到字面意思，不讲字源。

#### 方式 B：语境推理（适合成语、抽象词：一帆风顺、谆谆、启迪）

```
课文里有句话：「[贴完整课文句子]」

从这句话推测，「[词语]」最可能是什么意思？
```

#### 选哪种？

| 词语类型 | 推荐方式 |
|---|---|
| 两字合成词 | 方式 A 构词推理 |
| 四字成语 | 方式 B 语境推理 |
| 抽象词 | 方式 B 语境推理 |
| 简单具象词（easy） | 跳过此关 |

### 🎨 原则 4：tip 用图标分块的短句格式（v5 重点！）

**这是这次升级的核心。** 学生不爱读长文字，所以所有 `tip`、`whyCorrect`、`whyWrong`、`remember` 字段都用**图标分块短句**格式：

#### 五种图标：

| 图标 | 含义 | 用法 |
|---|---|---|
| 🧩 | 拆字 | `🧩 教=教导，诲=教导 → 反复教导` |
| 🔗 | 同类词 | `🔗 同类词：训诲、教训` |
| 💡 | 猜词窍门 | `💡 看到"难忘"就知道是好印象` |
| ⚠️ | 易错点 | `⚠️ 别和"批评"混用` |
| ✨ | 一句话记住 | `✨ 教诲 = 长辈讲做人道理` |

#### tip 格式规则（必须严格遵守）：

1. **每行一个图标 + 一句话**（不超过 15 个字）
2. **每个 tip 最多 3 行**
3. **每行用 
 分隔**（JSON 里写 `
`）
4. **不要写完整长句**，要短、要直接、要好懂

#### 例子对比：

❌ **错误的 tip（v4 旧版，太长）**：
```
"拆开来看：「教」是教导，「诲」也是教导。合起来就是「反复地、耐心地教导」。同类词：「训诲」「教训」，都跟"教"字一样有"教导"的意思。"
```

✅ **正确的 tip（v5 新版，短而清晰）**：
```
"🧩 教=教导，诲=教导 → 反复教导
🔗 同类词：训诲、教训
✨ 教诲 = 长辈反复教导"
```

### whyCorrect 和 whyWrong 字段也要短

❌ 错误（太长）：
```
"whyCorrect": "B 句用「教诲」描述长辈对晚辈讲做人道理，完全贴合词义。"
"whyWrong": "A 句「拿作业本」是日常小事，用「教诲」太严肃，应该用「叫」；C 句同学之间不能用「教诲」，应该用「教」或「帮我改」。"
```

✅ 正确（短而清晰）：
```
"whyCorrect": "✅ 长辈讲做人道理 = 教诲"
"whyWrong": "❌ A：日常小事不用「教诲」
❌ C：同学之间不用「教诲」"
```

### remember 字段一句话总结

❌ 错误（太长）：
```
"remember": "教诲 = 长辈/老师 + 做人做事的道理。同学之间、日常小事都不用「教诲」。"
```

✅ 正确（一句话）：
```
"remember": "✨ 教诲 = 长辈/老师讲做人道理"
```

## 出题规范

每个 hard 词出三关，easy 词只出第三关：

**第1关 词义（meaning）**：构词推理或语境推理。

**第2关 用法（usage）**：3 个场合来自不同领域。

**第3关 陷阱（trap）**：3 个句子来自不同场景，干扰项是学生真实可能犯的错误。

## JSON 格式（v5 图标版）

```json
[
  {
    "word": "教诲",
    "pinyin": "jiào huì",
    "difficulty": "hard",
    "meaning": {
      "scene": "👨‍🏫 💡",
      "caption": "「老师又一次告诉我们……」",
      "prompt": "课文里说：「老师对我们的教诲，至今难忘。」

「教诲」这个词，「教」是教导，「诲」也是教导。
两个字合起来，意思最接近：",
      "options": ["教师上课的内容", "老师反复给学生的教导启发", "老师对学生的批评"],
      "correct": 1,
      "tip": "🧩 教=教导，诲=教导 → 反复教导
🔗 同类词：训诲、教训
✨ 教诲 = 长辈反复教导"
    },
    "usage": {
      "prompt": "下面哪个最适合用「教诲」？",
      "options": [
        "妈妈让我去食阁买晚餐",
        "外婆经常告诉我做人要诚实善良",
        "数学老师在白板上写公式"
      ],
      "correct": 1,
      "tip": "✨ 教诲 = 长辈讲做人道理
⚠️ 不用在日常小事上"
    },
    "trap": {
      "prompt": "下面哪一句最恰当？",
      "options": [
        "老师叫我去办公室拿作业本，这是一次<u>教诲</u>。",
        "爷爷常常<u>教诲</u>我，做人要懂得感恩。",
        "我把功课交给同学批改，他<u>教诲</u>我改正错误。"
      ],
      "correct": 1,
      "whyCorrect": "✅ 长辈讲做人道理 = 教诲",
      "whyWrong": "❌ A：日常小事不用「教诲」
❌ C：同学之间不用「教诲」",
      "remember": "✨ 教诲 = 长辈/老师讲做人道理"
    }
  }
]
```

注意例子：
- meaning.tip：3 行图标短句
- usage.tip：2 行图标短句
- whyCorrect：1 行 ✅ 短句
- whyWrong：2 行 ❌ 短句（每个错误选项一行）
- remember：1 行 ✨ 总结

## 字段说明

- `word`: 词语本身
- `pinyin`: 拼音（声调用 ā á ǎ à）
- `difficulty`: "hard" 或 "easy"
- `meaning.scene`: 2-3 个 emoji
- `correct`: 0/1/2
- 选项里要点出的词用 `<u>词</u>`

## 干扰项设计原则

### ✅ 好的干扰项

- 近义词混用（新颖 vs 新；有效 vs 高效）
- 大词小用（"一诺千金"配"洗一次碗"）
- 搭配错误（"维护健康"应是"保持健康"）
- 逻辑矛盾（"一帆风顺"配"千辛万苦"）

### ❌ 坏的干扰项

- 完全不沾边（"光线照在金子上"）
- 明显错误（"很开心"作为成语意思）

## 出题前检查清单

在生成 JSON 之前，请先列一张表：

| 词语 | 难度 | 方式 | meaning位置 | usage位置 | trap位置 |
|---|---|---|---|---|---|
| 词1 | hard | 构词 | B | A | C |
| 词2 | hard | 语境 | A | C | B |

确保 A/B/C 三个位置数量均匀。

---

## 我的课文

**课文标题**：[在这里填]

**年级和单元**：[例如：Sec 1 单元二 第三课]

**课文全文**：
[在这里贴课文全文]

**要出题的词语**：

| # | 词语 | 难度 |
|---|---|---|
| 1 | [词1] | hard |
| 2 | [词2] | hard |

---

请按以上规范，生成完整的 JSON 数组。要求：

1. **只输出 JSON**，不要任何说明文字
2. JSON 以 `[` 开头，`]` 结尾
3. 所有字段名用英文双引号
4. `correct` 是数字（0/1/2）
5. 选项数量保持 3 个
6. **所有 tip / whyCorrect / whyWrong / remember 都用图标短句格式**
7. 每行用 `
` 分隔（JSON 字符串内）
8. 出完后自己数 A/B/C 分布，某位置超 50% 请重调"""
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

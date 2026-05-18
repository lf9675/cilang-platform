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
    if st.button("👁 以学生身份预览", use_container_width=True, help="看学生看到什么"):
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
            # 每个单元只有 4 篇课文（v7 修正：原本有 10 课，与教材实际不符）
            lesson_no_options = ["第一课", "第二课", "第三课", "第四课"]
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
            prompt_text = """我是新加坡中学华文教师，30 年教学经验。请根据我提供的课文，给我出一份词语闯关题库（JSON 格式）。

# 教学目标

让学生学会：
1. **从课文上下文推测词义**（培养真实阅读能力）
2. **从构词角度拆解词语**（培养举一反三能力）
3. **避免新加坡学生五大典型偏误**（针对性巩固）

学生**不是来背词义**的，是来学会**怎么自己猜词、避免常见错误**。

# 学生背景

- 新加坡中学华文 Higher Chinese 学生
- 中等及偏弱程度
- 英语是主导语言，写华文时常受英语思维干扰
- 例句要贴近新加坡学生生活：MRT、组屋、食阁、邻里学校、华人新年、社区图书馆
- 不要用中国大陆才有的事物（高铁、外卖小哥、双11、北京天津）
- 避免文言、太书面的表达
- 不讲古汉语字源（不要说"诲字从言从每"），只讲字面意思

# 🎯 核心升级：干扰项必须基于新加坡学生五大偏误库

**这是 v7 最重要的原则。** 不要凭空想象干扰项，必须从以下五大偏误库选取。

## 📚 五大偏误库（新加坡学生真实错误）

### 偏误 1：英语负迁移（直译式搭配）

英语主导的学生会把英文词组逐字硬译成华文：

| 错误（直译） | 正确（华文规范） | 英文源头 |
|---|---|---|
| 拿考试 | 参加考试 / 应考 | take an exam |
| 减少压力 | 减轻 / 缓解压力 | reduce stress |
| 见医生 | 看医生 / 看病 | see a doctor |
| 我的英文很重 | 我的英文口音很重 | heavy accent |
| 做朋友 | 交朋友 | make friends |
| 开始一个公司 | 创办一家公司 | start a company |
| 严重的问题 | 严峻的问题 | serious problem |

**用作干扰项的方法**：把目标词的正确搭配，改成"英语直译"的错误搭配。

### 偏误 2：本土口语方言泛化（万能量词）

新加坡学生受方言影响，量词高度简化：

- 「一**粒**」乱用：一粒西瓜、一粒气球、一粒太阳（应是"个"）
- 「一**只**」乱用：一只船、一只车（应是"艘/辆"）
- 「一**个**」万能化：一个建议、一个想法（有些应是"条/项/份"）

**用作干扰项的方法**：在选项里故意用错量词，看学生能否识别。

### 偏误 3：近义词/关联词混淆（O Level Paper 2 重灾区！）

一词多译导致的混淆——这是新加坡 O Level 失分最严重的部分：

| 易混词对 | 区别 | 学生常犯错误 |
|---|---|---|
| 或者 vs 还是 | 还是用于疑问句 | "你想去打球**或者**踢球？"（应是"还是"）|
| 反映 vs 反应 | 反映=表达；反应=回应 | "他的成绩**反应**了努力"（应是"反映"）|
| 怀疑 vs 疑惑 | 怀疑=不信任；疑惑=不明白 | "我对题目很**怀疑**"（应是"疑惑"）|
| 减少 vs 减轻 | 减少=数量；减轻=程度 | "**减少**压力"（应是"减轻"）|
| 看 vs 见 | 看=动作；见=看到 | "我**见**电影"（应是"看"）|
| 教导 vs 教训 vs 教诲 | 教诲=反复教导道理 | 大词小用 |
| 维护 vs 保护 vs 保持 | 维护=抽象（荣誉/秩序） | "**维护**身体健康"（应是"保持"）|
| 提高 vs 提升 vs 增加 | 各有适用对象 | "**增加**水平"（应是"提高"）|

**用作干扰项的方法**：让干扰项用一个近义词替换目标词，看学生能否识别细微差异。

### 偏误 4：拼音输入同音/形近别字

学生只输入拼音，对字形不敏感：

| 学生写的 | 正确 | 偏误类型 |
|---|---|---|
| 因该努力 | 应该努力 | 同音 yīng |
| 捡查身体 | 检查身体 | 形近 |
| 检察身体 | 检查身体 | 同音 jiǎn chá |
| 生活水瓶 | 生活水平 | 同音 píng |
| 努利学习 | 努力学习 | 形近 |
| 心清舒畅 | 心情舒畅 | 形近 |
| 同情人物 | 同情心物（同情心） | 字序混乱 |
| 鼓励发言 vs 鼓舞士气 | 区别 | 近义动词混淆 |

**用作干扰项的方法**：在第3关陷阱关，让某个例句里用了"错别字"（学生真的会写错的字）。

### 偏误 5：成语降维误用（望文生义）

学生背成语但不理解语境：

| 学生错误 | 错在哪里 |
|---|---|
| 心情五颜六色 | 五颜六色形容**色彩**，不形容心情 |
| 成绩美不胜收 | 美不胜收形容**景物**，不形容成绩 |
| 半途而废回家 | 半途而废是**抽象放弃**，不是物理走一半 |
| 食物刻骨铭心 | 大词小用，刻骨铭心是用于深刻经历 |
| 友谊一帆风顺 | 一帆风顺形容**事情进展**，不形容关系 |
| 一诺千金答应洗碗 | 大词小用，一诺千金用于重要承诺 |
| 经过千辛万苦，一帆风顺地完成 | 逻辑矛盾，前面困难+后面顺利 |
| 师恩感激他对我的批评 | 师恩=老师的恩情，不是单次批评 |
| 开卷有益看了一部电影 | 开卷=读书，不是看电影 |

**用作干扰项的方法**：在第3关陷阱关，让某个例句"形容对象错误"或"大词小用"。

# ⚠️ 三个最重要的出题原则

## 🎲 原则 1：正确答案必须随机分布

每出一题，正确答案位置（0/1/2）必须随机。出完所有题后：
- A 选项（correct: 0）占比 25-40%
- B 选项（correct: 1）占比 25-40%
- C 选项（correct: 2）占比 25-40%

**禁止**：默认放 A、连续 3 题同位置、某位置占比超 50%。

## 📚 原则 2：选项情境多样化

- 课文情境：每个词的所有选项中，最多 1-2 个用课文情境
- 课外情境：其他来自家庭、学校、邻里、节庆、兴趣场景
- 三关共 9 选项，课文情境 2-3 个，课外 6-7 个

## 🧩 原则 3：词义关（第1关）用构词推理或语境推理

### 方式 A：构词推理（适合两字合成词：师恩、教诲、勤奋）

```
课文里说：「[课文一句话]」

「[词语]」这个词，「[字1]」是 [字1意思]，「[字2]」是 [字2意思]。
两个字合起来，意思最接近：
```

### 方式 B：语境推理（适合成语：一帆风顺、未雨绸缪）

```
课文里有句话：「[完整课文句子]」

从这句话推测，「[词语]」最可能是什么意思？
```

**构词分析只到字面意思**，不讲字源、偏旁、古汉语。

# 🎯 词语类型 × 偏误库的搭配（最重要！）

不同类型的词，应该用不同的偏误库做干扰项：

| 词语类型 | 例子 | 推荐用的偏误 | 推荐用的偏误 |
|---|---|---|---|
| **成语类**（4字） | 一帆风顺、未雨绸缪、师恩难忘 | 偏误 5（成语降维误用）| 偏误 3（近义成语混淆）|
| **合成动词** | 维护、教诲、提高 | 偏误 3（近义词混淆）| 偏误 1（英语负迁移）|
| **抽象名词** | 友谊、师恩、压力 | 偏误 1（英语负迁移）| 偏误 3（近义词混淆）|
| **常用动宾搭配** | 检查、看病、参加 | 偏误 4（同音别字）| 偏误 1（英语负迁移）|
| **形容词/副词** | 新颖、尴尬、谆谆 | 偏误 3（近义词混淆）| 偏误 5（语境误用）|
| **数量/量词** | 一粒/一个/一项 | 偏误 2（量词错误）| 偏误 3（近义量词）|

**核心规则**：每道题的 2 个干扰项，**至少有 1 个**来自上面表格推荐的偏误类型。

# 🔍 干扰项强度自检（每道题出完都要做！）

对每个干扰项问 3 个问题：
1. **真实性检查**：这个错误是新加坡学生**真的会犯**的吗？还是凭空想象？
   - ❌ 如果答案是凭空想象 → **重出**
2. **难度检查**：中等程度学生看一眼会立刻排除吗？
   - ❌ 如果"立刻排除" → **太弱，重出**
3. **教育价值**：学生答错后，能学到一个具体的偏误规则吗？
   - ❌ 如果"学不到东西" → **重出**

**铁律**：**如果你想出一个"完全不沾边"的干扰项，停下来，去五大偏误库找替代。**

# 🎨 tip / whyCorrect / whyWrong 用图标短句（v5 沿用）

学生不爱读长文字，所有解释字段用图标短句。

## 图标含义

| 图标 | 用途 |
|---|---|
| 🧩 | 拆字 |
| 🔗 | 同类词 |
| 💡 | 猜词窍门 |
| ⚠️ | 易错点 |
| ✨ | 一句话记住 |
| 🇸🇬 | 新加坡学生注意（英语直译陷阱等）|

## 格式规则

- 每行一个图标 + 一句话（≤15 字）
- tip 最多 3 行
- whyWrong 要点明"这是哪类偏误"

# JSON 格式范例

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
      "options": [
        "老师对学生的批评和责备",
        "老师反复给学生的教导启发",
        "老师上课时教给我的知识"
      ],
      "correct": 1,
      "tip": "🧩 教=教导，诲=教导 → 反复教导
🔗 同类词：训诲、教训
✨ 教诲 ≠ 批评、≠ 上课"
    },
    "usage": {
      "prompt": "下面哪个最适合用「教诲」？",
      "options": [
        "外婆经常告诉我做人要诚实善良",
        "妈妈让我去食阁买晚餐",
        "数学老师在白板上写公式"
      ],
      "correct": 0,
      "tip": "✨ 教诲 = 长辈讲做人道理
⚠️ 不用在日常小事或单纯教知识"
    },
    "trap": {
      "prompt": "下面哪一句最恰当？",
      "options": [
        "老师叫我去办公室拿作业本，这是一次<u>教诲</u>。",
        "我把功课交给同学批改，他<u>教诲</u>我改正错误。",
        "爷爷常常<u>教诲</u>我，做人要懂得感恩。"
      ],
      "correct": 2,
      "whyCorrect": "✅ 长辈讲做人道理 = 教诲",
      "whyWrong": "❌ A：日常小事不用「教诲」（偏误5：大词小用）
❌ B：同学之间不用「教诲」（偏误3：教诲 vs 教）",
      "remember": "✨ 教诲 = 长辈/老师讲做人道理"
    }
  }
]
```

**注意上面例子的干扰项**：
- meaning 关：
  - A「批评和责备」← 真实错误（情感色彩混淆）
  - C「上课时教知识」← 真实错误（教诲 ≠ 上课）
- usage 关：
  - B「让我去食阁买晚餐」← 大词小用
  - C「白板上写公式」← 教诲 ≠ 教知识
- trap 关：
  - A 大词小用（拿作业本太小事）
  - B 教诲 vs 教（同学之间用错）

**每个干扰项都对应真实的偏误类型**，不是凭空想象！

# 出题前检查清单（出题前必填）

请先在心里列出：

| 词语 | 难度 | 类型 | 用偏误库 | meaning位置 | usage位置 | trap位置 |
|---|---|---|---|---|---|---|
| 词1 | hard | 成语 | 偏误5+偏误3 | A | C | B |
| 词2 | hard | 合成动词 | 偏误3+偏误1 | B | A | C |
| 词3 | easy | 普通词 | 偏误4 | / | / | A |

确保：
- A/B/C 三个位置分布均匀
- 每个词用的偏误库**符合上面推荐表**

---

# 我的课文

**课文标题**：[在这里填]

**年级和单元**：[例如：Sec 1 单元二 第三课]

**课文全文**：
[在这里贴课文全文]

**要出题的词语**：

| # | 词语 | 难度 |
|---|---|---|
| 1 | [词1] | hard |
| 2 | [词2] | hard |
| 3 | [词3] | easy |

---

# 输出要求

1. **只输出 JSON**，不要任何说明文字、不要 markdown 代码块包裹
2. JSON 以 `[` 开头，`]` 结尾
3. 所有字段名用英文双引号
4. `correct` 是数字（0/1/2）
5. 选项数量保持 3 个
6. **每道题的 2 个干扰项，至少 1 个来自五大偏误库**
7. **whyWrong 字段必须标注偏误类型**（例：「偏误1：英语直译」「偏误3：近义词混淆」「偏误5：大词小用」）
8. tip / whyCorrect / whyWrong / remember 用图标短句格式（每行≤15 字）
9. 出完后自检：A/B/C 分布、偏误项覆盖、是否有"凭空想象的干扰项"
10. **最重要：宁可让题目变难，也不要"一看就知道"的弱干扰项**"""
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

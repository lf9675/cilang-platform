"""
auth.py - 老师认证模块
"""
import streamlit as st
import database as db


def teacher_login_ui():
    """老师登录UI（在侧边栏或主页面调用）"""
    if "teacher" in st.session_state and st.session_state.teacher:
        return st.session_state.teacher

    st.markdown("### 👩‍🏫 老师登录")

    tab1, tab2 = st.tabs(["登录", "注册"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名", key="login_user")
            password = st.text_input("密码", type="password", key="login_pwd")
            submit = st.form_submit_button("登录", use_container_width=True, type="primary")

        if submit:
            if not username or not password:
                st.error("请输入用户名和密码")
            else:
                teacher = db.login_teacher(username, password)
                if teacher:
                    st.session_state.teacher = teacher
                    st.success(f"欢迎回来，{teacher['display_name']}！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")

    with tab2:
        with st.form("register_form"):
            username = st.text_input("用户名（英文，登录用）", key="reg_user")
            display_name = st.text_input("显示名称（中文，给学生看的）", key="reg_name")
            password = st.text_input("密码（至少6位）", type="password", key="reg_pwd")
            password2 = st.text_input("再次输入密码", type="password", key="reg_pwd2")
            submit = st.form_submit_button("注册", use_container_width=True)

        if submit:
            if not all([username, display_name, password, password2]):
                st.error("所有字段都要填写")
            elif password != password2:
                st.error("两次密码不一致")
            else:
                ok, msg = db.register_teacher(username, password, display_name)
                if ok:
                    st.success(msg + "，请回到「登录」标签登录")
                else:
                    st.error(msg)

    return None


def require_teacher():
    """要求老师登录才能继续。返回 teacher 字典或 stop"""
    if "teacher" in st.session_state and st.session_state.teacher:
        return st.session_state.teacher

    teacher_login_ui()
    st.stop()


def teacher_logout_button():
    """侧边栏注销按钮"""
    if "teacher" in st.session_state and st.session_state.teacher:
        with st.sidebar:
            st.markdown(f"**当前老师：** {st.session_state.teacher['display_name']}")
            if st.button("🚪 注销", use_container_width=True):
                del st.session_state["teacher"]
                st.rerun()

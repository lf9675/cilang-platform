"""
detective_utils.py - 侦探闯关完成码校验工具
SALT 必须与 HTML 端一致！
"""

import hmac
import hashlib

# ⚠️ 必须与 templates/恐怖事件-侦探闯关v7.html 中的 COMPLETION_SALT 完全一致
COMPLETION_SALT = b"kewenciyu_v7_2026"

CHARS = "0123456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 去掉了易混淆的 I/L/O


def generate_completion_code(class_name: str, student_id: str, lesson_id: int, badges: int) -> str:
    """生成完成码（与 HTML 端算法一致，供测试用）"""
    payload = f"{class_name}|{student_id}|{lesson_id}|{badges}".encode("utf-8")
    sig = hmac.new(COMPLETION_SALT, payload, hashlib.sha256).digest()
    code = "".join(CHARS[sig[i] % len(CHARS)] for i in range(4))
    return f"DT-{code}-{badges}"


def verify_completion_code(code: str, class_name: str, student_id: str, lesson_id: int):
    """
    校验完成码。返回 (是否合法: bool, 徽章数: int)
    
    完成码格式：DT-XXXX-N
    """
    parts = code.strip().upper().split("-")
    if len(parts) != 3:
        return False, 0
    if parts[0] != "DT":
        return False, 0
    if len(parts[1]) != 4:
        return False, 0
    
    try:
        badges = int(parts[2])
    except ValueError:
        return False, 0
    
    if not (0 <= badges <= 5):
        return False, 0
    
    expected_code = generate_completion_code(class_name, student_id, lesson_id, badges)
    expected_xxxx = expected_code.split("-")[1]
    
    if parts[1] == expected_xxxx:
        return True, badges
    return False, 0

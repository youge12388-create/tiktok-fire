"""抖音 DOM Selector 与页面文本标记集中管理（§27）。

抖音网页结构变更时只需修改本文件，业务代码应从这里导入这些常量，
不得在各模块分散书写 CSS Selector / 文案标记。
"""

from __future__ import annotations

CHAT_URL = "https://www.douyin.com/chat"

# 登录相关
LOGIN_TEXTS = ["扫码登录", "验证码登录", "登录后查看", "登录后即可"]
LOGIN_TAB_TEXT = "扫码登录"
QR_CODE_SELECTOR = "#animate_qrcode_container"
QR_IMAGE_SELECTORS = [
    "#animate_qrcode_container img",
    '[data-e2e="login-qrcode"] img',
    'div[class*="qrcode"] img',
]
QR_CLICK_CANDIDATES = [
    "#animate_qrcode_container",
    'div[class*="qrcode"]',
    'div[class*="refresh"]',
]

# 聊天列表
CONTACT_ITEM_WRAPPER = '[class*="conversationConversationItemwrapper"]'
CONTACT_TITLE = ".conversationConversationItemtitle"
CONTACT_TITLE_FALLBACK = '[class*="Itemtitle"]'
TAG_NEXT_TO_TITLE = (
    '[class*="TagNextToTitle"], [class*="timeStr"], '
    '[class*="streak"], [class*="Streak"]'
)
BADGE_SELECTOR = '[class*="badge"]'
STREAK_SELECTOR = (
    '[class*="commonStreaknormalText"], '
    '[class*="commonStreakstreakContainer"]'
)
FLAME_ICON_MARK = "flame_icon"
LIST_SCROLL_SELECTOR = (
    '[class*="conversationList"], [class*="chatList"], '
    '[class*="ContactList"], [class*="contactList"]'
)

# 会话 / 输入 / 搜索
CHAT_INPUT_SELECTOR = 'div[contenteditable="true"]'
SEARCH_PLACEHOLDER = "搜索"
SEND_BUTTON_TEXT = "发消息"

# 风控 / 安全验证文本标记（§20）
RISK_TEXT_MARKERS = [
    "操作频繁",
    "操作太频繁",
    "发送过于频繁",
    "请稍后再试",
    "稍后再试",
    "请稍后",
    "安全验证",
    "滑动验证",
    "验证码",
    "验证中心",
    "人机验证",
    "网络异常",
    "请勿频繁",
]

# 二维码过期提示
QR_EXPIRED_TEXTS = ["二维码已过期", "已失效", "已过期", "点击刷新", "刷新"]

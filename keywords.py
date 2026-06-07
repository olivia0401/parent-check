# keywords.py
# The keyword library that powers the risk judgement.
# Kept in its own file so the rules are easy to read, explain, and extend.
#
# Bilingual on purpose: the target users are Chinese-speaking elderly living in
# the UK, who receive BOTH Chinese health/supplement rumours AND English-language
# UK scam texts (Royal Mail, HMRC, bank impersonation, "Hi Mum" on WhatsApp).

# --- CRITICAL terms: identity / money / medication. Heaviest weight (+3) ---
# If any of these appear, the content is treated as very likely a problem.
CRITICAL = [
    # Chinese
    "转账", "汇款", "验证码", "银行卡", "身份证", "屏幕共享", "停药",
    # English (UK scams)
    "pin", "otp", "one-time code", "sort code", "password", "bank details",
]

# --- SCAM terms: classic fraud signals. Medium-heavy weight (+2) ---
SCAM = [
    # Chinese
    "下载app", "陌生链接", "点击链接", "稳赚不赔", "高收益", "限时返利",
    "医保认证", "退款客服", "账户异常", "冻结", "中奖", "客服",
    # English (UK smishing / impersonation)
    "royal mail", "dpd", "parcel", "redelivery", "hmrc", "tax refund",
    "rebate", "suspended", "verify", "click", "your account", "hi mum",
    "hi dad", "new number",
]

# --- HEALTH terms: supplement / wellness exaggeration. Light weight (+1) ---
HEALTH = [
    "包治百病", "根治", "清血管", "排毒", "祖传秘方", "专家推荐",
    "不用吃药", "降压药有害", "糖尿病治愈", "买三送三", "限时优惠",
    "保健品", "养生", "特效", "无副作用",
]

# --- BENIGN terms: ordinary hobbies. Used only to reassure, never to flag ---
BENIGN = [
    "养花", "做菜", "摄影", "书法", "旅游", "戏曲", "钓鱼", "宠物",
    "种菜", "月季", "广场舞", "下棋",
]

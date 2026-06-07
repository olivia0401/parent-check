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
    "转账",
    "汇款",
    "验证码",
    "银行卡",
    "身份证",
    "屏幕共享",
    "停药",
    "安全账户",
    "洗钱",  # 公检法 (fake police/court) scams move money to a "safe account"
    # English (UK scams)
    "pin",
    "otp",
    "one-time code",
    "sort code",
    "password",
    "bank details",
]

# --- SCAM terms: classic fraud signals. Medium-heavy weight (+2) ---
SCAM = [
    # Chinese — links / accounts / refunds
    "下载app",
    "陌生链接",
    "点击链接",
    "医保认证",
    "退款客服",
    "账户异常",
    "冻结",
    "中奖",
    "客服",
    "解冻",
    "理赔",
    "注销",
    "征信",
    "贷款",
    # Chinese — fake authority (公检法)
    "公检法",
    "通缉",
    "涉嫌",
    "配合调查",
    "公安局",
    "法院传票",
    "逮捕令",
    # Chinese — investment / job (刷单) scams
    "稳赚不赔",
    "高收益",
    "限时返利",
    "内幕消息",
    "导师",
    "跟单",
    "刷单",
    "垫付",
    "佣金",
    "返利",
    "投资群",
    # English (UK smishing / impersonation)
    "royal mail",
    "dpd",
    "evri",
    "parcel",
    "redelivery",
    "hmrc",
    "tax refund",
    "rebate",
    "suspended",
    "verify",
    "click",
    "your account",
    "hi mum",
    "hi dad",
    "new number",
    "dvla",
    "vehicle tax",
    "energy rebate",
    "ofgem",
    "unusual activity",
    "confirm your identity",
    "reactivate",
    "customs fee",
    "unpaid",
    "outstanding payment",
    # English — tech-support / remote-access / prize / investment scams
    "download this app",
    "download the app",
    "share your screen",
    "screen share",
    "remote access",
    "remote support",
    "gift card",
    "claim now",
    "you have won",
    "free iphone",
    "free gift",
    "lottery",
    "prize",
    "bitcoin",
    "crypto",
    "guaranteed return",
    "double your money",
]

# --- HEALTH terms: supplement / wellness exaggeration. Light weight (+1) ---
HEALTH = [
    "包治百病",
    "根治",
    "清血管",
    "血管垃圾",
    "排毒",
    "祖传秘方",
    "专家推荐",
    "不用吃药",
    "降压药有害",
    "糖尿病治愈",
    "买三送三",
    "限时优惠",
    "保健品",
    "养生",
    "特效",
    "无副作用",
    # more Chinese wellness / supplement exaggeration
    "抗癌",
    "偏方",
    "净化血液",
    "酸碱体质",
    "干细胞",
    "提高免疫力",
    "量子",
    "通经络",
    "包好",
    "神药",
    # English wellness / supplement exaggeration
    "detox",
    "cures",
    "cure-all",
    "miracle",
    "natural remedy",
    "no side effects",
    "anti-aging",
    "boost immune",
    "fat-burning",
    "reverse aging",
    "superfood",
]

# --- BENIGN terms: ordinary hobbies. Used only to reassure, never to flag ---
BENIGN = [
    "养花",
    "做菜",
    "摄影",
    "书法",
    "旅游",
    "戏曲",
    "钓鱼",
    "宠物",
    "种菜",
    "月季",
    "广场舞",
    "下棋",
]

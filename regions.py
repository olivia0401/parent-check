# regions.py
# Region-specific configuration. The same codebase ships as a UK build or a China
# build by setting the REGION environment variable (default "uk").
#
# What differs by region: the anti-fraud hotline, how to report, and the privacy
# regime named on the About page. (The contact channel — WeChat vs WhatsApp —
# follows the UI language instead, so a Chinese speaker in the UK gets WeChat
# *and* the UK hotline.)

import os

REGIONS = {
    # ---------------------------- United Kingdom ----------------------------
    "uk": {
        "hotline": "159",  # Stop Scams UK: safely reach your bank
        "hotline_label": {
            "zh": "打电话给银行（拨 159）",
            "en": "Call your bank (dial 159)",
        },
        "report": {
            "zh": "怀疑被骗可举报：Action Fraud 0300 123 2040",
            "en": "Suspect a scam? Report to Action Fraud: 0300 123 2040",
        },
        "health_line": {
            "zh": "身体不适请联系家庭医生(GP)；非紧急可拨 NHS 111，紧急情况拨 999。",
            "en": "If you feel unwell, contact your GP; for non-emergencies call NHS 111, in an emergency call 999.",
        },
        "privacy": {
            "zh": "本应用遵循英国《通用数据保护条例》（UK GDPR）。",
            "en": "This app follows UK GDPR.",
        },
        "rights": {
            "zh": "根据英国 GDPR，你有权访问、更正或删除你的数据。如对处理方式不满，可向英国信息专员办公室（ICO，ico.org.uk）投诉。",
            "en": "Under UK GDPR you have the right to access, correct or delete your data. If you are unhappy with how it is handled, you can complain to the Information Commissioner's Office (ICO, ico.org.uk).",
        },
    },
    # ------------------------------- China ----------------------------------
    "cn": {
        "hotline": "96110",  # 国家反诈中心专线
        "hotline_label": {
            "zh": "打电话给国家反诈专线（拨 96110）",
            "en": "Call the national anti-fraud hotline (96110)",
        },
        "report": {
            "zh": "怀疑被骗请立即拨打 110 报警",
            "en": "If you suspect a scam, call the police on 110",
        },
        "health_line": {
            "zh": "身体不适请到正规医院就诊；紧急情况拨打 120。",
            "en": "If you feel unwell, see a licensed hospital; in an emergency call 120.",
        },
        "privacy": {
            "zh": "本应用遵循中国《个人信息保护法》（PIPL）。",
            "en": "This app follows China's PIPL.",
        },
        "rights": {
            "zh": "根据《个人信息保护法》，你有权查阅、复制、更正和删除你的个人信息，也可以撤回同意。",
            "en": "Under China's PIPL you have the right to access, copy, correct and delete your personal information, and to withdraw consent.",
        },
    },
}


def current_region_code():
    """Resolve the active region, defaulting to the UK build."""
    code = os.environ.get("REGION", "uk").lower()
    return code if code in REGIONS else "uk"


def current_region():
    return REGIONS[current_region_code()]

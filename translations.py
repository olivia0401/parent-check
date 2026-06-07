# translations.py
# All user-facing text in both Chinese and English, keyed by short codes.
#
# Why a dictionary instead of two sets of templates: the verdict, advice and the
# "send to family" message are all stored in the database as language-NEUTRAL
# codes (e.g. risk = "danger", category = "scam"). They are only turned into
# words at display time, using this table. That means a single saved check can be
# viewed in either language, and there is no duplicated logic.
#
# Target users: Chinese-speaking elderly living in the UK. They receive Chinese
# health rumours AND English UK scam texts, so the UI must work in both.

TRANSLATIONS = {
    # ----------------------------------------------------------------- 中文
    "zh": {
        "other_lang": "en",
        "other_lang_name": "English",
        "brand": "爸妈求证",
        "nav_home": "首页",
        "nav_history": "历史",
        "nav_about": "关于",
        "footer": "这个应用不能代替医生、警察、银行或家人，只帮你先停一下、再确认。",

        # home / index
        "home_title": "拿不准，先求证",
        "home_lead": "看到养生文章、保健品广告、可疑短信或奇怪链接，先别急。把内容写下来，我帮你看看。",
        "label_content": "把看到的内容写在这里：",
        "placeholder": "例如：您的医保账户异常，请点击链接完成认证，需要输入身份证和验证码……",
        "label_source": "内容来源：",
        "submit": "开始求证",

        # content-source labels (keys are the codes stored in the database)
        "sources": {
            "health_article": "养生文章",
            "supplement_ad": "保健品广告",
            "suspicious_msg": "可疑短信",
            "other": "其他",
        },

        # result
        "result_label": "结论",
        "risk": {
            "ok": "看起来还好",
            "caution": "要小心",
            "danger": "很可能有问题",
        },
        "summary": {
            "none": "我没有看出明显风险。如果内容涉及付款、吃药或个人信息，还是建议再确认一下。",
            "scam": "这段内容有明显的诈骗特征，请非常小心。",
            "health": "这段内容像是在夸大保健品或养生效果。",
            "mixed": "这段内容里有一些需要小心的地方。",
        },
        "advice": {
            "none": [],
            "scam": ["不要点任何链接", "不要转账或付款", "不要把验证码、银行卡或身份证号告诉任何人"],
            "health": ["不要马上付款购买", "不要因为它而停掉医生开的药", "不要相信“包治百病/根治”这类说法"],
            "mixed": ["先不要付款、转账或点链接", "不要泄露个人信息或验证码", "拿不准就先停下来，问家人确认"],
        },
        "reasons_heading": "发现的问题",
        "advice_heading": "现在不要做",
        "child_heading": "发给孩子确认",
        "copy_button": "复制给孩子",
        "copied": "已复制，可以粘贴发给孩子了。",
        "save_view": "保存并查看记录",
        "back_home": "返回首页",

        # generated "send to family" message
        "reason_sep": "、",
        "child_generic_src": "一些内容",
        "child_intro": "我刚刚看到{src}，想请你帮我确认一下。",
        "child_verdict": "App 判断：{risk}。",
        "child_reason": "原因：内容里出现了 {reasons}。",
        "child_advice": "建议：先不要付款、不要点链接、不要停药，最好等你或医生确认后再决定。",

        # history
        "history_title": "历史记录",
        "history_empty": "还没有记录。回到首页求证一条试试。",

        # detail
        "detail_content": "当时的内容",
        "detail_child": "发给孩子的话",
        "feedback_q": "这次有帮助吗？",
        "feedback_yes": "有帮助",
        "feedback_no": "没帮助",
        "feedback_thanks": "你的反馈：{ans}（谢谢）",
        "back_history": "返回历史",

        # about
        "about_title": "关于这个应用",
        "about_lead": "“爸妈求证”是一个帮助长辈在拿不准时先停一下的小工具。",
        "about_can_title": "它能做什么",
        "about_can_text": "当你看到养生文章、保健品广告或可疑短信时，把内容写进来，它会用保守的方式判断风险（看起来还好 / 要小心 / 很可能有问题），指出可疑的地方，并生成一段可以发给家人确认的话。",
        "about_cannot_title": "它不能做什么",
        "about_cannot_text": "这个应用不能代替医生、警察、银行或家人。它不会告诉你某件事一定“安全”，因为真实世界里没有人能保证这一点。它只是帮你在做决定前多停一秒，用更谨慎的方式判断，并鼓励你向家人或专业人士确认。",
        "about_why_title": "为什么用规则，而不是 AI",
        "about_why_text": "在涉及钱和健康的高风险场景里，“能解释清楚为什么”比“看起来聪明”更重要。规则判断稳定、可预测，而且每一次都能明确告诉你它为什么这么判断。",
    },

    # --------------------------------------------------------------- English
    "en": {
        "other_lang": "zh",
        "other_lang_name": "中文",
        "brand": "Parent Check",
        "nav_home": "Home",
        "nav_history": "History",
        "nav_about": "About",
        "footer": "This app can't replace a doctor, the police, your bank or your family — it just helps you pause and check.",

        # home / index
        "home_title": "Not sure? Check first",
        "home_lead": "Seen a health article, a supplement ad, a suspicious text or a strange link? Don't rush. Write it down here and I'll take a look.",
        "label_content": "Write what you saw here:",
        "placeholder": "e.g. Your account is suspended. Click this link to verify and enter your one-time code…",
        "label_source": "Where is it from:",
        "submit": "Check it",

        "sources": {
            "health_article": "Health article",
            "supplement_ad": "Supplement ad",
            "suspicious_msg": "Suspicious message",
            "other": "Other",
        },

        "result_label": "Verdict",
        "risk": {
            "ok": "Looks okay",
            "caution": "Be careful",
            "danger": "Very likely a problem",
        },
        "summary": {
            "none": "I didn't spot any clear risk. If it involves payment, medication or personal information, it's still worth double-checking.",
            "scam": "This has clear signs of a scam — please be very careful.",
            "health": "This looks like it's exaggerating the effects of a supplement or health remedy.",
            "mixed": "There are a few things here worth being careful about.",
        },
        "advice": {
            "none": [],
            "scam": ["Don't click any links", "Don't transfer money or pay", "Never share codes, card or ID numbers with anyone"],
            "health": ["Don't rush to pay for it", "Don't stop any medication your doctor prescribed", "Don't believe 'cure-all' or 'completely cures' claims"],
            "mixed": ["Don't pay, transfer money or click links for now", "Don't share personal information or codes", "If you're unsure, stop and ask a family member"],
        },
        "reasons_heading": "What looked risky",
        "advice_heading": "Don't do this now",
        "child_heading": "Send to your family to confirm",
        "copy_button": "Copy for family",
        "copied": "Copied — you can paste and send it to your family now.",
        "save_view": "Save and view record",
        "back_home": "Back to home",

        "reason_sep": ", ",
        "child_generic_src": "something",
        "child_intro": "I just saw {src} and wanted to check with you.",
        "child_verdict": "The app says: {risk}.",
        "child_reason": "Why: it contained {reasons}.",
        "child_advice": "Suggestion: don't pay, don't click any links, and don't stop any medication until you or a doctor have confirmed.",

        "history_title": "History",
        "history_empty": "No records yet. Go to the home page and check something.",

        "detail_content": "The content",
        "detail_child": "Message for family",
        "feedback_q": "Was this helpful?",
        "feedback_yes": "Helpful",
        "feedback_no": "Not helpful",
        "feedback_thanks": "Your feedback: {ans} (thank you)",
        "back_history": "Back to history",

        "about_title": "About this app",
        "about_lead": "Parent Check is a small tool that helps older people pause when they're not sure.",
        "about_can_title": "What it can do",
        "about_can_text": "When you see a health article, a supplement ad or a suspicious message, write it in. It judges the risk conservatively (Looks okay / Be careful / Very likely a problem), points out what looked suspicious, and writes a short message you can send to your family to confirm.",
        "about_cannot_title": "What it can't do",
        "about_cannot_text": "This app can't replace a doctor, the police, your bank or your family. It will never tell you that something is definitely 'safe', because no one in the real world can guarantee that. It just helps you pause for a second before deciding, judge more carefully, and encourages you to confirm with family or a professional.",
        "about_why_title": "Why rules, not AI",
        "about_why_text": "In high-stakes situations involving money and health, being able to explain *why* matters more than looking clever. Rule-based judgement is stable and predictable, and it can always tell you exactly why it reached its verdict.",
    },
}

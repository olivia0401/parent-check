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
        "safety_warning": "请不要输入银行卡号、验证码、密码或身份证信息。如果对方让你转账、提供验证码、下载 App、点链接，先联系家人或官方渠道。",
        "trust_line": "这个工具会偏保守：宁可提醒你小心，也不轻易说“安全”。",
        "examples_heading": "或试试这几个例子（点一下自动填入）：",
        "examples": [
            {"label": "保健品广告", "source": "supplement_ad", "text": "这款天然保健品可以调理三高，不用吃药，限时优惠，今天下单买二送一。"},
            {"label": "诈骗短信", "source": "suspicious_msg", "text": "Royal Mail: Your parcel is waiting for redelivery. Please pay £1.99 at this link within 24 hours."},
            {"label": "养生谣言", "source": "health_article", "text": "每天喝这种水可以清除血管垃圾，很多医生都不会告诉你。"},
        ],

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
            "ok": "暂未发现明显风险，仍建议确认",
            "caution": "要小心",
            "danger": "很可能有问题",
        },
        "summary": {
            "none": "我没有发现明显的高风险词语，但这不代表一定安全。涉及钱、药、验证码、链接或个人信息时，还是建议先问家人或联系官方渠道。",
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
        "reason_model": "AI 模型判定为可疑",
        "advice_heading": "现在不要做",
        "child_heading": "发给孩子确认",
        "copy_button": "复制给孩子",
        "copied": "已复制，可以粘贴发给孩子了。",
        "share_button": "转发给家人",
        "whatsapp_button": "用 WhatsApp 发送",
        "call_heading": "需要的话，打个电话核实",
        "call_family": "打电话给家人",
        "family_number_label": "家人电话（只保存在这台设备上）",
        "family_number_placeholder": "输入家人手机号",
        "save_number": "保存号码",
        "change_number": "换号码",
        "wechat_button": "复制并打开微信",
        "wechat_heading": "发给家人的微信",
        "wechat_id_label": "家人微信号（只保存在这台设备上）",
        "wechat_id_placeholder": "输入家人的微信号",
        "wechat_saved_prefix": "发给家人微信：",
        "copy_wechat_id": "复制微信号",
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

        # privacy policy
        "nav_privacy": "隐私",
        "privacy_title": "隐私说明",
        "privacy_lead": "我们尽量少收集信息，并用大白话告诉你我们怎么处理。",
        "privacy_collect_title": "我们会保存什么",
        "privacy_collect_text": "你输入的内容、它的来源类型、判断结果和时间，会保存下来，用来显示你的“历史记录”。这些记录只和你浏览器里的一个随机编号关联，不和你的姓名或账号关联。",
        "privacy_local_title": "只存在你手机/设备上的",
        "privacy_local_text": "你保存的家人电话或微信号，只保存在你这台设备的浏览器里，不会上传到我们的服务器。",
        "privacy_not_title": "我们不会做的事",
        "privacy_not_text": "我们不要求你的姓名、账号或登录，不收集你的位置，不出售你的数据，也不会把你的内容发给任何第三方 AI（判断在本应用内完成）。",
        "privacy_private_title": "你的记录只属于你",
        "privacy_private_text": "历史记录只在你自己的浏览器里可见。清除浏览器的 Cookie 或网站数据，就会断开这个关联。",
        "privacy_rights_title": "你的权利",
        "privacy_contact_title": "联系我们",
        "privacy_contact_text": "有任何关于数据的问题，请联系：seal80644748@outlook.com",
    },

    # --------------------------------------------------------------- English
    "en": {
        "other_lang": "zh",
        "other_lang_name": "中文",
        "brand": "ScamShield for Parents",
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
        "safety_warning": "Do not enter bank card numbers, verification codes, passwords or ID details. If someone asks you to transfer money, share a code, download an app or click a link, contact your family or an official channel first.",
        "trust_line": "This tool is deliberately cautious: it would rather warn you than ever call something “safe”.",
        "examples_heading": "Or try an example (tap to fill it in):",
        "examples": [
            {"label": "Supplement ad", "source": "supplement_ad", "text": "This natural supplement controls high blood pressure, sugar and cholesterol with no need for medication. Limited-time offer, buy two get one free today."},
            {"label": "Scam text", "source": "suspicious_msg", "text": "Royal Mail: Your parcel is waiting for redelivery. Please pay £1.99 at this link within 24 hours."},
            {"label": "Health myth", "source": "health_article", "text": "Drinking this water every day clears the rubbish out of your blood vessels, something many doctors won't tell you."},
        ],

        "sources": {
            "health_article": "Health article",
            "supplement_ad": "Supplement ad",
            "suspicious_msg": "Suspicious message",
            "other": "Other",
        },

        "result_label": "Verdict",
        "risk": {
            "ok": "No obvious risk found — still check with family",
            "caution": "Be careful",
            "danger": "Very likely a problem",
        },
        "summary": {
            "none": "I didn't find obvious warning signs, but that does not mean it is definitely safe. If money, medicine, verification codes, links, or personal information are involved, please check with family or an official source first.",
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
        "reason_model": "flagged as suspicious by the model",
        "advice_heading": "Don't do this now",
        "child_heading": "Send to your family to confirm",
        "copy_button": "Copy for family",
        "copied": "Copied — you can paste and send it to your family now.",
        "share_button": "Forward to family",
        "whatsapp_button": "Send via WhatsApp",
        "call_heading": "If you need to, call to verify",
        "call_family": "Call family",
        "family_number_label": "Family phone (saved on this device only)",
        "family_number_placeholder": "Enter a family phone number",
        "save_number": "Save number",
        "change_number": "Change number",
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
        "about_lead": "ScamShield for Parents is a small tool that helps older people pause when they're not sure.",
        "about_can_title": "What it can do",
        "about_can_text": "When you see a health article, a supplement ad or a suspicious message, write it in. It judges the risk conservatively (Looks okay / Be careful / Very likely a problem), points out what looked suspicious, and writes a short message you can send to your family to confirm.",
        "about_cannot_title": "What it can't do",
        "about_cannot_text": "This app can't replace a doctor, the police, your bank or your family. It will never tell you that something is definitely 'safe', because no one in the real world can guarantee that. It just helps you pause for a second before deciding, judge more carefully, and encourages you to confirm with family or a professional.",
        "about_why_title": "Why rules, not AI",
        "about_why_text": "In high-stakes situations involving money and health, being able to explain *why* matters more than looking clever. Rule-based judgement is stable and predictable, and it can always tell you exactly why it reached its verdict.",

        # privacy policy
        "nav_privacy": "Privacy",
        "privacy_title": "Privacy",
        "privacy_lead": "We collect as little as possible, and explain in plain language what we do with it.",
        "privacy_collect_title": "What we store",
        "privacy_collect_text": "The text you submit, its source category, the result and the time are stored so we can show you your history. These records are linked only to a random id in your browser — never to your name or an account.",
        "privacy_local_title": "Kept only on your device",
        "privacy_local_text": "The family phone number or WeChat ID you save stays in your browser on this device only; it is never sent to our server.",
        "privacy_not_title": "What we never do",
        "privacy_not_text": "We don't ask for your name, account or login, don't collect your location, don't sell your data, and don't send your messages to any third-party AI — the check happens inside this app.",
        "privacy_private_title": "Your history is yours",
        "privacy_private_text": "History is visible only in your own browser. Clearing your browser's cookies or site data breaks that link.",
        "privacy_rights_title": "Your rights",
        "privacy_contact_title": "Contact",
        "privacy_contact_text": "For any question about your data, contact: seal80644748@outlook.com",
    },
}

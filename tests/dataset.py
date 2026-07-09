# Hand-labelled set for evaluate.py: real-style scam texts, health rumours and
# benign messages, in Chinese and English. `expected` is the verdict it should
# get; `kind` lets the evaluator report recall per category.
#
# Written to look realistic rather than to match the keyword lists word for
# word - a few hard cases (keyword-free impersonation, benign messages that
# happen to mention 身份证/验证码) are in here on purpose to show where a
# rule-based system actually struggles.

CASES = [
    # scams (expected: danger)
    # Chinese: links / accounts / refunds
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "您的医保账户异常，请点击链接完成认证，需要输入身份证和验证码。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "恭喜您中奖！点击 http://bit.ly/win88 领取，需先交手续费转账。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "验 证 码 是 8823，请告诉客服完成退款。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "您的快递无法投递，请点击链接补缴费用并核实身份证。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "您的银行卡涉嫌异常交易已被冻结，请联系客服解冻并提供验证码。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "社保待遇需要重新认证，逾期停发，请点击链接办理并输入身份证。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "注销校园贷通知：不注销将影响征信，请按提示操作转账。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "我是淘宝客服，您的商品有质量问题给您理赔，请加微信办理退款。",
    },
    # Chinese: fake authority (公检法)
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "【公安局】您涉嫌洗钱，请配合调查，把资金转入安全账户自证清白。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "我是法院的，您有一张逮捕令，需立即缴纳保证金到指定账户。",
    },
    # Chinese: investment / job scams (刷单)
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "兼职刷单，足不出户日赚三百，先垫付后返利，加微信领佣金。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "投资群内幕消息，跟着导师操作稳赚不赔，高收益低风险。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "网络兼职，点赞关注返现，先做小任务返利再做大单垫付。",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "您的账户存在安全风险，请下载这个APP开启屏幕共享配合操作。",
    },
    # Chinese: impersonation (keyword-free, needs the semantic layer)
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "妈，我手机摔坏了换了新号码，这是我的新号。我急用，你先帮我打一点过来。",
    },
    # English: UK smishing
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Royal Mail: your parcel is waiting for redelivery. Pay £1.99 at http://royalmail-redelivery.com within 24 hours.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "HMRC: you are due a tax refund of £278. Verify your bank details here: http://hmrc-refund.net",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Your account is suspended. Click http://secure-verify-account.com and enter your one-time code.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Please download this app and share your screen so we can fix your computer remotely.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Click http://192.168.10.5/login to reactivate your bank card.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Win a free iPhone! Limited offer at http://prize.xyz, claim now.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "DVLA: your vehicle tax payment failed. Update your details at http://dvla-refund.top",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "EVRI: we missed you. A small customs fee of £2.50 is due: http://evri-parcel.icu",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Ofgem: you are owed an energy rebate of £400. Claim now at http://energy-rebate.click",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "We noticed unusual activity on your account. Confirm your identity at http://bit.ly/secure9",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Your card has an outstanding payment. Pay now to avoid problems: www.pay-now-card.xyz",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Invest in bitcoin with guaranteed returns, double your money in 30 days. DM our advisor.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Congratulations! You have won the national lottery. Send your bank details to claim your prize.",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Amazon: your account is locked. Verify here http://amaz0n-verify.top with your password.",
    },
    # English: impersonation (semantic)
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Hi Mum, I dropped my phone, this is my new number. Can you help me pay a bill quickly?",
    },
    {
        "kind": "scam",
        "source": "suspicious_msg",
        "expected": "danger",
        "text": "Grandma, it's me, I lost my phone and I'm on a friend's number. I urgently need you to transfer some money.",
    },
    # health (expected: caution / danger)
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "这款天然保健品可以调理三高，不用吃药，限时优惠，今天下单买二送一。",
    },
    {
        "kind": "health",
        "source": "health_article",
        "expected": "caution",
        "text": "每天喝这种水可以清除血管垃圾，很多医生都不会告诉你。",
    },
    {
        "kind": "health",
        "source": "health_article",
        "expected": "caution",
        "text": "祖传秘方包治百病，根治糖尿病，无副作用。",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "专家推荐这款保健品，长期吃远离高血压。",
    },
    {
        "kind": "health",
        "source": "health_article",
        "expected": "caution",
        "text": "这个偏方能抗癌，纯天然提高免疫力，化疗都不用做了。",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "量子能量杯净化血液，酸碱体质调理，包好。",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "干细胞疗法逆转衰老，一针年轻十岁。",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "danger",
        "text": "建议停药，改吃这个神药就能根治高血压。",
    },
    {
        "kind": "health",
        "source": "health_article",
        "expected": "caution",
        "text": "This supplement detoxes your blood and cures diabetes naturally.",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "Boost your immune system and reverse aging with this superfood, no side effects.",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "This miracle fat-burning tea melts belly fat in a week.",
    },
    {
        "kind": "health",
        "source": "supplement_ad",
        "expected": "caution",
        "text": "抗癌神药，限时优惠，买三送三。",
    },
    # benign (expected: ok)
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "月季花叶子发黄怎么办？",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "How do I grow tomatoes on a balcony?",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "今晚一起去公园散步吗？",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "广场舞新学了一支舞，明天教你。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "Recipe: how to make dumplings at home.",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "孙子周末来吃饭，做点他爱吃的菜。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "妈，我下班顺路买点水果回家。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "周末天气不错，约老张去钓鱼。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "Your Amazon order has been delivered to your front door.",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "The library book club meets on Tuesday at 2pm.",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "医生说我血压控制得不错，让我继续按时吃药。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "孙女考试得了第一名，真开心。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "Let's video call this weekend to see the grandkids.",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "How do I take good photos of birds in the garden?",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "明天去超市买菜，需要带什么吗？",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "The dentist appointment is confirmed for Monday morning.",
    },
    # hard benign: legitimately mention a trigger word (honest false-positive risk)
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "记住：不要把银行验证码告诉任何人。",
    },
    {
        "kind": "benign",
        "source": "other",
        "expected": "ok",
        "text": "社区中心周四有免费体检，记得带身份证。",
    },
]

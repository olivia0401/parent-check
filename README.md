# 爸妈求证 (ScamShield for Parents)

#### Video Demo: <在此粘贴你的 YouTube unlisted 链接>

#### Description

爸妈求证 (ScamShield for Parents) is a small web application that helps elderly people — in
my case, Chinese-speaking seniors living in the UK — pause and get a second
opinion when they see something they are not sure about: a health/supplement
article, an advertisement promising miracle cures, a suspicious text message, or
a strange link. The user pastes or types the text, picks where it came from, and
the app returns a **conservative** judgement, points out exactly which words
looked risky, lists what they should *not* do right now, and — most importantly —
generates a short message they can forward to their adult children to confirm.

This project was built as my CS50x final project. It draws on Week 6 (Python),
Week 7 (SQL), Week 8 (HTML/CSS/JavaScript) and Week 9 (Flask).

#### Why this project

I started out wanting to build a general "anti-scam app" for the elderly, but the
more I thought about it, the more I realised two things. First, the person who
actually installs and cares about such a tool is usually the **adult child**, not
the elderly parent. Second, what an older person really needs in the dangerous
moment is not a clever AI — it is permission to *stop and ask someone* before
acting. So I narrowed the idea down to a **family verification tool**: its single
most important output is the "send this to your child" message, which turns a
lonely yes/no decision into a conversation.

The need is real and local. Fraud is one of the largest crime categories in
England and Wales: according to the ONS Crime Survey for England and Wales, the
year ending December 2025 saw an estimated ~9.6 million headline crime incidents,
of which ~4.4 million were fraud — close to half. The ONS also estimates around
4.2 million fraud incidents in the year ending March 2025, roughly 3 million of
which involved a loss, and the Home Office estimated the cost of fraud at about
£14.4 billion for the year ending March 2024. My specific users — Chinese-speaking
elderly in the UK — sit in a gap: UK tools are in English and aimed at British
channels, while tools from China cannot reach them.

#### How it works

The user submits text on the home page. The text is scored by a rule-based engine
and the result is one of three verdicts, deliberately worded to avoid false
reassurance:

- **暂未发现明显风险，仍建议确认** (no obvious risk found — still check)
- **要小心** (be careful)
- **很可能有问题** (very likely a problem)

I never use the word "safe". In a setting that involves money and medication, it
would be irresponsible for software to tell an elderly person that something is
definitely safe.

#### Files

- **app.py** — the Flask application. It defines the routes (`/`, `/check`,
  `/history`, `/history/<id>`, `/feedback/<id>`, `/about`), opens the SQLite
  database, creates the table from `schema.sql` on first run, inserts each check,
  and queries the history. It also keeps the chosen language in the session and
  exposes the translation table to every template. This is where Flask (Week 9)
  and SQL (Week 7) meet.

- **helpers.py** — the "brain". `analyze_content()` scores the text and returns
  language-neutral codes (a risk level and an advice category); `build_view()`
  and `generate_child_message()` turn those codes into words for the current
  language. Keeping the logic here, separate from the web layer, made it easy to
  reason about and to explain.

- **keywords.py** — the keyword library, split into four lists: CRITICAL
  (identity/money/medication), SCAM (classic fraud signals), HEALTH (supplement
  exaggeration) and BENIGN (ordinary hobbies). It is **bilingual**: Chinese
  rumour vocabulary plus English UK-scam vocabulary (Royal Mail, HMRC, "Hi Mum"
  on WhatsApp, one-time codes), because my target users receive both.

- **translations.py** — every user-facing string in Chinese and English, keyed
  by short codes. This is what lets the whole app, including past records, be
  shown in either language.

- **normalize.py** — folds text to a compact form before matching (full-width to
  half-width, lower-case, strip spacing/punctuation) so simple evasions like
  "验 证 码" are still caught.

- **blocklist.py** — deterministic checks on the links and phone numbers in a
  message (raw-IP links, URL shorteners, scam-prone TLDs, punycode, a sample
  domain blocklist, UK premium-rate numbers). High precision, fully explainable.

- **semantic.py** — the escalation layer. It detects keyword-free scams by the
  co-occurrence of structural signals (e.g. impersonation = new-number + money
  request). It can only *raise* the risk, never lower it, and has a slot for a
  learned model that needs no API key to run.

- **evaluate.py** and **tests/dataset.py** — a labelled evaluation set and a
  script that measures accuracy, separating *missed warnings* (dangerous) from
  *false alarms* (merely annoying).

- **schema.sql** — the single `checks` table that stores every analysis. Risk,
  category and source are stored as language-neutral *codes*, not finished
  sentences, so a saved check can later be viewed in either language.

- **templates/** — the Jinja2 HTML pages: `layout.html` (shared frame),
  `index.html` (form), `result.html`, `history.html`, `detail.html`,
  `about.html`.

- **static/styles.css** — large fonts, big buttons and a three-colour risk
  scheme (green/amber/red), designed to be readable for older eyes.

#### Bilingual by design

My target users are Chinese-speaking elderly in the UK — a group that falls into
a gap: UK tools (Action Fraud, Age UK) are in English and aimed at British scam
channels, while tools from China can't reach them. They receive *both* Chinese
health rumours and English UK scam texts. So the app runs fully in Chinese or
English (a one-tap toggle), the keyword library covers both, and — because every
verdict is stored as a code rather than a sentence — even old history records
re-render in whichever language the user picks.

#### The scoring algorithm (a design choice)

Each CRITICAL keyword adds 3 to a danger score, each SCAM keyword adds 2, and
each HEALTH keyword adds 1 to a separate caution score. If the user says the
content is a "suspicious message" and there is already a signal, danger is nudged
up by one — this is how the app uses the context the user provides instead of
ignoring it. A danger score of 3 or more gives "很可能有问题"; any other signal
gives "要小心"; nothing gives the conservative "no obvious risk found — still
check with family".

#### Why rules, not AI

The most important design decision was to use transparent keyword rules rather
than a large language model. In a high-stakes domain — scams and health — an
**explainable and predictable** system is safer than a clever black box. The app
can always tell the user exactly *why* it flagged something, and it can never
"hallucinate" dangerous medical advice. The responsibility is also asymmetric:
wrongly saying "be careful" only mildly annoys the user, but wrongly saying
"safe" could cost them their savings or their health, so the rules are tuned to
lean conservative.

I intentionally avoided ever telling users that something is "safe". In high-risk
contexts such as scams, health claims and money transfers, a false sense of
safety can be dangerous. Even the lowest-risk result is worded as "no obvious
risk found — still check with family", shown in a neutral colour rather than
green, and still encourages the user to confirm with family or an official source.

#### Accuracy, and how I measured it

Rather than guessing, I measure the engine against a hand-labelled set of
real-style messages, tagged by category (`python evaluate.py`). On the current
61-case set it scores **97% exact accuracy**, and — the metric that matters most —
**100% scam recall with zero missed scams** across UK smishing, fake-authority,
investment/job, and impersonation types, in both Chinese and English. The two
failure types are reported separately because they are not equally bad: a *missed
scam* (a scam shown as "ok") is dangerous, while a *false alarm* (a benign message
flagged) is only annoying — so the engine is tuned to lean toward warning.

Measuring it directly drove the design. An early version missed a keyword-free
impersonation ("Mum, I changed my number, send me some money"); that motivated the
semantic layer (`semantic.py`), which looks at the *co-occurrence* of signals
(number-change + money request) rather than single words, and now catches it. The
only remaining failures are two benign messages that happen to contain a trigger
word ("never tell anyone your verification code"; "bring your ID card to the free
health check") — the acceptable side of leaning toward warning. Removing those
without weakening real detection is exactly the job of a learned model, slotted in
behind the same escalate-only contract (see Future architecture).

Before matching, input is normalised (`normalize.py`) and links/numbers are
checked deterministically against threat heuristics (`blocklist.py`), which is
what catches spaced-out evasions and scam URLs.

#### Trying a learned model (and choosing to gate it off)

To go beyond rules I trained a small scam classifier — character n-gram TF-IDF
plus logistic regression, which works for Chinese and English without word
segmentation (`train_model.py`, `model/`). It plugs into the same escalate-only
slot in `semantic.py`, can only raise risk, and fails safe.

Measured honestly, it does not yet earn its place. On a separate 64-example
training corpus it reaches only ~0.61 cross-validated F1, and its scam-vs-benign
probabilities overlap (~0.55 vs ~0.45), so at any threshold safe enough to avoid
new false alarms it never fires — turning it on changes none of the held-out
numbers. So I keep it **off by default**. The honest lesson is that with this
little labelled data the bottleneck is *data, not architecture*; and because the
model lives behind a deterministic floor and can only raise risk, it can be
switched on safely once there is enough data to make it reliable. The web app
needs no ML dependencies to run (`requirements-ml.txt`, `SEMANTIC_MODEL=1` enable
the optional model).

#### The feedback loop

Each saved check has a "was this helpful?" question. I added the `helpful` column
deliberately, so that a future version could learn from real usage and improve
the keyword rules — a small acknowledgement that a real product must iterate.

#### How to run

```
pip install -r requirements.txt
python app.py
```

Then open the address Flask prints (usually `http://127.0.0.1:5000`) in a
browser. The page is mobile-friendly, so it also works opened on a phone.

#### Security and privacy

Because users paste real messages (which may contain personal data), I treated
this as a security tool, not just a web form:

- **No SQL injection** — every query is parameterised; SQL is never built by
  string formatting.
- **No XSS** — all user content is rendered through Jinja's autoescaping; nothing
  uses `| safe`.
- **Data minimisation** — the original text a user pastes is **never stored**.
  Only the verdict, category, matched signals and timestamp are saved, keyed to
  an anonymous per-browser id, so each visitor sees only their own history.
- **No third-party calls** — the check runs locally; the optional model is off by
  default, so messages never leave the server.
- **CSRF** — every POST form carries a per-session token that is verified before
  the action runs; `SameSite=Lax` cookies are a second layer.
- **Right to erase** — `POST /history/clear` deletes a browser's records from the
  server; the history page has a "Clear history" button.
- **Matching precision** — English keywords match on word boundaries (so "pin"
  doesn't fire inside "shopping"); Chinese uses compact substring matching to
  resist spacing evasion.
- **Session cookies** are `HttpOnly` + `SameSite=Lax` and `Secure` in production.
- **Config** — `debug` is off in production (gunicorn); the secret key is
  *required* from the environment in production (no fallback); dependencies are
  pinned; the `source` field is whitelisted; submitted text is length-capped.
- **Tested** — `python -m pytest` covers the judgement logic (including the
  no-false-positive cases), CSRF rejection and per-browser isolation; CI runs
  ruff + pytest + the accuracy check on every push.

Known limits I would address for a larger deployment: per-request rate limiting,
moving from SQLite to Postgres with a data-retention policy, and automated
dependency scanning.

#### Limitations and future work

This is a prototype. Keyword rules cannot catch every evolving scam, and the
app deliberately does not read messages automatically, handle payments, or give
medical advice. Future directions include OCR for uploaded screenshots, a
language model layer (used only to *explain*, never to override the conservative
verdict), and real notifications to family members.

The current version works well as a CS50 web app and proof of concept. If I
continued developing it, I would likely shift the product toward adult children
as the primary users, because they are often the people who actually help their
parents verify suspicious messages. That, rather than more keywords, is the real
next step.

#### Future architecture

The current version uses deterministic, explainable rules rather than a large
language model. This was an intentional design choice for the CS50 prototype: in
high-risk situations such as scams, health claims, money transfers, and
verification codes, the system should be conservative, predictable, and easy to
explain.

A real product would not necessarily *need* an LLM, but it would need a semantic
understanding layer — and an LLM is one way to implement that, not the only one.
Rather than replacing the rule-based system, I would use a layered architecture:

1. **Deterministic rules and threat intelligence as the safety floor.** Known
   high-risk signals such as verification codes, payment requests, suspicious
   links, health miracle claims, and known scam URLs would always trigger a
   higher-risk result.
2. **A semantic understanding layer as an escalation system.** A first version
   of this already exists in `semantic.py`: a heuristic that flags keyword-free
   scams (such as impersonation) by the co-occurrence of structural signals. A
   smaller classifier or an LLM would slot into the same place to improve recall
   on novel scams and emotional manipulation. Either way, this layer may only
   *raise* the risk level, never lower it.
3. **Human-in-the-loop confirmation.** The product would keep encouraging users
   to check with family or official sources, especially where money, medicine,
   personal data, or verification codes are involved.
4. **Privacy and abuse protection.** A real product would handle sensitive
   messages carefully, avoid sending unnecessary personal data to third-party
   APIs, and defend against prompt injection — because scam messages are
   themselves adversarial inputs.

This keeps the product aligned with its core principle: never give users a false
sense of safety.

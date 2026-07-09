# 爸妈求证 (ScamShield for Parents)

**A hybrid scam-safety AI agent: a deterministic risk floor + a Gemini
tool-calling agent + bilingual RAG + privacy-preserving local history.**

#### Video Demo: <在此粘贴你的 YouTube unlisted 链接>

#### What it is

爸妈求证 (ScamShield for Parents) is a bilingual web app that helps elderly
people — in my case, Chinese-speaking seniors living in the UK — pause and get a
second opinion when they see something they aren't sure about: a health article,
a miracle-cure advert, a suspicious text, or a strange link. The user pastes the
text, picks where it came from, and the app returns a **conservative** verdict,
points out exactly which signals looked risky, says what *not* to do right now,
and — most importantly — drafts a short message they can forward to their adult
children to confirm.

Under the hood it is not a single model call and not a pile of `if` statements.
It is a **layered safety system** where a deterministic rule engine sets a risk
*floor* that AI can raise but never lower, and a Gemini **tool-calling agent**
does a second-opinion pass — deciding for itself whether to search a bilingual
**RAG** knowledge base of known scams or run a phone-number checker before
committing to a verdict. Every layer is built around one product principle: in a
domain where a wrong "safe" can cost someone their savings or their health, the
system is only ever allowed to escalate caution, never to grant reassurance.

#### Why this shape

The interesting engineering problem here isn't "how good is the model". A large
model is perfectly capable of judging a scam message. The hard part is building
an AI product that is *trustworthy for a high-stakes, vulnerable user* — one
where the failure that matters (a scam waved through as "safe") is asymmetrically
worse than the annoying failure (a benign message flagged). That asymmetry drove
every architectural choice below, and it is the part I care about as an AI
engineer.

The need is also real and local. Fraud is one of the largest crime categories in
England and Wales — the ONS estimated around 4.2 million fraud incidents in the
year ending March 2025, ~3 million of them involving a loss, and the Home Office
put the cost of fraud at ~£14.4 billion for the year ending March 2024. My
specific users — Chinese-speaking elderly in the UK — sit in a gap: UK tools are
in English and aimed at British channels, while tools from China can't reach
them. They receive *both* Chinese health rumours and English UK scam texts.

## Architecture: a layered safety system

A single message flows through the pipeline top to bottom. Each layer can only
**raise** the risk level; none can lower it.

```
user text ──► [1] normalise ──► [2] deterministic rule engine ──► base risk
                                       (keywords · blocklist · semantic)
                                                                        │
                                            base risk (the safety floor)│
                                                                        ▼
              final risk ◄── [3] Gemini tool-calling agent (escalate-only)
                                    │        │
                                    ▼        ▼
                        query_knowledge_base   check_phone_numbers
                             (bilingual RAG)      (number classifier)
```

**[1] Normalisation** (`normalize.py`) folds text to a compact form (full-width→
half-width, lower-case, strip spacing/punctuation) so evasions like `验 证 码`
still match.

**[2] The deterministic floor** (`helpers.py`, `keywords.py`, `blocklist.py`,
`semantic.py`) scores the text with transparent, explainable rules: a bilingual
keyword library, a threat-intel check on links/phone numbers, and a *semantic
escalation* heuristic that catches keyword-free scams (family impersonation =
new-number + money + urgency) by the co-occurrence of structural signals. This
layer is the **safety floor** — it runs with no API key, no network, and its
output is a lower bound on the final risk.

**[3] The Gemini agent** (`ai/agent.py`) takes a second look *only* to find what
the rules missed. It is a genuine tool-calling agent, not a one-shot prompt:
given the message, it decides whether it needs more evidence, calls tools, reads
the results, and then commits to a verdict — bounded to raising the risk.

Verdicts are worded to avoid false reassurance. There are three, and none of
them is the word "safe":

- **暂未发现明显风险，仍建议确认** — no obvious risk found, still check
- **要小心** — be careful
- **很可能有问题** — very likely a problem

## The agent (`ai/agent.py`, `ai/tools.py`)

The agent loop is deliberately small and auditable:

1. The user message is wrapped in `<message>` tags and explicitly labelled as
   **data, not instructions**, with a directive to ignore anything inside it that
   tries to change the verdict — because scam messages are themselves adversarial
   input (see *Prompt-injection defence*).
2. Gemini gets the two tool declarations and runs for **up to two turns**: one to
   optionally call tools, one to answer. It chooses whether to call
   `query_knowledge_base`, `check_phone_numbers`, both, or neither.
3. Tool calls it requests are executed **in parallel** (`run_tools_parallel`,
   a `ThreadPoolExecutor` with a hard timeout) and the results are fed back.
4. The reply is parsed into `{risk, reason, advice}`. `pick_higher_risk()` then
   merges it with the rule-based floor so the agent can only ever escalate.

The two tools:

- **`query_knowledge_base`** — semantic retrieval over the RAG store of past
  scam cases, returning the closest matches with their type and analysis.
- **`check_phone_numbers`** — extracts phone numbers from the message and
  classifies each (UK premium-rate / international / mobile / official helpline,
  or the Chinese equivalents), giving the model structured evidence it can't
  reliably eyeball from raw text.

## Bilingual RAG (`ai/rag_engine.py`)

A lightweight retrieval layer with no vector-DB dependency, sized honestly for a
few dozen curated examples:

- Each scam case (`data/scams_{zh,en}.json`) is embedded with Gemini
  `text-embedding-004` and stored in SQLite as a JSON float array
  (`scam_cases` table).
- Retrieval loads the rows for the active language and ranks them by **cosine
  similarity** in Python. This is deliberately simple: at this corpus size a
  vector database would be over-engineering, and the code documents that it would
  be the wrong choice at scale.
- The store is **seeded once on first run** and separated by language, so the
  Chinese and English knowledge bases never cross-contaminate retrieval.

## AI safety design (the point of the project)

Every decision here follows from "never give a vulnerable user a false sense of
safety":

- **Escalate-only contract.** The deterministic floor is a lower bound. The
  semantic heuristic, the optional learned model, and the LLM agent can each only
  *raise* risk. This is enforced in code (`pick_higher_risk`, `semantic.escalate`),
  not just documented, so no probabilistic component can ever downgrade a warning.
- **Fail-safe, and fail-*loud enough*.** If the API key is missing, the network
  fails, or the model returns a malformed reply, the AI step is skipped and the
  rule-based verdict stands — the app degrades gracefully to the floor. Failures
  are logged with their error type for observability rather than swallowed
  silently, so a broken agent is visible instead of quietly disabled.
- **Never "safe".** The system prompt forbids the model from ever outputting a
  safe verdict; the parser defaults an unrecognised reply to *caution* rather than
  dropping the warning. Even the lowest verdict is worded "no obvious risk found,
  still check", shown in a neutral colour, not green.
- **Prompt-injection defence.** User text is passed as tagged data with explicit
  instructions to ignore embedded directives — treating the scam message as the
  adversarial input it is, not as a trusted continuation of the prompt.
- **Privacy floor for a sensitive domain.** The AI step is *optional* and
  key-gated; with no key the app runs fully locally. The original pasted text is
  **never persisted** — only the verdict, category, matched signals and timestamp
  — so the history feature can't become a breach surface.

## Files

- **app.py** — the Flask app: routes, SQLite access, and the orchestration in
  `/check` that runs the rule engine, then (if a key is set) the Gemini agent,
  then applies the escalate-only merge before saving and rendering.
- **ai/agent.py** — the tool-calling agent loop: prompt construction, the
  two-turn tool cycle, reply parsing, and the escalate-only risk merge.
- **ai/tools.py** — the tool declarations plus `query_knowledge_base` and
  `check_phone_numbers`, run in parallel with a timeout.
- **ai/rag_engine.py** — the bilingual RAG store: embed, seed, and cosine
  retrieval over SQLite.
- **ai/llm_client.py** — a thin `requests` wrapper over Gemini
  (`generateContent` + embeddings), where every failure returns `None` so the
  app can carry on.
- **helpers.py** — the deterministic scoring engine: turns text into
  language-neutral risk/category/evidence codes.
- **keywords.py** — the bilingual keyword library (CRITICAL / SCAM / HEALTH /
  BENIGN), covering both Chinese rumour vocabulary and English UK-scam vocabulary.
- **blocklist.py** — deterministic threat-intel on links and numbers (raw-IP
  links, shorteners, scam-prone TLDs, punycode, UK premium-rate numbers).
- **semantic.py** — the keyword-free escalation heuristic, plus the optional
  learned-model slot (escalate-only, off by default).
- **fetch_url.py** — fetches and extracts article text from a pasted link, with
  SSRF protection that re-validates the host **after redirects**.
- **normalize.py** — text folding so spaced-out / full-width evasions still match.
- **translations.py** — every user-facing string in Chinese and English, keyed
  by code, so even saved history re-renders in either language.
- **regions.py** — UK vs China build config (hotline, reporting channel, privacy
  regime) via the `REGION` env var.
- **schema.sql** — the `checks` table (verdicts, never raw text) and the
  `scam_cases` RAG table (text + embedding).
- **evaluate.py**, **tests/** — a labelled evaluation set and the accuracy
  harness; unit tests for the judgement logic, CSRF, and per-browser isolation.
- **templates/**, **static/** — large-font, three-colour (green/amber/red) UI
  designed for older eyes.

## Bilingual by design

My target users fall into a gap: UK tools (Action Fraud, Age UK) are English and
aimed at British channels; tools from China can't reach them. So the app runs
fully in Chinese or English (one-tap toggle), the keyword library and the RAG
store both cover both languages, and because every verdict is stored as a *code*
rather than a sentence, even old history records re-render in whichever language
the user picks.

## The deterministic floor, measured

The floor isn't a throwaway baseline — it does real work and I measure it. On a
hand-labelled 61-case set (`python evaluate.py`) it scores **97% exact accuracy**
and, the metric that matters most, **100% scam recall with zero missed scams**
across UK smishing, fake-authority, investment/job, and impersonation types, in
both languages. Missed scams and false alarms are reported *separately* because
they are not equally bad — a missed scam is dangerous, a false alarm is merely
annoying — so the engine is tuned to lean toward warning. Measuring it directly
drove the design: an early miss on a keyword-free impersonation ("Mum, I changed
my number, send me some money") is exactly what motivated the semantic layer, and
now the RAG store and LLM agent, all behind the same escalate-only contract.

I also trained a small character-n-gram TF-IDF + logistic-regression classifier
(`train_model.py`, `model/`) for the same escalate-only slot. Measured honestly
it doesn't yet earn its place (~0.61 CV F1 on a 64-example corpus; the scam/benign
probabilities overlap), so it's **off by default** — the honest lesson being that
here the bottleneck is *data, not architecture*. It's kept behind the
deterministic floor so it can be switched on safely once there's enough data. The
web app needs no ML dependencies to run.

## Security and privacy

Because users paste real messages that may contain personal data, I treated this
as a security tool, not just a web form:

- **Data minimisation** — the pasted text is **never stored**. Only the verdict,
  category, matched signals and timestamp are saved, keyed to an anonymous
  per-browser id, so each visitor sees only their own history.
- **AI is opt-in and privacy-scoped** — the agent is off unless `GEMINI_API_KEY`
  is set; with no key the whole app runs locally. Only the message text (capped)
  is sent to Gemini for the second-opinion pass, never the user's history or id.
- **Prompt-injection hardening** — user text is passed to the model as tagged
  data with explicit instructions to ignore embedded directives.
- **No SQL injection / no XSS** — every query is parameterised; all user content
  is rendered through Jinja autoescaping (no `| safe`).
- **SSRF protection** — pasted links are validated against internal/loopback/
  metadata addresses, and the final URL is re-checked **after redirects** so an
  external page can't bounce the fetcher onto an internal address.
- **CSRF** — every POST form carries a per-session token; `SameSite=Lax` cookies
  are a second layer. Session cookies are `HttpOnly` and `Secure` in production.
- **Right to erase** — `POST /history/clear` deletes a browser's records.
- **Config hardening** — `debug` off in production; the secret key is *required*
  from the environment (no fallback); dependencies pinned; `source` whitelisted;
  submitted text length-capped; POSTs rate-limited per client IP.
- **Logging** — verdicts and errors are logged for observability, but **never**
  the text the user submitted.
- **Tested** — `python -m pytest` covers the judgement logic, CSRF rejection and
  per-browser isolation; CI runs ruff + pytest + the accuracy check on every push.

Known limits for a larger deployment: moving SQLite→Postgres with a retention
policy (all DB access is isolated in `get_db()`), a shared rate-limit store, and
automated dependency scanning (`pip-audit` / Dependabot).

## How to run

```bash
pip install -r requirements.txt
python app.py
```

Then open the address Flask prints (usually `http://127.0.0.1:5000`). The page is
mobile-friendly.

**To enable the AI layer**, set a free Gemini API key
(https://aistudio.google.com/app/apikey):

```bash
cp .env.example .env      # then fill in GEMINI_API_KEY
export GEMINI_API_KEY=...  # or put it in .env
python app.py
```

Without a key the app runs exactly as before on the deterministic floor — the AI
step simply stays off. `SEMANTIC_MODEL=1` (plus `requirements-ml.txt`) enables the
optional local classifier.

## Limitations and future work

This is a prototype, and it's deliberately conservative about scope: it doesn't
read messages automatically, handle payments, or give medical advice. Natural
next steps, all behind the same escalate-only, privacy-preserving contract: OCR
for uploaded screenshots, growing the RAG corpus from confirmed cases (the
`add_case` path already exists), a feedback loop that learns from the "was this
helpful?" signal, and real notifications to family members. The bigger product
bet is to shift the primary user toward the *adult child* — the person who
actually helps a parent verify a suspicious message — because turning a lonely
yes/no into a family conversation is the real value, more than any single model.

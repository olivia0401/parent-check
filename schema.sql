-- schema.sql
-- One table that stores every check the user runs, so they can review history.
--
-- risk / category / source are stored as language-neutral codes, not finished
-- sentences - translations.py looks them up at display time so a saved check
-- can be viewed in either Chinese or English.

-- we don't store the original text the user pasted (could contain personal
-- data), only the verdict and evidence.
CREATE TABLE IF NOT EXISTS checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,   -- when the check was run (ISO string)
    source      TEXT    NOT NULL,   -- source code: health_article / supplement_ad / suspicious_msg / other
    risk        TEXT    NOT NULL,   -- risk code: ok / caution / danger
    category    TEXT    NOT NULL,   -- advice category: none / scam / health / mixed
    reasons     TEXT    NOT NULL,   -- matched keywords (evidence), one per line
    helpful     INTEGER,            -- feedback: 1 = helpful, 0 = not, NULL = no answer yet
    user_token  TEXT                -- anonymous per-browser id, so history stays private
);

-- History is always queried by user_token, so index it.
CREATE INDEX IF NOT EXISTS idx_checks_user ON checks(user_token);

-- Scam case knowledge base for RAG.  Embeddings are stored as JSON float arrays.
CREATE TABLE IF NOT EXISTS scam_cases (
    id         TEXT PRIMARY KEY,
    lang       TEXT NOT NULL,       -- "zh" or "en"
    text       TEXT NOT NULL,       -- the scam message text
    category   TEXT NOT NULL,       -- scam type label
    analysis   TEXT NOT NULL,       -- plain-language explanation
    embedding  TEXT NOT NULL,       -- JSON array of floats (Gemini text-embedding-004)
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_lang ON scam_cases(lang);

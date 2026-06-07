-- schema.sql
-- Database schema for "爸妈求证" (Parent Check).
-- One table that stores every check the user runs, so they can review history.
-- Covers CS50 Week 7 (SQL): table creation, primary keys, typed columns.
--
-- Note: risk / category / source are stored as language-NEUTRAL codes, not as
-- finished sentences. The words are looked up in translations.py at display time,
-- so a saved check can be viewed in either Chinese or English.

CREATE TABLE IF NOT EXISTS checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,   -- when the check was run (ISO string)
    source      TEXT    NOT NULL,   -- source code: health_article / supplement_ad / suspicious_msg / other
    content     TEXT    NOT NULL,   -- the text the user pasted or typed
    risk        TEXT    NOT NULL,   -- risk code: ok / caution / danger
    category    TEXT    NOT NULL,   -- advice category: none / scam / health / mixed
    reasons     TEXT    NOT NULL,   -- matched keywords (evidence), one per line
    helpful     INTEGER             -- feedback: 1 = helpful, 0 = not, NULL = no answer yet
);

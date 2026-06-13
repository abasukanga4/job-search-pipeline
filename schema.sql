-- Job-search pipeline — data model (SQLite)
--
-- Three tables: postings ingested + scored (jobs), applications generated from
-- them (applications), and inbound email responses tracked back to an
-- application (responses). The UNIQUE(source, posting_id) constraint is what
-- makes ingestion idempotent — re-running never creates duplicates.

CREATE TABLE jobs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  source         TEXT NOT NULL,              -- 'indeed' | 'linkedin'
  posting_id     TEXT NOT NULL,              -- stable id from the source
  title          TEXT NOT NULL,
  company        TEXT,
  location       TEXT,
  workplace_type TEXT,                       -- Remote | Hybrid | On-Site
  url            TEXT NOT NULL,
  description    TEXT,
  raw_json       TEXT,                       -- full original posting, serialized
  score          INTEGER,                    -- 0-100 fit score
  score_reason   TEXT,                       -- one-line honest pitch
  first_seen     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  status         TEXT DEFAULT 'new',
  UNIQUE(source, posting_id)                 -- idempotent ingestion
);

CREATE TABLE applications (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id            INTEGER NOT NULL REFERENCES jobs(id),
  status            TEXT NOT NULL DEFAULT 'queued',   -- queued|drafted|applied|rejected|interview
  applied_at        TIMESTAMP,
  notes             TEXT,
  cover_letter_path TEXT,
  updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE responses (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id      TEXT NOT NULL UNIQUE,               -- Gmail thread id
  application_id INTEGER REFERENCES applications(id),
  label          TEXT,                               -- e.g. rejection | interview | recruiter
  parsed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  subject        TEXT,
  snippet        TEXT
);

CREATE INDEX idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX idx_jobs_score ON jobs(score);

-- ============================================================================
--  TVK மக்கள் சேவை மையம் – கல்லாவி
--  TVK People's Service Center – Kallavi
--  SQLite Database Schema  (Step 1 of 10)
-- ----------------------------------------------------------------------------
--  Notes for the app layer:
--    * SQLite does NOT enforce foreign keys unless you turn them on per
--      connection.  In app.py, run this on every connection:
--          PRAGMA foreign_keys = ON;
--    * All timestamps are stored as UTC text (YYYY-MM-DD HH:MM:SS) via
--      DEFAULT CURRENT_TIMESTAMP.  Convert to IST in the template/view layer.
--    * "Performance" numbers (total complaints, total activities) are NOT
--      stored as columns — they are computed with COUNT() at read time so
--      they can never drift out of sync.  See the helper views at the bottom.
-- ============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;     -- better concurrent reads for a web app

-- ============================================================================
--  1. USERS  — login credentials + role only
--     Admin   = a row with role='admin' (no volunteer profile)
--     Volunteer = a row with role='volunteer' (1:1 with a volunteers row)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('admin', 'volunteer')),
    is_active       INTEGER NOT NULL DEFAULT 1,        -- 1 = active, 0 = deactivated
    last_login      TEXT,                              -- updated on each login
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
--  2. VOLUNTEERS  — full profile, 1:1 with a 'volunteer' user
--     Sensitive identity fields (aadhaar_*, voter_id_*) live here but the
--     app must only expose them to admins.
-- ============================================================================
CREATE TABLE IF NOT EXISTS volunteers (
    id                        INTEGER PRIMARY KEY,
    user_id                   INTEGER NOT NULL UNIQUE,
    volunteer_code            TEXT    NOT NULL UNIQUE,   -- e.g. TVK-VOL-0001 (auto-generated)

    -- Personal details
    full_name                 TEXT    NOT NULL,
    mobile                    TEXT    NOT NULL,
    alt_mobile                TEXT,
    email                     TEXT,
    dob                       TEXT,                      -- YYYY-MM-DD
    gender                    TEXT    CHECK (gender IN ('male','female','other') OR gender IS NULL),
    blood_group               TEXT,
    profile_photo             TEXT,                      -- relative path under /static/uploads/volunteers/

    -- Address details
    door_no                   TEXT,
    street                    TEXT,
    area                      TEXT,
    ward_no                   TEXT,
    village                   TEXT    DEFAULT 'Kallavi',
    pincode                   TEXT,

    -- Identity details  (ADMIN-ONLY in the UI)
    aadhaar_number            TEXT,
    aadhaar_doc               TEXT,                      -- uploaded file path
    voter_id_number           TEXT,
    voter_id_doc              TEXT,                      -- uploaded file path

    -- Organization details
    joining_date              TEXT,
    assigned_ward             TEXT,
    assigned_street           TEXT,
    status                    TEXT    NOT NULL DEFAULT 'active'
                                      CHECK (status IN ('active','inactive')),
    notes                     TEXT,

    -- Emergency contact
    emergency_contact_name    TEXT,
    emergency_contact_relation TEXT,
    emergency_contact_mobile  TEXT,

    -- Bookkeeping
    registration_date         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at                TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================================================
--  3. CATEGORIES  — complaint categories (bilingual)
-- ============================================================================
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE,    -- stable key used in code/filters
    name_en     TEXT    NOT NULL,
    name_ta     TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

-- ============================================================================
--  4. COMPLAINTS
--     Soft-delete via is_archived; rejection via status='rejected'.
--     ward_no is denormalized onto the complaint so admin ward-filtering
--     does not require a join back to the volunteer/citizen.
-- ============================================================================
CREATE TABLE IF NOT EXISTS complaints (
    id                  INTEGER PRIMARY KEY,
    tracking_id         TEXT    NOT NULL UNIQUE,         -- TVK-KAL-YYYY-0001

    -- Citizen / issue details
    citizen_name        TEXT    NOT NULL,
    citizen_mobile      TEXT    NOT NULL,
    address             TEXT    NOT NULL,
    street              TEXT,
    landmark            TEXT,                            -- optional
    ward_no             TEXT,
    category_id         INTEGER NOT NULL,
    description         TEXT    NOT NULL,

    -- Workflow
    status              TEXT    NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','in_progress','resolved','closed','rejected')),
    resolution_remarks  TEXT,                            -- admin remarks on resolve/close
    rejection_reason    TEXT,                            -- why marked fake/duplicate/spam
    is_archived         INTEGER NOT NULL DEFAULT 0,      -- soft delete

    -- Ownership / audit
    created_by          INTEGER NOT NULL,                -- volunteer (users.id) who registered it
    resolved_by         INTEGER,                         -- admin (users.id) who resolved/closed
    created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TEXT,

    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (created_by)  REFERENCES users(id),
    FOREIGN KEY (resolved_by) REFERENCES users(id)
);

-- ============================================================================
--  5. STATUS_HISTORY  — full timeline of every status change
-- ============================================================================
CREATE TABLE IF NOT EXISTS status_history (
    id              INTEGER PRIMARY KEY,
    complaint_id    INTEGER NOT NULL,
    old_status      TEXT,                                -- NULL on the very first (creation) entry
    new_status      TEXT    NOT NULL,
    changed_by      INTEGER,                             -- users.id (NULL allowed for system events)
    remarks         TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by)   REFERENCES users(id)
);

-- ============================================================================
--  6. PHOTOS  — before/after images attached to a complaint
-- ============================================================================
CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY,
    complaint_id    INTEGER NOT NULL,
    file_path       TEXT    NOT NULL,                    -- relative path under /static/uploads/complaints/
    photo_type      TEXT    NOT NULL CHECK (photo_type IN ('before','after')),
    uploaded_by     INTEGER,                             -- users.id
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by)  REFERENCES users(id)
);

-- ============================================================================
--  7. ACTIVITIES  — service activities submitted by volunteers
--     (feed straight into the gallery; no approval flow in v1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS activities (
    id              INTEGER PRIMARY KEY,
    title           TEXT    NOT NULL,
    activity_type   TEXT    NOT NULL
                            CHECK (activity_type IN
                                ('food_donation','blood_donation','educational_support',
                                 'medical_camp','public_welfare','events')),
    activity_date   TEXT,                                -- YYYY-MM-DD
    location        TEXT,
    volunteers_participated INTEGER,
    description     TEXT,
    submitted_by    INTEGER NOT NULL,                    -- users.id (volunteer or admin)
    is_archived     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (submitted_by) REFERENCES users(id)
);

-- ============================================================================
--  8. ACTIVITY_PHOTOS  — many photos per activity
-- ============================================================================
CREATE TABLE IF NOT EXISTS activity_photos (
    id              INTEGER PRIMARY KEY,
    activity_id     INTEGER NOT NULL,
    file_path       TEXT    NOT NULL,                    -- under /static/uploads/activities/
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
);

-- ============================================================================
--  9. SETTINGS  — key/value store for site config + counters
--     Tracking-ID and volunteer-code sequences live here so generation is a
--     single atomic UPDATE...RETURNING instead of scanning the table.
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
    id          INTEGER PRIMARY KEY,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT,
    updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
--  INDEXES  — back the search / filter / dashboard queries
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_complaints_status      ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_category    ON complaints(category_id);
CREATE INDEX IF NOT EXISTS idx_complaints_created_by  ON complaints(created_by);
CREATE INDEX IF NOT EXISTS idx_complaints_ward        ON complaints(ward_no);
CREATE INDEX IF NOT EXISTS idx_complaints_archived    ON complaints(is_archived);
CREATE INDEX IF NOT EXISTS idx_complaints_created_at  ON complaints(created_at);
CREATE INDEX IF NOT EXISTS idx_status_hist_complaint  ON status_history(complaint_id);
CREATE INDEX IF NOT EXISTS idx_photos_complaint       ON photos(complaint_id);
CREATE INDEX IF NOT EXISTS idx_activities_type        ON activities(activity_type);
CREATE INDEX IF NOT EXISTS idx_activities_archived    ON activities(is_archived);
CREATE INDEX IF NOT EXISTS idx_actphotos_activity     ON activity_photos(activity_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_user        ON volunteers(user_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_ward        ON volunteers(ward_no);

-- ============================================================================
--  HELPER VIEWS  — live performance numbers (never stored, never stale)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_volunteer_stats AS
SELECT
    vu.id                                   AS user_id,
    v.id                                    AS volunteer_id,
    v.volunteer_code,
    v.full_name,
    v.status,
    vu.last_login,
    (SELECT COUNT(*) FROM complaints c
       WHERE c.created_by = vu.id AND c.is_archived = 0)            AS total_complaints,
    (SELECT COUNT(*) FROM complaints c
       WHERE c.created_by = vu.id AND c.status = 'pending'
         AND c.is_archived = 0)                                     AS pending_complaints,
    (SELECT COUNT(*) FROM complaints c
       WHERE c.created_by = vu.id AND c.status IN ('resolved','closed')
         AND c.is_archived = 0)                                     AS resolved_complaints,
    (SELECT COUNT(*) FROM activities a
       WHERE a.submitted_by = vu.id AND a.is_archived = 0)          AS total_activities
FROM volunteers v
JOIN users vu ON vu.id = v.user_id;

-- Dashboard counters in one row
CREATE VIEW IF NOT EXISTS v_complaint_counts AS
SELECT
    COUNT(*)                                                AS total,
    SUM(status = 'pending')                                 AS pending,
    SUM(status = 'in_progress')                             AS in_progress,
    SUM(status = 'resolved')                                AS resolved,
    SUM(status = 'closed')                                  AS closed,
    SUM(status = 'rejected')                                AS rejected
FROM complaints
WHERE is_archived = 0;

-- ============================================================================
--  SEED DATA
-- ============================================================================
-- Complaint categories (bilingual, in display order)
INSERT OR IGNORE INTO categories (slug, name_en, name_ta, sort_order) VALUES
    ('water',        'Water',             'குடிநீர்',              1),
    ('road',         'Road',              'சாலை',                  2),
    ('street_light', 'Street Light',      'தெரு விளக்கு',          3),
    ('drainage',     'Drainage',          'வடிகால்',               4),
    ('health',       'Health',            'சுகாதாரம்',             5),
    ('education',    'Education',          'கல்வி',                 6),
    ('govt_scheme',  'Government Scheme',  'அரசு திட்டம்',          7),
    ('corruption',   'Corruption / Bribery','ஊழல் / லஞ்சம்',        8),
    ('others',       'Others',            'மற்றவை',                9);

-- Site settings + ID counters
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('site_name_ta',        'TVK மக்கள் சேவை மையம் – கல்லாவி'),
    ('site_name_en',        'TVK People''s Service Center – Kallavi'),
    ('tagline',             'மக்கள் சேவைக்கான டிஜிட்டல் தளம்'),
    ('contact_number',      '+91 8940524235'),
    ('contact_email',       'tvkkallavi@gmail.com'),
    ('contact_address',     'Kallavi - 635304'),
    ('tracking_prefix',     'TVK-KAL'),
    ('volunteer_prefix',    'TVK-VOL'),
    ('volunteer_seq',       '0'),          -- last volunteer number issued
    ('complaint_seq_year',  ''),           -- year of the current complaint counter
    ('complaint_seq',       '0');          -- last complaint number for that year

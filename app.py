"""
TVK மக்கள் சேவை மையம் – கல்லாவி
TVK People's Service Center – Kallavi
Main Flask application.
"""
import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, flash, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "tvkkallavi.db")
UPLOAD_ROOT = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_DOC = {"png", "jpg", "jpeg", "webp", "gif", "pdf"}
MAX_CONTENT_MB = 8
IST = timezone(timedelta(hours=5, minutes=30))

app = Flask(__name__)
# In production set FLASK_SECRET_KEY as an environment variable on Render.
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_MB * 1024 * 1024

# Activity types: (key, English label, Tamil label, emoji)
ACTIVITY_TYPES = [
    ("food_donation",      "Food Donation",       "உணவு வழங்கல்",  "🍲"),
    ("blood_donation",     "Blood Donation",      "இரத்த தானம்",   "🩸"),
    ("educational_support","Educational Support", "கல்வி உதவி",    "📚"),
    ("medical_camp",       "Medical Camp",        "மருத்துவ முகாம்","⚕️"),
    ("public_welfare",     "Public Welfare",      "பொது நலன்",     "🤝"),
    ("events",             "Events",              "நிகழ்வுகள்",     "🎉"),
]
ACTIVITY_KEYS = {t[0] for t in ACTIVITY_TYPES}
ACTIVITY_LABEL = {t[0]: t[1] for t in ACTIVITY_TYPES}
ACTIVITY_LABEL_TA = {t[0]: t[2] for t in ACTIVITY_TYPES}


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")  # FK enforcement, every connection
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# ID generation (atomic via the settings counters)
# --------------------------------------------------------------------------
def next_tracking_id():
    db = get_db()
    prefix = query("SELECT value FROM settings WHERE key='tracking_prefix'", one=True)["value"]
    year = str(datetime.now(IST).year)
    cur_year = query("SELECT value FROM settings WHERE key='complaint_seq_year'", one=True)["value"]
    if cur_year != year:
        db.execute("UPDATE settings SET value=? WHERE key='complaint_seq_year'", (year,))
        db.execute("UPDATE settings SET value='0' WHERE key='complaint_seq'")
    db.execute("UPDATE settings SET value = CAST(value AS INTEGER)+1 WHERE key='complaint_seq'")
    seq = int(query("SELECT value FROM settings WHERE key='complaint_seq'", one=True)["value"])
    db.commit()
    return f"{prefix}-{year}-{seq:04d}"


def next_volunteer_code():
    db = get_db()
    prefix = query("SELECT value FROM settings WHERE key='volunteer_prefix'", one=True)["value"]
    db.execute("UPDATE settings SET value = CAST(value AS INTEGER)+1 WHERE key='volunteer_seq'")
    seq = int(query("SELECT value FROM settings WHERE key='volunteer_seq'", one=True)["value"])
    db.commit()
    return f"{prefix}-{seq:04d}"


# --------------------------------------------------------------------------
# CSRF protection (lightweight, session-based)
# --------------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.context_processor
def inject_globals():
    settings = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}
    return dict(csrf_token=csrf_token, site=settings, current_user=current_user(),
                ACTIVITY_TYPES=ACTIVITY_TYPES, ACTIVITY_LABEL=ACTIVITY_LABEL,
                ACTIVITY_LABEL_TA=ACTIVITY_LABEL_TA)


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf")
        form_token = request.form.get("_csrf")
        if not token or token != form_token:
            abort(400, "CSRF token missing or invalid.")


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return query("SELECT * FROM users WHERE id=? AND is_active=1", (uid,), one=True)


def login_required(role=None):
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            user = current_user()
            if not user:
                flash("தயவுசெய்து உள்நுழையவும். / Please log in.", "warning")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


# --------------------------------------------------------------------------
# Upload helper
# --------------------------------------------------------------------------
def save_upload(file_storage, subfolder, allowed=ALLOWED_IMAGE):
    if not file_storage or file_storage.filename == "":
        return None
    fname = secure_filename(file_storage.filename)
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in allowed:
        raise ValueError(f"File type .{ext} not allowed.")
    unique = f"{secrets.token_hex(8)}_{fname}"
    dest_dir = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, unique))
    return f"uploads/{subfolder}/{unique}"  # path relative to /static


# ==========================================================================
# PUBLIC ROUTES
# ==========================================================================
@app.route("/")
def index():
    counts = query("SELECT * FROM v_complaint_counts", one=True)
    counts = dict(counts) if counts else {}
    for k in ("total", "pending", "in_progress", "resolved", "closed", "rejected"):
        counts[k] = counts.get(k) or 0

    service_counts = {}
    for t in ACTIVITY_KEYS:
        service_counts[t] = query(
            "SELECT COUNT(*) c FROM activities WHERE activity_type=? AND is_archived=0", (t,), one=True
        )["c"]

    recent = query("""
        SELECT a.*, (SELECT file_path FROM activity_photos WHERE activity_id=a.id LIMIT 1) AS cover
        FROM activities a WHERE a.is_archived=0
        ORDER BY a.created_at DESC LIMIT 6
    """)
    return render_template("index.html", counts=counts, service_counts=service_counts, recent=recent)


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(os.path.join(BASE_DIR, "static"), "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Content-Type"] = "application/javascript"
    return resp


@app.route("/track", methods=["GET", "POST"])
def track():
    complaint = None
    history = []
    photos = {"before": [], "after": []}
    searched = False
    if request.method == "POST":
        searched = True
        tid = request.form.get("tracking_id", "").strip().upper()
        complaint = query("""
            SELECT c.*, cat.name_en AS cat_en, cat.name_ta AS cat_ta
            FROM complaints c JOIN categories cat ON cat.id=c.category_id
            WHERE c.tracking_id=? AND c.is_archived=0
        """, (tid,), one=True)
        if complaint:
            history = query("SELECT * FROM status_history WHERE complaint_id=? ORDER BY created_at",
                            (complaint["id"],))
            for p in query("SELECT * FROM photos WHERE complaint_id=?", (complaint["id"],)):
                photos[p["photo_type"]].append(p["file_path"])
    return render_template("track.html", complaint=complaint, history=history,
                           photos=photos, searched=searched)


@app.route("/gallery")
def gallery():
    items = query("""
        SELECT a.*,
               (SELECT file_path FROM activity_photos WHERE activity_id=a.id LIMIT 1) AS cover,
               (SELECT COUNT(*) FROM activity_photos WHERE activity_id=a.id) AS photo_count
        FROM activities a WHERE a.is_archived=0 ORDER BY a.created_at DESC
    """)
    return render_template("gallery.html", items=items)


@app.route("/activity/<int:aid>")
def activity_detail(aid):
    a = query("""SELECT a.*, u.username AS submitted_by_name
                 FROM activities a LEFT JOIN users u ON u.id=a.submitted_by
                 WHERE a.id=? AND a.is_archived=0""", (aid,), one=True)
    if not a:
        abort(404)
    photos = [p["file_path"] for p in
              query("SELECT file_path FROM activity_photos WHERE activity_id=? ORDER BY id", (aid,))]
    user = current_user()
    can_edit = bool(user) and (user["role"] == "admin" or user["id"] == a["submitted_by"])
    can_delete = bool(user) and user["role"] == "admin"
    return render_template("activity_detail.html", a=a, photos=photos,
                           can_edit=can_edit, can_delete=can_delete)


# ==========================================================================
# AUTH
# ==========================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            if not user["is_active"]:
                flash("உங்கள் கணக்கு செயலிழக்கப்பட்டுள்ளது. / Your account is deactivated.", "danger")
                return redirect(url_for("login"))
            session.clear()
            session["uid"] = user["id"]
            session["role"] = user["role"]
            execute("UPDATE users SET last_login=? WHERE id=?", (now_utc(), user["id"]))
            flash("வரவேற்கிறோம்! / Welcome!", "success")
            return redirect(url_for("dashboard"))
        flash("தவறான பயனர் பெயர் அல்லது கடவுச்சொல். / Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("வெளியேறிவிட்டீர்கள். / You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("vol_dashboard"))


# ==========================================================================
# ADMIN
# ==========================================================================
@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    counts = dict(query("SELECT * FROM v_complaint_counts", one=True) or {})
    for k in ("total", "pending", "in_progress", "resolved", "closed", "rejected"):
        counts[k] = counts.get(k) or 0
    by_cat = query("""
        SELECT cat.name_en AS label, COUNT(c.id) AS n
        FROM categories cat LEFT JOIN complaints c
          ON c.category_id=cat.id AND c.is_archived=0
        GROUP BY cat.id ORDER BY cat.sort_order
    """)
    by_month = query("""
        SELECT strftime('%Y-%m', created_at) AS label, COUNT(*) AS n
        FROM complaints WHERE is_archived=0
        GROUP BY label ORDER BY label DESC LIMIT 6
    """)
    recent = query("""
        SELECT c.*, cat.name_en AS cat_en FROM complaints c
        JOIN categories cat ON cat.id=c.category_id
        WHERE c.is_archived=0 ORDER BY c.created_at DESC LIMIT 8
    """)
    return render_template("admin/dashboard.html", counts=counts,
                           by_cat=by_cat, by_month=list(reversed(by_month)), recent=recent)


@app.route("/admin/complaints")
@login_required(role="admin")
def admin_complaints():
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    ward = request.args.get("ward", "").strip()
    search = request.args.get("q", "").strip()
    archived = request.args.get("archived", "0")

    sql = """SELECT c.*, cat.name_en AS cat_en FROM complaints c
             JOIN categories cat ON cat.id=c.category_id WHERE 1=1"""
    args = []
    sql += " AND c.is_archived=?"; args.append(1 if archived == "1" else 0)
    if status:
        sql += " AND c.status=?"; args.append(status)
    if category:
        sql += " AND cat.slug=?"; args.append(category)
    if ward:
        sql += " AND c.ward_no=?"; args.append(ward)
    if search:
        sql += " AND (c.tracking_id LIKE ? OR c.citizen_name LIKE ? OR c.citizen_mobile LIKE ?)"
        args += [f"%{search}%"] * 3
    sql += " ORDER BY c.created_at DESC"
    rows = query(sql, args)
    cats = query("SELECT * FROM categories ORDER BY sort_order")
    return render_template("admin/complaints.html", rows=rows, cats=cats,
                           f={"status": status, "category": category, "ward": ward,
                              "q": search, "archived": archived})


@app.route("/admin/complaint/<int:cid>")
@login_required(role="admin")
def admin_complaint_detail(cid):
    c = query("""SELECT c.*, cat.name_en AS cat_en, cat.name_ta AS cat_ta,
                        u.username AS created_by_name
                 FROM complaints c JOIN categories cat ON cat.id=c.category_id
                 LEFT JOIN users u ON u.id=c.created_by WHERE c.id=?""", (cid,), one=True)
    if not c:
        abort(404)
    history = query("SELECT * FROM status_history WHERE complaint_id=? ORDER BY created_at", (cid,))
    photos = {"before": [], "after": []}
    for p in query("SELECT * FROM photos WHERE complaint_id=?", (cid,)):
        photos[p["photo_type"]].append(p["file_path"])
    return render_template("admin/complaint_detail.html", c=c, history=history, photos=photos)


@app.route("/admin/complaint/<int:cid>/update", methods=["POST"])
@login_required(role="admin")
def admin_complaint_update(cid):
    c = query("SELECT * FROM complaints WHERE id=?", (cid,), one=True)
    if not c:
        abort(404)
    new_status = request.form.get("status", c["status"])
    remarks = request.form.get("resolution_remarks", "").strip()
    rejection = request.form.get("rejection_reason", "").strip()
    valid = {"pending", "in_progress", "resolved", "closed", "rejected"}
    if new_status not in valid:
        abort(400)

    resolved_at = c["resolved_at"]
    if new_status in ("resolved", "closed") and not resolved_at:
        resolved_at = now_utc()

    execute("""UPDATE complaints SET status=?, resolution_remarks=?, rejection_reason=?,
               resolved_by=?, resolved_at=?, updated_at=? WHERE id=?""",
            (new_status, remarks or c["resolution_remarks"], rejection or c["rejection_reason"],
             session["uid"], resolved_at, now_utc(), cid))

    if new_status != c["status"]:
        execute("""INSERT INTO status_history (complaint_id, old_status, new_status, changed_by, remarks)
                   VALUES (?,?,?,?,?)""", (cid, c["status"], new_status, session["uid"], remarks))

    after = request.files.get("after_photo")
    if after and after.filename:
        try:
            path = save_upload(after, "complaints", ALLOWED_IMAGE)
            execute("""INSERT INTO photos (complaint_id, file_path, photo_type, uploaded_by)
                       VALUES (?,?,'after',?)""", (cid, path, session["uid"]))
        except ValueError as e:
            flash(str(e), "danger")

    flash("புகார் புதுப்பிக்கப்பட்டது. / Complaint updated.", "success")
    return redirect(url_for("admin_complaint_detail", cid=cid))


@app.route("/admin/complaint/<int:cid>/archive", methods=["POST"])
@login_required(role="admin")
def admin_complaint_archive(cid):
    to = 0 if request.form.get("restore") else 1
    execute("UPDATE complaints SET is_archived=?, updated_at=? WHERE id=?", (to, now_utc(), cid))
    flash("மீட்டமைக்கப்பட்டது / Restored." if to == 0 else "காப்பகப்படுத்தப்பட்டது / Archived.", "info")
    return redirect(request.referrer or url_for("admin_complaints"))


# ----- Volunteer management -----
@app.route("/admin/volunteers")
@login_required(role="admin")
def admin_volunteers():
    q = request.args.get("q", "").strip()
    sql = """SELECT v.*, u.is_active, u.last_login, s.total_complaints, s.total_activities
             FROM volunteers v JOIN users u ON u.id=v.user_id
             LEFT JOIN v_volunteer_stats s ON s.volunteer_id=v.id WHERE 1=1"""
    args = []
    if q:
        sql += """ AND (v.full_name LIKE ? OR v.mobile LIKE ? OR v.volunteer_code LIKE ?
                        OR v.ward_no LIKE ? OR v.street LIKE ?)"""
        args += [f"%{q}%"] * 5
    sql += " ORDER BY v.created_at DESC"
    rows = query(sql, args)
    return render_template("admin/volunteers.html", rows=rows, q=q)


@app.route("/admin/volunteer/new", methods=["GET", "POST"])
@login_required(role="admin")
def admin_volunteer_new():
    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip()
        password = f.get("password", "")
        if not username or not password:
            flash("பயனர்பெயர் மற்றும் கடவுச்சொல் தேவை. / Username and password required.", "danger")
            return redirect(url_for("admin_volunteer_new"))
        if query("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash("பயனர்பெயர் ஏற்கனவே உள்ளது. / Username already exists.", "danger")
            return redirect(url_for("admin_volunteer_new"))

        uid = execute("INSERT INTO users (username, password_hash, role) VALUES (?,?, 'volunteer')",
                      (username, generate_password_hash(password)))
        code = next_volunteer_code()
        profile_photo = None
        try:
            profile_photo = save_upload(request.files.get("profile_photo"), "volunteers")
        except ValueError as e:
            flash(str(e), "warning")
        aadhaar_doc = voter_doc = None
        try:
            aadhaar_doc = save_upload(request.files.get("aadhaar_doc"), "volunteers", ALLOWED_DOC)
            voter_doc = save_upload(request.files.get("voter_id_doc"), "volunteers", ALLOWED_DOC)
        except ValueError as e:
            flash(str(e), "warning")

        execute("""INSERT INTO volunteers
            (user_id, volunteer_code, full_name, mobile, alt_mobile, email, dob, gender, blood_group,
             profile_photo, door_no, street, area, ward_no, village, pincode,
             aadhaar_number, aadhaar_doc, voter_id_number, voter_id_doc,
             joining_date, assigned_ward, assigned_street, status, notes,
             emergency_contact_name, emergency_contact_relation, emergency_contact_mobile)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, code, f.get("full_name"), f.get("mobile"), f.get("alt_mobile"), f.get("email"),
             f.get("dob"), f.get("gender") or None, f.get("blood_group"), profile_photo,
             f.get("door_no"), f.get("street"), f.get("area"), f.get("ward_no"),
             f.get("village") or "Kallavi", f.get("pincode"),
             f.get("aadhaar_number"), aadhaar_doc, f.get("voter_id_number"), voter_doc,
             f.get("joining_date"), f.get("assigned_ward"), f.get("assigned_street"),
             f.get("status") or "active", f.get("notes"),
             f.get("emergency_contact_name"), f.get("emergency_contact_relation"),
             f.get("emergency_contact_mobile")))
        flash(f"தொண்டர் உருவாக்கப்பட்டார் / Volunteer created: {code}", "success")
        return redirect(url_for("admin_volunteers"))
    return render_template("admin/volunteer_form.html", v=None)


@app.route("/admin/volunteer/<int:vid>")
@login_required(role="admin")
def admin_volunteer_detail(vid):
    v = query("""SELECT v.*, u.username, u.is_active, u.last_login, u.created_at AS user_created
                 FROM volunteers v JOIN users u ON u.id=v.user_id WHERE v.id=?""", (vid,), one=True)
    if not v:
        abort(404)
    stats = query("SELECT * FROM v_volunteer_stats WHERE volunteer_id=?", (vid,), one=True)
    recent = query("""SELECT c.*, cat.name_en AS cat_en FROM complaints c
                      JOIN categories cat ON cat.id=c.category_id
                      WHERE c.created_by=? ORDER BY c.created_at DESC LIMIT 10""", (v["user_id"],))
    return render_template("admin/volunteer_detail.html", v=v, stats=stats, recent=recent)


@app.route("/admin/volunteer/<int:vid>/toggle", methods=["POST"])
@login_required(role="admin")
def admin_volunteer_toggle(vid):
    v = query("SELECT user_id FROM volunteers WHERE id=?", (vid,), one=True)
    if not v:
        abort(404)
    execute("UPDATE users SET is_active = 1 - is_active WHERE id=?", (v["user_id"],))
    execute("""UPDATE volunteers SET status =
               CASE WHEN (SELECT is_active FROM users WHERE id=?)=1 THEN 'active' ELSE 'inactive' END
               WHERE id=?""", (v["user_id"], vid))
    flash("தொண்டர் நிலை மாற்றப்பட்டது. / Volunteer status changed.", "info")
    return redirect(request.referrer or url_for("admin_volunteers"))


@app.route("/admin/volunteer/<int:vid>/reset", methods=["POST"])
@login_required(role="admin")
def admin_volunteer_reset(vid):
    v = query("SELECT user_id FROM volunteers WHERE id=?", (vid,), one=True)
    new_pw = request.form.get("new_password", "").strip()
    if not v or len(new_pw) < 4:
        flash("கடவுச்சொல் குறைந்தது 4 எழுத்துகள். / Password must be at least 4 chars.", "danger")
        return redirect(url_for("admin_volunteer_detail", vid=vid))
    execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_pw), v["user_id"]))
    flash("கடவுச்சொல் மீட்டமைக்கப்பட்டது. / Password reset.", "success")
    return redirect(url_for("admin_volunteer_detail", vid=vid))


# ----- Admin activities/gallery management -----
@app.route("/admin/activities")
@login_required(role="admin")
def admin_activities():
    rows = query("""SELECT a.*, u.username,
                    (SELECT file_path FROM activity_photos WHERE activity_id=a.id LIMIT 1) AS cover
                    FROM activities a LEFT JOIN users u ON u.id=a.submitted_by
                    ORDER BY a.created_at DESC""")
    return render_template("admin/activities.html", rows=rows)


@app.route("/admin/activity/<int:aid>/archive", methods=["POST"])
@login_required(role="admin")
def admin_activity_archive(aid):
    to = 0 if request.form.get("restore") else 1
    execute("UPDATE activities SET is_archived=? WHERE id=?", (to, aid))
    flash("புதுப்பிக்கப்பட்டது. / Updated.", "info")
    return redirect(url_for("admin_activities"))


# ==========================================================================
# VOLUNTEER
# ==========================================================================
@app.route("/volunteer")
@login_required(role="volunteer")
def vol_dashboard():
    uid = session["uid"]
    v = query("SELECT * FROM volunteers WHERE user_id=?", (uid,), one=True)
    stats = query("SELECT * FROM v_volunteer_stats WHERE user_id=?", (uid,), one=True)
    recent = query("""SELECT c.*, cat.name_en AS cat_en FROM complaints c
                      JOIN categories cat ON cat.id=c.category_id
                      WHERE c.created_by=? ORDER BY c.created_at DESC LIMIT 8""", (uid,))
    return render_template("volunteer/dashboard.html", v=v, stats=stats, recent=recent)


@app.route("/volunteer/complaint/new", methods=["GET", "POST"])
@login_required(role="volunteer")
def vol_complaint_new():
    cats = query("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order")
    if request.method == "POST":
        f = request.form
        cat = query("SELECT id FROM categories WHERE id=?", (f.get("category_id"),), one=True)
        if not cat:
            flash("வகையைத் தேர்ந்தெடுக்கவும். / Select a category.", "danger")
            return redirect(url_for("vol_complaint_new"))
        tid = next_tracking_id()
        cid = execute("""INSERT INTO complaints
            (tracking_id, citizen_name, citizen_mobile, address, street, landmark, ward_no,
             category_id, description, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (tid, f.get("citizen_name"), f.get("citizen_mobile"), f.get("address"),
             f.get("street"), f.get("landmark"), f.get("ward_no"),
             f.get("category_id"), f.get("description"), session["uid"]))
        execute("""INSERT INTO status_history (complaint_id, old_status, new_status, changed_by, remarks)
                   VALUES (?, NULL, 'pending', ?, 'Complaint registered')""", (cid, session["uid"]))
        before = request.files.get("before_photo")
        if before and before.filename:
            try:
                path = save_upload(before, "complaints", ALLOWED_IMAGE)
                execute("""INSERT INTO photos (complaint_id, file_path, photo_type, uploaded_by)
                           VALUES (?,?,'before',?)""", (cid, path, session["uid"]))
            except ValueError as e:
                flash(str(e), "warning")
        flash(f"புகார் பதிவு செய்யப்பட்டது! கண்காணிப்பு எண்: {tid}", "success")
        return redirect(url_for("vol_complaint_new"))
    return render_template("volunteer/complaint_form.html", cats=cats)


@app.route("/volunteer/complaints")
@login_required(role="volunteer")
def vol_complaints():
    q = request.args.get("q", "").strip()
    sql = """SELECT c.*, cat.name_en AS cat_en FROM complaints c
             JOIN categories cat ON cat.id=c.category_id WHERE c.created_by=?"""
    args = [session["uid"]]
    if q:
        sql += " AND c.tracking_id LIKE ?"; args.append(f"%{q}%")
    sql += " ORDER BY c.created_at DESC"
    rows = query(sql, args)
    return render_template("volunteer/my_complaints.html", rows=rows, q=q)


@app.route("/activity/new", methods=["GET", "POST"])
@login_required()
def activity_new():
    if request.method == "POST":
        f = request.form
        if f.get("activity_type") not in ACTIVITY_KEYS:
            flash("வகையைத் தேர்ந்தெடுக்கவும். / Choose an activity type.", "danger")
            return redirect(url_for("activity_new"))
        vp = f.get("volunteers_participated", "").strip()
        vp = int(vp) if vp.isdigit() else None
        aid = execute("""INSERT INTO activities
                (title, activity_type, activity_date, location, volunteers_participated, description, submitted_by)
                VALUES (?,?,?,?,?,?,?)""",
                (f.get("title"), f.get("activity_type"), f.get("activity_date"),
                 f.get("location"), vp, f.get("description"), session["uid"]))
        for file in request.files.getlist("photos"):
            if file and file.filename:
                try:
                    path = save_upload(file, "activities", ALLOWED_IMAGE)
                    execute("INSERT INTO activity_photos (activity_id, file_path) VALUES (?,?)", (aid, path))
                except ValueError as e:
                    flash(str(e), "warning")
        flash("செயல்பாடு சமர்ப்பிக்கப்பட்டது! / Activity submitted!", "success")
        return redirect(url_for("activity_detail", aid=aid))
    return render_template("activity_form.html", act=None, photos=[])


def _can_manage_activity(a):
    user = current_user()
    return user and (user["role"] == "admin" or user["id"] == a["submitted_by"])


@app.route("/activity/<int:aid>/edit", methods=["GET", "POST"])
@login_required()
def activity_edit(aid):
    a = query("SELECT * FROM activities WHERE id=?", (aid,), one=True)
    if not a:
        abort(404)
    if not _can_manage_activity(a):
        abort(403)  # volunteers may edit only their own
    if request.method == "POST":
        f = request.form
        if f.get("activity_type") not in ACTIVITY_KEYS:
            flash("வகையைத் தேர்ந்தெடுக்கவும். / Choose an activity type.", "danger")
            return redirect(url_for("activity_edit", aid=aid))
        vp = f.get("volunteers_participated", "").strip()
        vp = int(vp) if vp.isdigit() else None
        execute("""UPDATE activities SET title=?, activity_type=?, activity_date=?,
                   location=?, volunteers_participated=?, description=? WHERE id=?""",
                (f.get("title"), f.get("activity_type"), f.get("activity_date"),
                 f.get("location"), vp, f.get("description"), aid))
        for file in request.files.getlist("photos"):
            if file and file.filename:
                try:
                    path = save_upload(file, "activities", ALLOWED_IMAGE)
                    execute("INSERT INTO activity_photos (activity_id, file_path) VALUES (?,?)", (aid, path))
                except ValueError as e:
                    flash(str(e), "warning")
        flash("செயல்பாடு புதுப்பிக்கப்பட்டது! / Activity updated!", "success")
        return redirect(url_for("activity_detail", aid=aid))
    photos = query("SELECT id, file_path FROM activity_photos WHERE activity_id=? ORDER BY id", (aid,))
    return render_template("activity_form.html", act=a, photos=photos)


@app.route("/activity/<int:aid>/photo/<int:pid>/delete", methods=["POST"])
@login_required()
def activity_photo_delete(aid, pid):
    a = query("SELECT * FROM activities WHERE id=?", (aid,), one=True)
    if not a or not _can_manage_activity(a):
        abort(403)
    p = query("SELECT file_path FROM activity_photos WHERE id=? AND activity_id=?", (pid, aid), one=True)
    if p:
        fp = os.path.join(BASE_DIR, "static", p["file_path"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        execute("DELETE FROM activity_photos WHERE id=?", (pid,))
        flash("படம் நீக்கப்பட்டது. / Photo removed.", "info")
    return redirect(url_for("activity_edit", aid=aid))


@app.route("/admin/activity/<int:aid>/delete", methods=["POST"])
@login_required(role="admin")
def admin_activity_delete(aid):
    for p in query("SELECT file_path FROM activity_photos WHERE activity_id=?", (aid,)):
        fp = os.path.join(BASE_DIR, "static", p["file_path"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
    execute("DELETE FROM activity_photos WHERE activity_id=?", (aid,))
    execute("DELETE FROM activities WHERE id=?", (aid,))
    flash("செயல்பாடு நிரந்தரமாக நீக்கப்பட்டது. / Activity permanently deleted.", "info")
    return redirect(url_for("admin_activities"))


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
@app.errorhandler(403)
def e403(e):
    return render_template("error.html", code=403,
                           msg="அனுமதி இல்லை / Access denied."), 403


@app.errorhandler(404)
def e404(e):
    return render_template("error.html", code=404,
                           msg="பக்கம் கிடைக்கவில்லை / Page not found."), 404


@app.errorhandler(400)
def e400(e):
    return render_template("error.html", code=400,
                           msg="தவறான கோரிக்கை / Bad request."), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)

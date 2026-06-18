# TVK மக்கள் சேவை மையம் – கல்லாவி
### TVK People's Service Center – Kallavi

A village-level public service & complaint management portal for TVK, Kallavi pilot.
Flask + SQLite + Bootstrap 5. Two roles: **Admin** and **Volunteer**.

---

## 1. What's inside

```
tvkkallavi/
├── app.py              ← all routes, auth, uploads, CSRF
├── init_db.py          ← creates the database + default admin
├── schema.sql          ← database structure (9 tables, 2 views)
├── requirements.txt    ← Python packages
├── Procfile            ← tells Render how to start the app
├── render.yaml         ← one-click Render config
├── .gitignore
├── static/
│   ├── css/style.css   ← TVK red + gold theme
│   ├── js/main.js      ← animated counters
│   ├── img/            ← vijay.jpeg, tvk-flag.jpeg  (your images)
│   └── uploads/        ← complaint / volunteer / activity photos (created at runtime)
└── templates/          ← all pages (home, login, track, gallery, admin/*, volunteer/*)
```

> **Where do images go?** Branding images (Vijay, flag) are already in `static/img/`.
> All other photos are uploaded *through the app* and land in `static/uploads/` automatically — you never place those by hand.

---

## 2. Run it on your computer (Windows / VS Code)

Open the folder in VS Code, then in the terminal:

```bash
# 1. install the packages
pip install -r requirements.txt

# 2. build the database + create the admin account (run ONCE)
python init_db.py

# 3. start the app
python app.py
```

Open **http://localhost:5000** in your browser.

**Default admin login:**
- Username: `admin`
- Password: `admin123`

> Change this immediately. Either reset it after logging in, or set your own
> before step 2:  `set ADMIN_PASSWORD=YourStrongPass`  (PowerShell: `$env:ADMIN_PASSWORD="YourStrongPass"`).

### First things to do as admin
1. Log in → go to **தொண்டர்கள் / Volunteers** → **புதிய தொண்டர்** to create volunteer accounts.
   (Volunteers cannot self-register — only you can create them.)
2. Volunteers log in and register complaints; each gets a tracking ID like `TVK-KAL-2026-0001`.
3. You update status, add an after-photo and resolution remark; the public **Track** page shows the full timeline.

---

## 3. Put it on GitHub

```bash
git init
git add .
git commit -m "TVK Kallavi service portal"
git branch -M main
git remote add origin https://github.com/Aerovant/tvkkallavi.git
git push -u origin main
```

(The `.gitignore` keeps the database and uploaded files out of the repo.)

---

## 4. Deploy free on Render

1. Go to **render.com** → **New** → **Web Service** → connect your GitHub repo.
2. Render auto-detects `render.yaml`. If filling manually instead:
   - **Build Command:** `pip install -r requirements.txt && python init_db.py`
   - **Start Command:** `gunicorn app:app`
   - **Instance type:** Free
3. Under **Environment**, add:
   - `FLASK_SECRET_KEY` → any long random string (Render can generate one)
   - `ADMIN_USERNAME` and `ADMIN_PASSWORD` → your chosen admin credentials
4. Click **Deploy**. Your site goes live at `https://tvkkallavi.onrender.com`.

> **Important note about the free tier and uploads:** Render's free disk is *ephemeral* —
> uploaded photos are wiped whenever the service restarts/redeploys, and the SQLite
> file resets too. That's fine for a pilot demo. For permanent storage later, add a
> Render **Persistent Disk** mounted at the project folder, or move the database to
> Render Postgres and photos to a service like Cloudinary/S3. I can wire either up when you're ready.

---

## 5. Security included
- Passwords hashed (Werkzeug), never stored in plain text
- Session-based login with role separation (admin vs volunteer)
- CSRF token on every form
- File-upload validation (type + 8 MB size limit)
- Soft-delete + full status history (nothing is ever truly erased)
- Aadhaar / Voter ID visible to admins only

---

## 6. Default category & status reference
**Categories:** Water, Road, Street Light, Drainage, Health, Education, Government Scheme, Others
**Statuses:** Pending → In Progress → Resolved → Closed (or Rejected for fake/spam)

---

*Built for the Kallavi pilot. Version 1.*

"""
Gig Worker Platform for Event Staffing
Flask + SQLite backend
- Admin creates organizer accounts
- Organizers login and post jobs / assign workers
- Workers register publicly
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3, os, hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = "gigworker_secret_2024"
DB_PATH = os.path.join(os.path.dirname(__file__), "gig_platform.db")

# ─────────────────────────────────────────
# ADMIN MASTER CREDENTIALS
# ─────────────────────────────────────────
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ─────────────────────────────────────────
# HELPERS — password hashing
# ─────────────────────────────────────────

def hash_password(password):
    """Simple SHA-256 hash for storing passwords safely."""
    return hashlib.sha256(password.encode()).hexdigest()


# ─────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────

def admin_required(f):
    """Protect route — only master admin can access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login as admin to access this page.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def organizer_required(f):
    """Protect route — only logged-in organizers can access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("organizer_logged_in"):
            flash("Please login as an organizer to access this page.", "warning")
            return redirect(url_for("organizer_login"))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur  = conn.cursor()

    # Workers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            phone      TEXT NOT NULL,
            location   TEXT NOT NULL,
            skill      TEXT NOT NULL,
            available  INTEGER DEFAULT 1,
            registered TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # Organizers — created by admin
    cur.execute("""
        CREATE TABLE IF NOT EXISTS organizers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            username     TEXT NOT NULL UNIQUE,
            password     TEXT NOT NULL,
            company      TEXT,
            phone        TEXT,
            active       INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # Jobs — linked to the organizer who posted
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            organizer_id   INTEGER NOT NULL,
            event_name     TEXT NOT NULL,
            location       TEXT NOT NULL,
            event_datetime TEXT NOT NULL,
            workers_needed INTEGER NOT NULL,
            pay_per_worker REAL NOT NULL,
            created_at     TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (organizer_id) REFERENCES organizers(id) ON DELETE CASCADE
        )
    """)

    # Assignments
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL,
            worker_id   INTEGER NOT NULL,
            assigned_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (job_id)    REFERENCES jobs(id)    ON DELETE CASCADE,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
            UNIQUE (job_id, worker_id)
        )
    """)

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════
# PUBLIC ROUTES
# ═══════════════════════════════════════════

@app.route("/")
def index():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    name     = request.form.get("name", "").strip()
    phone    = request.form.get("phone", "").strip()
    location = request.form.get("location", "").strip()
    skill    = request.form.get("skill", "").strip()

    if not all([name, phone, location, skill]):
        flash("All fields are required.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute(
        "INSERT INTO workers (name, phone, location, skill) VALUES (?, ?, ?, ?)",
        (name, phone, location, skill)
    )
    conn.commit()
    conn.close()
    flash(f"Welcome, {name}! You're now registered on the platform. 🎉", "success")
    return redirect(url_for("index"))


@app.route("/jobs")
def jobs():
    """Public job listing page."""
    conn      = get_db()
    jobs_list = conn.execute("""
        SELECT j.*, o.name as organizer_name, o.company
        FROM jobs j
        JOIN organizers o ON j.organizer_id = o.id
        ORDER BY j.id DESC
    """).fetchall()

    enriched = []
    for job in jobs_list:
        count = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE job_id=?", (job["id"],)
        ).fetchone()[0]
        enriched.append({"job": job, "assigned_count": count})
    conn.close()
    return render_template("jobs.html", enriched=enriched)


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    conn = get_db()
    job  = conn.execute("""
        SELECT j.*, o.name as organizer_name, o.company
        FROM jobs j JOIN organizers o ON j.organizer_id = o.id
        WHERE j.id=?
    """, (job_id,)).fetchone()

    if not job:
        flash("Job not found.", "danger")
        conn.close()
        return redirect(url_for("jobs"))

    assigned = conn.execute("""
        SELECT w.* FROM workers w
        JOIN assignments a ON w.id = a.worker_id
        WHERE a.job_id = ?
    """, (job_id,)).fetchall()
    conn.close()
    return render_template("job_detail.html", job=job, assigned=assigned)


# ═══════════════════════════════════════════
# ADMIN LOGIN / LOGOUT
# ═══════════════════════════════════════════

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Welcome back, Admin! 👋", "success")
            return redirect(url_for("admin"))
        flash("Invalid credentials.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("admin_login"))


# ═══════════════════════════════════════════
# ADMIN ROUTES — manage workers + organizers
# ═══════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin():
    """Admin dashboard — workers + organizer accounts."""
    search  = request.args.get("search", "").strip()
    skill_f = request.args.get("skill", "").strip()
    avail_f = request.args.get("available", "").strip()

    conn   = get_db()
    query  = "SELECT * FROM workers WHERE 1=1"
    params = []

    if search:
        like    = f"%{search}%"
        query  += " AND (name LIKE ? OR location LIKE ? OR phone LIKE ?)"
        params += [like, like, like]
    if skill_f:
        query += " AND skill = ?"
        params.append(skill_f)
    if avail_f != "":
        query += " AND available = ?"
        params.append(int(avail_f))

    query  += " ORDER BY id DESC"
    workers = conn.execute(query, params).fetchall()

    organizers = conn.execute("SELECT * FROM organizers ORDER BY id DESC").fetchall()

    total      = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
    available  = conn.execute("SELECT COUNT(*) FROM workers WHERE available=1").fetchone()[0]
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    total_org  = conn.execute("SELECT COUNT(*) FROM organizers").fetchone()[0]
    total_asn  = conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    conn.close()

    return render_template("admin.html",
        workers=workers, organizers=organizers,
        search=search, skill_filter=skill_f, avail_filter=avail_f,
        stats=dict(total=total, available=available,
                   total_jobs=total_jobs, total_organizers=total_org,
                   total_assignments=total_asn))


@app.route("/admin/create_organizer", methods=["GET", "POST"])
@admin_required
def create_organizer():
    """Admin creates a new organizer account."""
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        company  = request.form.get("company", "").strip()
        phone    = request.form.get("phone", "").strip()

        if not all([name, username, password]):
            flash("Name, username and password are required.", "danger")
            return redirect(url_for("create_organizer"))

        conn = get_db()
        # Check if username already exists
        exists = conn.execute(
            "SELECT id FROM organizers WHERE username=?", (username,)
        ).fetchone()

        if exists:
            flash(f"Username '{username}' is already taken. Choose another.", "danger")
            conn.close()
            return redirect(url_for("create_organizer"))

        conn.execute(
            "INSERT INTO organizers (name, username, password, company, phone) VALUES (?, ?, ?, ?, ?)",
            (name, username, hash_password(password), company, phone)
        )
        conn.commit()
        conn.close()
        flash(f"✅ Organizer account created for '{name}'. Username: {username}", "success")
        return redirect(url_for("admin"))

    return render_template("create_organizer.html")


@app.route("/admin/delete_organizer/<int:org_id>", methods=["POST"])
@admin_required
def delete_organizer(org_id):
    conn = get_db()
    conn.execute("DELETE FROM organizers WHERE id=?", (org_id,))
    conn.commit()
    conn.close()
    flash("Organizer account deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/toggle_organizer/<int:org_id>", methods=["POST"])
@admin_required
def toggle_organizer(org_id):
    """Enable or disable an organizer account."""
    conn = get_db()
    org  = conn.execute("SELECT active FROM organizers WHERE id=?", (org_id,)).fetchone()
    if org:
        new_val = 0 if org["active"] else 1
        conn.execute("UPDATE organizers SET active=? WHERE id=?", (new_val, org_id))
        conn.commit()
    conn.close()
    flash("Organizer status updated.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/reset_password/<int:org_id>", methods=["POST"])
@admin_required
def reset_password(org_id):
    """Admin resets an organizer's password."""
    new_pass = request.form.get("new_password", "").strip()
    if not new_pass:
        flash("New password cannot be empty.", "danger")
        return redirect(url_for("admin"))

    conn = get_db()
    conn.execute(
        "UPDATE organizers SET password=? WHERE id=?",
        (hash_password(new_pass), org_id)
    )
    conn.commit()
    conn.close()
    flash("Password reset successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/delete_worker/<int:worker_id>", methods=["POST"])
@admin_required
def delete_worker(worker_id):
    conn = get_db()
    conn.execute("DELETE FROM workers WHERE id=?", (worker_id,))
    conn.commit()
    conn.close()
    flash("Worker removed.", "info")
    return redirect(url_for("admin"))


@app.route("/toggle_availability/<int:worker_id>", methods=["POST"])
@admin_required
def toggle_availability(worker_id):
    conn   = get_db()
    worker = conn.execute("SELECT available FROM workers WHERE id=?", (worker_id,)).fetchone()
    if worker:
        conn.execute("UPDATE workers SET available=? WHERE id=?",
                     (0 if worker["available"] else 1, worker_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin"))


# ═══════════════════════════════════════════
# ORGANIZER LOGIN / LOGOUT
# ═══════════════════════════════════════════

@app.route("/organizer/login", methods=["GET", "POST"])
def organizer_login():
    if session.get("organizer_logged_in"):
        return redirect(url_for("organizer_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        org  = conn.execute(
            "SELECT * FROM organizers WHERE username=? AND password=?",
            (username, hash_password(password))
        ).fetchone()
        conn.close()

        if org:
            if not org["active"]:
                flash("Your account has been disabled. Contact admin.", "danger")
                return redirect(url_for("organizer_login"))
            # Save organizer info in session
            session["organizer_logged_in"] = True
            session["organizer_id"]        = org["id"]
            session["organizer_name"]      = org["name"]
            session["organizer_company"]   = org["company"] or ""
            flash(f"Welcome, {org['name']}! 🎉", "success")
            return redirect(url_for("organizer_dashboard"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("organizer_login.html")


@app.route("/organizer/logout")
def organizer_logout():
    session.pop("organizer_logged_in", None)
    session.pop("organizer_id", None)
    session.pop("organizer_name", None)
    session.pop("organizer_company", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("organizer_login"))


# ═══════════════════════════════════════════
# ORGANIZER ROUTES — post jobs, assign workers
# ═══════════════════════════════════════════

@app.route("/organizer/dashboard")
@organizer_required
def organizer_dashboard():
    """Organizer sees only their own jobs."""
    org_id    = session["organizer_id"]
    conn      = get_db()
    jobs_list = conn.execute(
        "SELECT * FROM jobs WHERE organizer_id=? ORDER BY id DESC", (org_id,)
    ).fetchall()

    enriched = []
    for job in jobs_list:
        count = conn.execute(
            "SELECT COUNT(*) FROM assignments WHERE job_id=?", (job["id"],)
        ).fetchone()[0]
        enriched.append({"job": job, "assigned_count": count})

    total_jobs = len(jobs_list)
    total_asn  = conn.execute("""
        SELECT COUNT(*) FROM assignments a
        JOIN jobs j ON a.job_id = j.id
        WHERE j.organizer_id=?
    """, (org_id,)).fetchone()[0]
    total_workers = conn.execute("SELECT COUNT(*) FROM workers WHERE available=1").fetchone()[0]

    conn.close()
    return render_template("organizer_dashboard.html",
        enriched=enriched,
        stats=dict(total_jobs=total_jobs,
                   total_assignments=total_asn,
                   available_workers=total_workers))


@app.route("/organizer/add_job", methods=["GET", "POST"])
@organizer_required
def organizer_add_job():
    """Organizer posts a new job."""
    if request.method == "POST":
        event_name     = request.form.get("event_name", "").strip()
        location       = request.form.get("location", "").strip()
        event_datetime = request.form.get("event_datetime", "").strip()
        workers_needed = request.form.get("workers_needed", "0").strip()
        pay_per_worker = request.form.get("pay_per_worker", "0").strip()

        if not all([event_name, location, event_datetime, workers_needed, pay_per_worker]):
            flash("All fields are required.", "danger")
            return redirect(url_for("organizer_add_job"))

        conn = get_db()
        conn.execute(
            """INSERT INTO jobs (organizer_id, event_name, location, event_datetime, workers_needed, pay_per_worker)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session["organizer_id"], event_name, location,
             event_datetime, int(workers_needed), float(pay_per_worker))
        )
        conn.commit()
        conn.close()
        flash(f"✅ Job '{event_name}' posted! 📢 Workers have been notified.", "success")
        return redirect(url_for("organizer_dashboard"))

    return render_template("add_job.html",
                           form_action=url_for("organizer_add_job"),
                           cancel_url=url_for("organizer_dashboard"))


@app.route("/organizer/delete_job/<int:job_id>", methods=["POST"])
@organizer_required
def organizer_delete_job(job_id):
    """Organizer deletes their own job."""
    org_id = session["organizer_id"]
    conn   = get_db()
    # Make sure organizer can only delete their OWN jobs
    job = conn.execute(
        "SELECT id FROM jobs WHERE id=? AND organizer_id=?", (job_id, org_id)
    ).fetchone()

    if job:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.execute("DELETE FROM assignments WHERE job_id=?", (job_id,))
        conn.commit()
        flash("Job deleted.", "info")
    else:
        flash("You can only delete your own jobs.", "danger")

    conn.close()
    return redirect(url_for("organizer_dashboard"))


@app.route("/organizer/assign/<int:job_id>", methods=["GET", "POST"])
@organizer_required
def organizer_assign(job_id):
    """Organizer assigns workers to their job."""
    org_id = session["organizer_id"]
    conn   = get_db()

    # Security: organizer can only manage their OWN jobs
    job = conn.execute(
        "SELECT * FROM jobs WHERE id=? AND organizer_id=?", (job_id, org_id)
    ).fetchone()

    if not job:
        flash("Job not found or access denied.", "danger")
        conn.close()
        return redirect(url_for("organizer_dashboard"))

    if request.method == "POST":
        worker_ids = request.form.getlist("worker_ids")
        if not worker_ids:
            flash("Please select at least one worker.", "warning")
            return redirect(url_for("organizer_assign", job_id=job_id))

        assigned = 0
        for wid in worker_ids:
            try:
                conn.execute(
                    "INSERT INTO assignments (job_id, worker_id) VALUES (?, ?)",
                    (job_id, int(wid))
                )
                assigned += 1
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        flash(f"✅ {assigned} worker(s) assigned to '{job['event_name']}'.", "success")
        conn.close()
        return redirect(url_for("organizer_assign", job_id=job_id))

    available_workers = conn.execute("""
        SELECT * FROM workers WHERE available=1
        AND id NOT IN (SELECT worker_id FROM assignments WHERE job_id=?)
        ORDER BY name
    """, (job_id,)).fetchall()

    already_assigned = conn.execute("""
        SELECT w.* FROM workers w
        JOIN assignments a ON w.id = a.worker_id
        WHERE a.job_id=?
    """, (job_id,)).fetchall()

    conn.close()
    return render_template("assign.html", job=job,
        available_workers=available_workers,
        already_assigned=already_assigned,
        unassign_url="organizer_unassign",
        back_url=url_for("organizer_dashboard"))


@app.route("/organizer/unassign/<int:job_id>/<int:worker_id>", methods=["POST"])
@organizer_required
def organizer_unassign(job_id, worker_id):
    org_id = session["organizer_id"]
    conn   = get_db()
    # Verify ownership
    job = conn.execute(
        "SELECT id FROM jobs WHERE id=? AND organizer_id=?", (job_id, org_id)
    ).fetchone()
    if job:
        conn.execute(
            "DELETE FROM assignments WHERE job_id=? AND worker_id=?",
            (job_id, worker_id)
        )
        conn.commit()
        flash("Worker unassigned.", "info")
    conn.close()
    return redirect(url_for("organizer_assign", job_id=job_id))


# ═══════════════════════════════════════════
# ADMIN — can also manage all jobs
# ═══════════════════════════════════════════

@app.route("/delete_job/<int:job_id>", methods=["POST"])
@admin_required
def delete_job(job_id):
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.execute("DELETE FROM assignments WHERE job_id=?", (job_id,))
    conn.commit()
    conn.close()
    flash("Job deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/assign/<int:job_id>", methods=["GET", "POST"])
@admin_required
def assign(job_id):
    conn = get_db()
    job  = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

    if not job:
        flash("Job not found.", "danger")
        conn.close()
        return redirect(url_for("admin"))

    if request.method == "POST":
        worker_ids = request.form.getlist("worker_ids")
        if not worker_ids:
            flash("Select at least one worker.", "warning")
            return redirect(url_for("assign", job_id=job_id))

        assigned = 0
        for wid in worker_ids:
            try:
                conn.execute("INSERT INTO assignments (job_id, worker_id) VALUES (?, ?)",
                             (job_id, int(wid)))
                assigned += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        flash(f"✅ {assigned} worker(s) assigned.", "success")
        conn.close()
        return redirect(url_for("assign", job_id=job_id))

    available_workers = conn.execute("""
        SELECT * FROM workers WHERE available=1
        AND id NOT IN (SELECT worker_id FROM assignments WHERE job_id=?)
        ORDER BY name
    """, (job_id,)).fetchall()

    already_assigned = conn.execute("""
        SELECT w.* FROM workers w
        JOIN assignments a ON w.id = a.worker_id
        WHERE a.job_id=?
    """, (job_id,)).fetchall()

    conn.close()
    return render_template("assign.html", job=job,
        available_workers=available_workers,
        already_assigned=already_assigned,
        unassign_url="unassign",
        back_url=url_for("admin"))


@app.route("/unassign/<int:job_id>/<int:worker_id>", methods=["POST"])
@admin_required
def unassign(job_id, worker_id):
    conn = get_db()
    conn.execute("DELETE FROM assignments WHERE job_id=? AND worker_id=?",
                 (job_id, worker_id))
    conn.commit()
    conn.close()
    flash("Worker unassigned.", "info")
    return redirect(url_for("assign", job_id=job_id))


# ─────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

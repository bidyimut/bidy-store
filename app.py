import os
import uuid
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, abort, g, jsonify)
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Gunakan secret key dari environment variable jika ada (lebih aman di produksi)
app.secret_key = os.environ.get("SECRET_KEY", "kunci-rahasia-bidy-store-123456")

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(os.path.dirname(__file__), "toko_buku.db")

# Admin credentials (bisa diatur via environment variable agar aman jika repo GitHub bersifat publik)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ---------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    """Create tables and seed initial books if empty."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL DEFAULT 0,
            rating REAL NOT NULL DEFAULT 0,
            pages INTEGER NOT NULL DEFAULT 0,
            c1 TEXT NOT NULL DEFAULT '#333',
            c2 TEXT NOT NULL DEFAULT '#111',
            description TEXT NOT NULL DEFAULT '',
            cover_image TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS featured_books (
            slot INTEGER PRIMARY KEY CHECK(slot IN (1, 2, 3)),
            book_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            payment_method TEXT NOT NULL DEFAULT 'Transfer Bank',
            total INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            book_title TEXT NOT NULL,
            book_author TEXT NOT NULL,
            price INTEGER NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            subtotal INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    """)

    # Seed data if books table is empty
    count = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    if count == 0:
        seed_books = [
            ("Laskar Pelangi", "Andrea Hirata", "Fiksi", 89000, 4.8, 529,
             "#f2994a", "#c0392b",
             "Kisah persahabatan sepuluh anak di Belitung yang berjuang meraih pendidikan di tengah keterbatasan."),
            ("Bumi Manusia", "Pramoedya Ananta Toer", "Sastra", 125000, 4.9, 535,
             "#355c7d", "#2c3e50",
             "Novel sejarah tentang Minke, pribumi terpelajar yang berhadapan dengan ketidakadilan era kolonial."),
            ("Filosofi Teras", "Henry Manampiring", "Pengembangan Diri", 98000, 4.7, 346,
             "#27ae60", "#145a32",
             "Pengantar filsafat Stoa yang praktis untuk menghadapi stres dan emosi negatif sehari-hari."),
            ("Atomic Habits", "James Clear", "Pengembangan Diri", 108000, 4.9, 352,
             "#f1c40f", "#d68910",
             "Cara sederhana membangun kebiasaan baik dan menghilangkan kebiasaan buruk lewat perubahan kecil."),
            ("Sapiens", "Yuval Noah Harari", "Sains & Sejarah", 135000, 4.8, 512,
             "#8e44ad", "#4a235a",
             "Perjalanan singkat umat manusia dari zaman batu hingga era teknologi modern."),
            ("Dilan 1990", "Pidi Baiq", "Romansa", 79000, 4.5, 344,
             "#e84393", "#a8326f",
             "Kisah cinta remaja di Bandung tahun 1990 yang manis, lucu, dan tak terlupakan."),
            ("Cantik Itu Luka", "Eka Kurniawan", "Sastra", 115000, 4.6, 520,
             "#16a085", "#0b5345",
             "Saga keluarga lintas generasi dengan nuansa realisme magis di tanah Halimunda."),
            ("Python untuk Pemula", "Tim Kodekita", "Teknologi", 95000, 4.6, 280,
             "#2980b9", "#1b4f72",
             "Belajar pemrograman Python dari nol dengan contoh proyek nyata yang mudah diikuti."),
            ("Hujan", "Tere Liye", "Fiksi", 85000, 4.7, 320,
             "#5dade2", "#21618c",
             "Fiksi ilmiah romantis tentang kenangan, kehilangan, dan harapan di masa depan."),
            ("Rich Dad Poor Dad", "Robert Kiyosaki", "Bisnis", 92000, 4.5, 336,
             "#2ecc71", "#1d8348",
             "Pelajaran keuangan dari dua figur ayah yang mengubah cara pandang tentang uang."),
            ("Zero to One", "Peter Thiel", "Bisnis", 105000, 4.6, 224,
             "#34495e", "#17202a",
             "Catatan tentang startup dan cara membangun sesuatu yang benar-benar baru."),
            ("Pulang", "Leila S. Chudori", "Sastra", 99000, 4.7, 461,
             "#d35400", "#6e2c00",
             "Kisah eksil politik Indonesia di Paris dan pencarian makna rumah yang sesungguhnya."),
        ]
        db.executemany(
            "INSERT INTO books (title, author, category, price, rating, pages, c1, c2, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", seed_books
        )
        db.commit()
    db.close()


# Initialize DB on startup
init_db()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def rupiah(value):
    return "Rp " + f"{int(value):,}".replace(",", ".")


app.jinja_env.filters["rupiah"] = rupiah


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_all_books():
    db = get_db()
    return [dict(row) for row in db.execute("SELECT * FROM books ORDER BY id").fetchall()]


def get_book(book_id):
    db = get_db()
    row = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return dict(row) if row else None


def get_categories():
    db = get_db()
    rows = db.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def get_cart():
    return session.setdefault("cart", {})


def cart_items():
    items, total = [], 0
    for book_id, qty in get_cart().items():
        book = get_book(int(book_id))
        if book:
            subtotal = book["price"] * qty
            total += subtotal
            items.append({"book": book, "qty": qty, "subtotal": subtotal})
    return items, total


@app.context_processor
def inject_globals():
    return {
        "cart_count": sum(get_cart().values()),
        "categories": get_categories(),
        "is_admin": session.get("is_admin", False),
    }


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Silakan login sebagai admin terlebih dahulu.", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------
def get_featured_books():
    """Ambil 3 buku featured dari tabel featured_books, fallback ke rating tertinggi."""
    db = get_db()
    rows = db.execute(
        "SELECT b.* FROM featured_books f JOIN books b ON f.book_id = b.id ORDER BY f.slot"
    ).fetchall()
    if len(rows) == 3:
        return [dict(r) for r in rows]
    # fallback jika belum dikonfigurasi
    all_books = get_all_books()
    return sorted(all_books, key=lambda b: -b["rating"])[:3]


@app.route("/")
def home():
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("kategori", "").strip()
    sort = request.args.get("urut", "")

    books = get_all_books()
    if q:
        books = [b for b in books if q in b["title"].lower() or q in b["author"].lower()]
    if cat:
        books = [b for b in books if b["category"] == cat]
    if sort == "murah":
        books = sorted(books, key=lambda b: b["price"])
    elif sort == "mahal":
        books = sorted(books, key=lambda b: -b["price"])
    elif sort == "rating":
        books = sorted(books, key=lambda b: -b["rating"])

    featured = get_featured_books()
    return render_template("index.html", books=books, featured=featured,
                           q=q, active_cat=cat, sort=sort)


@app.route("/buku/<int:book_id>")
def detail(book_id):
    book = get_book(book_id) or abort(404)
    all_books = get_all_books()
    related = [b for b in all_books if b["category"] == book["category"] and b["id"] != book_id][:4]
    return render_template("detail.html", book=book, related=related)


@app.route("/keranjang")
def cart():
    items, total = cart_items()
    return render_template("cart.html", items=items, total=total)


@app.route("/keranjang/tambah/<int:book_id>", methods=["POST"])
def cart_add(book_id):
    if not get_book(book_id):
        abort(404)
    c = get_cart()
    c[str(book_id)] = c.get(str(book_id), 0) + 1
    session.modified = True
    book = get_book(book_id)
    flash(f"\"{book['title']}\" ditambahkan ke keranjang.", "ok")
    return redirect(request.referrer or url_for("home"))


@app.route("/keranjang/ubah/<int:book_id>", methods=["POST"])
def cart_update(book_id):
    c = get_cart()
    try:
        qty = int(request.form.get("qty", 1))
    except ValueError:
        qty = 1
    if qty <= 0:
        c.pop(str(book_id), None)
    else:
        c[str(book_id)] = min(qty, 99)
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/keranjang/hapus/<int:book_id>", methods=["POST"])
def cart_remove(book_id):
    get_cart().pop(str(book_id), None)
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = cart_items()
    if not items:
        return redirect(url_for("cart"))
    if request.method == "POST":
        name = request.form.get("name", "").strip() or "Pelanggan"
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        payment = request.form.get("payment", "Transfer Bank")

        # Generate order code
        order_code = "LK-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()

        db = get_db()
        cur = db.execute(
            "INSERT INTO orders (order_code, customer_name, phone, address, payment_method, total) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_code, name, phone, address, payment, total)
        )
        order_id = cur.lastrowid

        for it in items:
            db.execute(
                "INSERT INTO order_items (order_id, book_id, book_title, book_author, price, qty, subtotal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (order_id, it["book"]["id"], it["book"]["title"], it["book"]["author"],
                 it["book"]["price"], it["qty"], it["subtotal"])
            )
        db.commit()

        session["cart"] = {}
        return redirect(url_for("receipt", order_code=order_code))
    return render_template("checkout.html", items=items, total=total)


# ---------------------------------------------------------------
# Receipt / Struk
# ---------------------------------------------------------------
@app.route("/struk/<order_code>")
def receipt(order_code):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
    if not order:
        abort(404)
    order = dict(order)
    items = [dict(r) for r in db.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order["id"],)).fetchall()]
    return render_template("receipt.html", order=order, items=items)


# ---------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Berhasil login sebagai admin.", "ok")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Username atau password salah.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Berhasil logout dari admin.", "ok")
    return redirect(url_for("home"))


# ---------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    total_books = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_revenue = db.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()[0]
    recent_orders = [dict(r) for r in db.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT 5").fetchall()]
    return render_template("admin/dashboard.html",
                           total_books=total_books, total_orders=total_orders,
                           total_revenue=total_revenue, recent_orders=recent_orders)


# ---------------------------------------------------------------
# Admin — Kelola Buku Featured (Halaman Utama)
# ---------------------------------------------------------------
@app.route("/admin/featured", methods=["GET", "POST"])
@admin_required
def admin_featured():
    db = get_db()
    all_books = get_all_books()

    if request.method == "POST":
        slot1 = request.form.get("slot_1", type=int)
        slot2 = request.form.get("slot_2", type=int)
        slot3 = request.form.get("slot_3", type=int)

        slots = [slot1, slot2, slot3]

        # Validasi: semua slot harus diisi & tidak boleh sama
        if not all(slots):
            flash("Semua slot harus dipilih.", "error")
            return redirect(url_for("admin_featured"))
        if len(set(slots)) != 3:
            flash("Ketiga buku featured harus berbeda.", "error")
            return redirect(url_for("admin_featured"))

        # Simpan ke tabel featured_books
        db.execute("DELETE FROM featured_books")
        for i, book_id in enumerate(slots, start=1):
            db.execute(
                "INSERT INTO featured_books (slot, book_id) VALUES (?, ?)",
                (i, book_id)
            )
        db.commit()
        flash("Buku featured halaman utama berhasil diperbarui! 🎉", "ok")
        return redirect(url_for("admin_featured"))

    # GET — ambil featured saat ini
    rows = db.execute(
        "SELECT f.slot, b.* FROM featured_books f JOIN books b ON f.book_id = b.id ORDER BY f.slot"
    ).fetchall()
    current = {r["slot"]: dict(r) for r in rows}

    return render_template("admin/featured.html", all_books=all_books, current=current)


# ---------------------------------------------------------------
# Admin — Kelola Buku
# ---------------------------------------------------------------
@app.route("/admin/buku")
@admin_required
def admin_books():
    books = get_all_books()
    return render_template("admin/books.html", books=books)


@app.route("/admin/buku/tambah", methods=["GET", "POST"])
@admin_required
def admin_book_add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        try:
            price = int(float(request.form.get("price", 0) or 0))
        except (ValueError, TypeError):
            price = 0
        try:
            rating = round(min(5.0, max(0.0, float(request.form.get("rating", 0) or 0))), 1)
        except (ValueError, TypeError):
            rating = 0.0
        try:
            pages = int(request.form.get("pages", 0) or 0)
        except (ValueError, TypeError):
            pages = 0
        c1 = request.form.get("c1", "#333333")
        c2 = request.form.get("c2", "#111111")
        desc = request.form.get("description", "").strip()

        cover_image = None
        if "cover" in request.files:
            file = request.files["cover"]
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit(".", 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                cover_image = filename

        db = get_db()
        db.execute(
            "INSERT INTO books (title, author, category, price, rating, pages, c1, c2, description, cover_image) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, author, category, price, rating, pages, c1, c2, desc, cover_image)
        )
        db.commit()
        flash(f"Buku \"{title}\" berhasil ditambahkan.", "ok")
        return redirect(url_for("admin_books"))
    return render_template("admin/book_form.html", book=None, action="Tambah")


@app.route("/admin/buku/edit/<int:book_id>", methods=["GET", "POST"])
@admin_required
def admin_book_edit(book_id):
    book = get_book(book_id) or abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        try:
            price = int(float(request.form.get("price", 0) or 0))
        except (ValueError, TypeError):
            price = 0
        try:
            rating = round(min(5.0, max(0.0, float(request.form.get("rating", 0) or 0))), 1)
        except (ValueError, TypeError):
            rating = 0.0
        try:
            pages = int(request.form.get("pages", 0) or 0)
        except (ValueError, TypeError):
            pages = 0
        c1 = request.form.get("c1", "#333333")
        c2 = request.form.get("c2", "#111111")
        desc = request.form.get("description", "").strip()

        cover_image = book.get("cover_image")
        if "cover" in request.files:
            file = request.files["cover"]
            if file and file.filename and allowed_file(file.filename):
                # Remove old cover
                if cover_image:
                    old_path = os.path.join(UPLOAD_FOLDER, cover_image)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                ext = file.filename.rsplit(".", 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                cover_image = filename

        db = get_db()
        db.execute(
            "UPDATE books SET title=?, author=?, category=?, price=?, rating=?, pages=?, "
            "c1=?, c2=?, description=?, cover_image=? WHERE id=?",
            (title, author, category, price, rating, pages, c1, c2, desc, cover_image, book_id)
        )
        db.commit()
        flash(f"Buku \"{title}\" berhasil diperbarui.", "ok")
        return redirect(url_for("admin_books"))
    return render_template("admin/book_form.html", book=book, action="Edit")


@app.route("/admin/buku/hapus/<int:book_id>", methods=["POST"])
@admin_required
def admin_book_delete(book_id):
    book = get_book(book_id)
    if book:
        if book.get("cover_image"):
            old_path = os.path.join(UPLOAD_FOLDER, book["cover_image"])
            if os.path.exists(old_path):
                os.remove(old_path)
        db = get_db()
        db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        db.commit()
        flash(f"Buku \"{book['title']}\" berhasil dihapus.", "ok")
    return redirect(url_for("admin_books"))


# ---------------------------------------------------------------
# Admin — Kelola Pesanan
# ---------------------------------------------------------------
@app.route("/admin/pesanan")
@admin_required
def admin_orders():
    db = get_db()
    orders = [dict(r) for r in db.execute(
        "SELECT * FROM orders ORDER BY created_at DESC").fetchall()]
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/pesanan/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    order = dict(order)
    items = [dict(r) for r in db.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()]
    return render_template("admin/order_detail.html", order=order, items=items)


@app.route("/admin/pesanan/hapus/<int:order_id>", methods=["POST"])
@admin_required
def admin_order_delete(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order:
        order_code = order["order_code"]
        db.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        db.commit()
        flash(f"Pesanan {order_code} berhasil dihapus.", "ok")
    else:
        flash("Pesanan tidak ditemukan.", "error")
    return redirect(url_for("admin_orders"))


# ---------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------
@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)

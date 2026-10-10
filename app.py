"""
Pharmacy Stock Management System
---------------------------------
A Flask + SQLite app with 4 modules:

1. Medicine / Inventory  - User search, Admin add/update/delete stock
2. Supplier Management   - add/update/delete/search suppliers, view purchase history
3. Sales & Billing (POS) - cart-based checkout, invoices, refunds
4. Reports & Analytics   - low stock, expired stock, top sellers, revenue, CSV export
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import sqlite3
from datetime import date, datetime, timedelta
import csv
import io

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # only for flash messages + cart session, fine for a student project

DB_NAME = "pharmacy.db"
LOW_STOCK_THRESHOLD = 10


# =========================================================
# DATABASE HELPERS
# =========================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Creates all tables if they don't exist, and migrates older databases."""
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            batch_number TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            unit_price REAL NOT NULL DEFAULT 0,
            supplier_id INTEGER,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            customer_name TEXT,
            sale_date TEXT NOT NULL,
            subtotal REAL NOT NULL,
            discount REAL NOT NULL DEFAULT 0,
            tax REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            medicine_id INTEGER,
            medicine_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales (id)
        )
    """)

    # --- Migration: older databases (created before this update) won't have
    # unit_price / supplier_id on medicines yet. Add them if missing. ---
    existing_cols = [row["name"] for row in conn.execute("PRAGMA table_info(medicines)")]
    if "unit_price" not in existing_cols:
        conn.execute("ALTER TABLE medicines ADD COLUMN unit_price REAL NOT NULL DEFAULT 0")
    if "supplier_id" not in existing_cols:
        conn.execute("ALTER TABLE medicines ADD COLUMN supplier_id INTEGER")

    conn.commit()
    conn.close()


# =========================================================
# MODULE 1: MEDICINE / INVENTORY
# =========================================================

@app.route("/")
def index():
    """User-facing page: search medicine availability."""
    query = request.args.get("q", "").strip()
    conn = get_db_connection()

    if query:
        medicines = conn.execute(
            "SELECT * FROM medicines WHERE name LIKE ? ORDER BY name",
            (f"%{query}%",)
        ).fetchall()
    else:
        medicines = conn.execute("SELECT * FROM medicines ORDER BY name").fetchall()

    conn.close()
    today = date.today().isoformat()
    return render_template("index.html", medicines=medicines, query=query, today=today)


@app.route("/admin")
def admin():
    """Admin dashboard: view all stock, highlight expired batches."""
    conn = get_db_connection()
    medicines = conn.execute("""
        SELECT medicines.*, suppliers.name AS supplier_name
        FROM medicines
        LEFT JOIN suppliers ON medicines.supplier_id = suppliers.id
        ORDER BY medicines.expiry_date
    """).fetchall()
    suppliers = conn.execute("SELECT * FROM suppliers WHERE status = 'active' ORDER BY name").fetchall()
    conn.close()
    today = date.today().isoformat()
    return render_template("admin.html", medicines=medicines, suppliers=suppliers, today=today)


@app.route("/admin/add", methods=["POST"])
def add_medicine():
    """Admin adds a new drug stock entry, optionally linked to a supplier."""
    name = request.form["name"].strip()
    dosage = request.form["dosage"].strip()
    quantity = request.form["quantity"].strip()
    batch_number = request.form["batch_number"].strip()
    expiry_date = request.form["expiry_date"].strip()
    unit_price = request.form.get("unit_price", "0").strip() or "0"
    supplier_id = request.form.get("supplier_id") or None

    if not (name and dosage and quantity and batch_number and expiry_date):
        flash("All fields are required.", "error")
        return redirect(url_for("admin"))

    conn = get_db_connection()
    conn.execute(
        """INSERT INTO medicines (name, dosage, quantity, batch_number, expiry_date, unit_price, supplier_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, dosage, int(quantity), batch_number, expiry_date, float(unit_price), supplier_id)
    )
    conn.commit()
    conn.close()
    flash(f"Added {name} to stock.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/update/<int:medicine_id>", methods=["POST"])
def update_medicine(medicine_id):
    """Admin updates dosage, quantity, and price for an existing medicine."""
    dosage = request.form["dosage"].strip()
    quantity = request.form["quantity"].strip()
    unit_price = request.form.get("unit_price", "0").strip() or "0"

    conn = get_db_connection()
    conn.execute(
        "UPDATE medicines SET dosage = ?, quantity = ?, unit_price = ? WHERE id = ?",
        (dosage, int(quantity), float(unit_price), medicine_id)
    )
    conn.commit()
    conn.close()
    flash("Medicine updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete/<int:medicine_id>", methods=["POST"])
def delete_medicine(medicine_id):
    """Admin removes a batch (e.g. after disposing of expired stock)."""
    conn = get_db_connection()
    conn.execute("DELETE FROM medicines WHERE id = ?", (medicine_id,))
    conn.commit()
    conn.close()
    flash("Batch removed.", "success")
    return redirect(url_for("admin"))


# =========================================================
# MODULE 2: SUPPLIER MANAGEMENT
# =========================================================

@app.route("/suppliers")
def suppliers():
    """1. List + search suppliers."""
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    if query:
        rows = conn.execute(
            "SELECT * FROM suppliers WHERE name LIKE ? ORDER BY name", (f"%{query}%",)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    conn.close()
    return render_template("suppliers.html", suppliers=rows, query=query)


@app.route("/suppliers/add", methods=["POST"])
def add_supplier():
    """2. Add a new supplier."""
    name = request.form["name"].strip()
    contact_person = request.form.get("contact_person", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    address = request.form.get("address", "").strip()

    if not name:
        flash("Supplier name is required.", "error")
        return redirect(url_for("suppliers"))

    conn = get_db_connection()
    conn.execute(
        """INSERT INTO suppliers (name, contact_person, phone, email, address, status)
           VALUES (?, ?, ?, ?, ?, 'active')""",
        (name, contact_person, phone, email, address)
    )
    conn.commit()
    conn.close()
    flash(f"Added supplier {name}.", "success")
    return redirect(url_for("suppliers"))


@app.route("/suppliers/update/<int:supplier_id>", methods=["POST"])
def update_supplier(supplier_id):
    """3. Edit an existing supplier's details."""
    contact_person = request.form.get("contact_person", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    address = request.form.get("address", "").strip()

    conn = get_db_connection()
    conn.execute(
        "UPDATE suppliers SET contact_person = ?, phone = ?, email = ?, address = ? WHERE id = ?",
        (contact_person, phone, email, address, supplier_id)
    )
    conn.commit()
    conn.close()
    flash("Supplier updated.", "success")
    return redirect(url_for("suppliers"))


@app.route("/suppliers/toggle/<int:supplier_id>", methods=["POST"])
def toggle_supplier_status(supplier_id):
    """4. Activate/deactivate a supplier (deactivated suppliers won't show when adding stock)."""
    conn = get_db_connection()
    current = conn.execute("SELECT status FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()

    if current is None:
        conn.close()
        flash("Supplier not found.", "error")
        return redirect(url_for("suppliers"))

    new_status = "inactive" if current["status"] == "active" else "active"
    conn.execute("UPDATE suppliers SET status = ? WHERE id = ?", (new_status, supplier_id))
    conn.commit()
    conn.close()
    flash(f"Supplier marked {new_status}.", "success")
    return redirect(url_for("suppliers"))


@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
def delete_supplier(supplier_id):
    """5. Delete a supplier (only if no stock currently references them)."""
    conn = get_db_connection()
    linked = conn.execute(
        "SELECT COUNT(*) AS c FROM medicines WHERE supplier_id = ?", (supplier_id,)
    ).fetchone()["c"]

    if linked > 0:
        conn.close()
        flash("Can't delete: this supplier has linked stock. Deactivate them instead.", "error")
        return redirect(url_for("suppliers"))

    conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    conn.commit()
    conn.close()
    flash("Supplier deleted.", "success")
    return redirect(url_for("suppliers"))


@app.route("/suppliers/<int:supplier_id>")
def supplier_detail(supplier_id):
    """6. View a supplier's profile and their purchase/stock history."""
    conn = get_db_connection()
    supplier = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    history = get_supplier_purchase_history(conn, supplier_id)
    conn.close()

    if supplier is None:
        flash("Supplier not found.", "error")
        return redirect(url_for("suppliers"))

    return render_template("supplier_detail.html", supplier=supplier, history=history)


def get_supplier_purchase_history(conn, supplier_id):
    """7. Helper: all medicine batches ever supplied by this supplier."""
    return conn.execute(
        "SELECT * FROM medicines WHERE supplier_id = ? ORDER BY expiry_date", (supplier_id,)
    ).fetchall()


def get_active_suppliers(conn):
    """8. Helper: active suppliers, used to populate the dropdown on the Add Stock form."""
    return conn.execute("SELECT * FROM suppliers WHERE status = 'active' ORDER BY name").fetchall()


def get_supplier_by_id(conn, supplier_id):
    """9. Helper: fetch a single supplier record."""
    return conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()


# =========================================================
# MODULE 3: SALES & BILLING (POS)
# =========================================================

def get_cart():
    """Helper: current shopping cart, kept in the browser session."""
    return session.get("cart", [])


def save_cart(cart):
    session["cart"] = cart


def generate_invoice_number(sale_id):
    """10. Helper: build a human-readable invoice number from the sale's row id."""
    return f"INV-{date.today().strftime('%Y%m%d')}-{sale_id:04d}"


@app.route("/sales/new")
def sales_new():
    """1. POS screen: browse in-stock medicines and view/build the current cart."""
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    today = date.today().isoformat()

    sql = "SELECT * FROM medicines WHERE quantity > 0 AND expiry_date >= ?"
    params = [today]
    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY name"

    available_medicines = conn.execute(sql, params).fetchall()
    conn.close()

    cart = get_cart()
    subtotal = sum(item["unit_price"] * item["quantity"] for item in cart)

    return render_template(
        "sales_new.html",
        medicines=available_medicines, cart=cart, subtotal=subtotal, query=query
    )


@app.route("/sales/add_item", methods=["POST"])
def add_to_cart():
    """2. Add a medicine (with quantity) to the in-progress cart."""
    medicine_id = int(request.form["medicine_id"])
    quantity = int(request.form.get("quantity", 1))

    conn = get_db_connection()
    med = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    conn.close()

    if med is None:
        flash("Medicine not found.", "error")
        return redirect(url_for("sales_new"))

    if quantity < 1 or quantity > med["quantity"]:
        flash(f"Only {med['quantity']} units of {med['name']} available.", "error")
        return redirect(url_for("sales_new"))

    cart = get_cart()
    for item in cart:
        if item["medicine_id"] == medicine_id:
            item["quantity"] = min(item["quantity"] + quantity, med["quantity"])
            break
    else:
        cart.append({
            "medicine_id": medicine_id,
            "name": med["name"],
            "unit_price": med["unit_price"],
            "quantity": quantity,
        })

    save_cart(cart)
    flash(f"Added {med['name']} to cart.", "success")
    return redirect(url_for("sales_new"))


@app.route("/sales/remove_item/<int:medicine_id>", methods=["POST"])
def remove_from_cart(medicine_id):
    """3. Remove a line item from the cart."""
    cart = [item for item in get_cart() if item["medicine_id"] != medicine_id]
    save_cart(cart)
    return redirect(url_for("sales_new"))


@app.route("/sales/update_item/<int:medicine_id>", methods=["POST"])
def update_cart_item(medicine_id):
    """4. Change the quantity of a line item already in the cart."""
    quantity = int(request.form.get("quantity", 1))
    cart = get_cart()
    for item in cart:
        if item["medicine_id"] == medicine_id:
            item["quantity"] = max(1, quantity)
            break
    save_cart(cart)
    return redirect(url_for("sales_new"))


@app.route("/sales/checkout", methods=["POST"])
def checkout():
    """5. Finalize the sale: create the invoice, save line items, and deduct stock."""
    cart = get_cart()
    if not cart:
        flash("Cart is empty.", "error")
        return redirect(url_for("sales_new"))

    customer_name = request.form.get("customer_name", "Walk-in Customer").strip() or "Walk-in Customer"
    discount = float(request.form.get("discount", 0) or 0)
    tax_percent = float(request.form.get("tax_percent", 0) or 0)

    subtotal = sum(item["unit_price"] * item["quantity"] for item in cart)
    tax_amount = (subtotal - discount) * (tax_percent / 100)
    total = subtotal - discount + tax_amount

    conn = get_db_connection()
    cur = conn.execute(
        """INSERT INTO sales (invoice_no, customer_name, sale_date, subtotal, discount, tax, total, status)
           VALUES ('', ?, ?, ?, ?, ?, ?, 'completed')""",
        (customer_name, datetime.now().isoformat(timespec="seconds"), subtotal, discount, tax_amount, total)
    )
    sale_id = cur.lastrowid
    invoice_no = generate_invoice_number(sale_id)
    conn.execute("UPDATE sales SET invoice_no = ? WHERE id = ?", (invoice_no, sale_id))

    for item in cart:
        line_total = item["unit_price"] * item["quantity"]
        conn.execute(
            """INSERT INTO sale_items (sale_id, medicine_id, medicine_name, quantity, unit_price, line_total)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sale_id, item["medicine_id"], item["name"], item["quantity"], item["unit_price"], line_total)
        )
        conn.execute(
            "UPDATE medicines SET quantity = quantity - ? WHERE id = ?",
            (item["quantity"], item["medicine_id"])
        )

    conn.commit()
    conn.close()
    save_cart([])
    flash(f"Sale completed. Invoice {invoice_no}.", "success")
    return redirect(url_for("sale_detail", sale_id=sale_id))


@app.route("/sales")
def sales_list():
    """6. View sales history, searchable by invoice number or customer name."""
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    if query:
        rows = conn.execute(
            "SELECT * FROM sales WHERE invoice_no LIKE ? OR customer_name LIKE ? ORDER BY id DESC",
            (f"%{query}%", f"%{query}%")
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("sales_list.html", sales=rows, query=query)


@app.route("/sales/<int:sale_id>")
def sale_detail(sale_id):
    """7. View a single invoice with its line items."""
    conn = get_db_connection()
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
    conn.close()

    if sale is None:
        flash("Invoice not found.", "error")
        return redirect(url_for("sales_list"))

    return render_template("sale_detail.html", sale=sale, items=items)


@app.route("/sales/<int:sale_id>/print")
def print_invoice(sale_id):
    """8. Clean, nav-free printable version of an invoice."""
    conn = get_db_connection()
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
    conn.close()
    return render_template("sale_print.html", sale=sale, items=items)


@app.route("/sales/<int:sale_id>/refund", methods=["POST"])
def refund_sale(sale_id):
    """9. Refund/cancel a completed sale and restore the stock it used."""
    conn = get_db_connection()
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()

    if sale is None or sale["status"] == "refunded":
        conn.close()
        flash("Sale not found or already refunded.", "error")
        return redirect(url_for("sales_list"))

    items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
    for item in items:
        if item["medicine_id"] is not None:
            conn.execute(
                "UPDATE medicines SET quantity = quantity + ? WHERE id = ?",
                (item["quantity"], item["medicine_id"])
            )

    conn.execute("UPDATE sales SET status = 'refunded' WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()
    flash(f"Invoice {sale['invoice_no']} refunded and stock restored.", "success")
    return redirect(url_for("sale_detail", sale_id=sale_id))


# =========================================================
# MODULE 4: REPORTS & ANALYTICS
# =========================================================

def get_low_stock_medicines(conn, threshold=LOW_STOCK_THRESHOLD):
    """1. Helper: medicines at or below the low-stock threshold."""
    return conn.execute(
        "SELECT * FROM medicines WHERE quantity <= ? ORDER BY quantity", (threshold,)
    ).fetchall()


def get_expired_medicines(conn):
    """2. Helper: medicines past their expiry date."""
    today = date.today().isoformat()
    return conn.execute(
        "SELECT * FROM medicines WHERE expiry_date < ? ORDER BY expiry_date", (today,)
    ).fetchall()


def get_top_selling_medicines(conn, limit=10):
    """3. Helper: best-selling medicines by total quantity sold (completed sales only)."""
    return conn.execute("""
        SELECT sale_items.medicine_name AS name,
               SUM(sale_items.quantity) AS total_qty,
               SUM(sale_items.line_total) AS total_revenue
        FROM sale_items
        JOIN sales ON sale_items.sale_id = sales.id
        WHERE sales.status = 'completed'
        GROUP BY sale_items.medicine_name
        ORDER BY total_qty DESC
        LIMIT ?
    """, (limit,)).fetchall()


def get_revenue_summary(conn):
    """4. Helper: revenue totals for today, this week, this month, and all-time."""
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    month_start = today.replace(day=1).isoformat()

    def revenue_since(start_date):
        row = conn.execute(
            "SELECT COALESCE(SUM(total), 0) AS total FROM sales WHERE status = 'completed' AND sale_date >= ?",
            (start_date,)
        ).fetchone()
        return row["total"]

    return {
        "today": revenue_since(today.isoformat()),
        "week": revenue_since(week_start),
        "month": revenue_since(month_start),
        "all_time": revenue_since("0000-00-00"),
    }


def get_supplier_purchase_totals(conn):
    """5. Helper: current stock quantity/value supplied by each active supplier."""
    return conn.execute("""
        SELECT suppliers.name AS supplier_name,
               COUNT(medicines.id) AS batch_count,
               COALESCE(SUM(medicines.quantity), 0) AS total_quantity,
               COALESCE(SUM(medicines.quantity * medicines.unit_price), 0) AS stock_value
        FROM suppliers
        LEFT JOIN medicines ON medicines.supplier_id = suppliers.id
        GROUP BY suppliers.id
        ORDER BY stock_value DESC
    """).fetchall()


def get_sales_trend(conn, days=7):
    """6. Helper: daily revenue totals for the last N days, for a simple trend table."""
    trend = []
    for i in range(days - 1, -1, -1):
        day = (date.today() - timedelta(days=i)).isoformat()
        row = conn.execute(
            "SELECT COALESCE(SUM(total), 0) AS total FROM sales WHERE status = 'completed' AND sale_date LIKE ?",
            (f"{day}%",)
        ).fetchone()
        trend.append({"date": day, "total": row["total"]})
    return trend


@app.route("/reports")
def reports_dashboard():
    """7. Main reports page: summary cards + top-5 previews of each report."""
    conn = get_db_connection()
    low_stock = get_low_stock_medicines(conn)
    expired = get_expired_medicines(conn)
    top_selling = get_top_selling_medicines(conn, limit=5)
    revenue = get_revenue_summary(conn)
    supplier_totals = get_supplier_purchase_totals(conn)
    trend = get_sales_trend(conn)
    total_medicines = conn.execute("SELECT COUNT(*) AS c FROM medicines").fetchone()["c"]
    conn.close()

    return render_template(
        "reports.html",
        low_stock=low_stock[:5], low_stock_count=len(low_stock),
        expired=expired[:5], expired_count=len(expired),
        top_selling=top_selling,
        revenue=revenue,
        supplier_totals=supplier_totals,
        trend=trend,
        total_medicines=total_medicines,
    )


@app.route("/reports/low-stock")
def low_stock_view():
    """8. Full low-stock report page (adjustable threshold via ?threshold=)."""
    threshold = int(request.args.get("threshold", LOW_STOCK_THRESHOLD))
    conn = get_db_connection()
    medicines = get_low_stock_medicines(conn, threshold)
    conn.close()
    return render_template("report_table.html",
                            title="Low Stock Report", medicines=medicines,
                            columns=["name", "dosage", "quantity", "batch_number"],
                            report_type="low_stock", threshold=threshold)


@app.route("/reports/expired")
def expired_view():
    """9. Full expired-stock report page."""
    conn = get_db_connection()
    medicines = get_expired_medicines(conn)
    conn.close()
    return render_template("report_table.html",
                            title="Expired Stock Report", medicines=medicines,
                            columns=["name", "dosage", "quantity", "batch_number", "expiry_date"],
                            report_type="expired", threshold=None)


@app.route("/reports/export/<report_type>")
def export_report(report_type):
    """10. Export a report as a downloadable CSV file."""
    conn = get_db_connection()

    output = io.StringIO()
    writer = csv.writer(output)

    if report_type == "low_stock":
        rows = get_low_stock_medicines(conn)
        writer.writerow(["Name", "Dosage", "Quantity", "Batch Number", "Expiry Date"])
        for m in rows:
            writer.writerow([m["name"], m["dosage"], m["quantity"], m["batch_number"], m["expiry_date"]])

    elif report_type == "expired":
        rows = get_expired_medicines(conn)
        writer.writerow(["Name", "Dosage", "Quantity", "Batch Number", "Expiry Date"])
        for m in rows:
            writer.writerow([m["name"], m["dosage"], m["quantity"], m["batch_number"], m["expiry_date"]])

    elif report_type == "top_selling":
        rows = get_top_selling_medicines(conn, limit=50)
        writer.writerow(["Medicine", "Total Quantity Sold", "Total Revenue"])
        for r in rows:
            writer.writerow([r["name"], r["total_qty"], round(r["total_revenue"], 2)])

    elif report_type == "sales":
        rows = conn.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
        writer.writerow(["Invoice No", "Customer", "Date", "Subtotal", "Discount", "Tax", "Total", "Status"])
        for s in rows:
            writer.writerow([s["invoice_no"], s["customer_name"], s["sale_date"],
                              s["subtotal"], s["discount"], s["tax"], s["total"], s["status"]])
    else:
        conn.close()
        flash("Unknown report type.", "error")
        return redirect(url_for("reports_dashboard"))

    conn.close()
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={report_type}_report.csv"}
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

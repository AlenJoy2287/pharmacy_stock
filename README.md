# Pharmacy Stock Management System

A Flask + SQLite web app with **4 modules**:

1. **Medicine / Inventory** — User searches availability; Admin adds/updates/deletes stock (with price and supplier).
2. **Supplier Management** — add/edit/delete/search suppliers, activate/deactivate, view each supplier's stock history.
3. **Sales & Billing (POS)** — cart-based checkout, auto-generated invoices, sales history, refunds, printable invoices.
4. **Reports & Analytics** — low-stock report, expired-stock report, top-selling medicines, revenue summary, supplier-wise stock value, CSV export.

## Project Structure

```
pharmacy_stock/
├── app.py                    <- Flask backend: all 4 modules' routes + database logic
├── requirements.txt          <- Python packages needed
├── templates/
│   ├── base.html                <- shared layout (navbar)
│   ├── index.html               <- User: search medicine
│   ├── admin.html                <- Admin: manage inventory
│   ├── suppliers.html            <- Supplier list + add/edit
│   ├── supplier_detail.html      <- Single supplier profile + purchase history
│   ├── sales_new.html            <- POS: build cart, checkout
│   ├── sales_list.html           <- Sales history
│   ├── sale_detail.html          <- Single invoice + refund action
│   ├── sale_print.html           <- Clean printable invoice
│   ├── reports.html              <- Reports dashboard (summary cards + previews)
│   └── report_table.html         <- Full low-stock / expired report tables
└── static/
    └── style.css                <- all styling
```

The database (`pharmacy.db`) is created automatically the first time you run the app. **If you already have a `pharmacy.db` from before this update, don't delete it** — `app.py` automatically migrates it (adds the new `unit_price` and `supplier_id` columns) without losing your existing data.

## How to Run This in VS Code

### 1. Install Python (if you haven't)
Download from https://www.python.org/downloads/ and check **"Add Python to PATH"** during install.

### 2. Open the project in VS Code
`File > Open Folder...` → select the `pharmacy_stock` folder. Install the **Python extension** (Microsoft) from the Extensions sidebar.

### 3. Open a terminal
`Terminal > New Terminal` (or `` Ctrl + ` ``)

### 4. Create and activate a virtual environment
```
python -m venv venv
```
- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

Your prompt should now start with `(venv)`.

### 5. Install Flask
```
pip install -r requirements.txt
```

### 6. Run the app
```
python app.py
```
Then open **http://127.0.0.1:5000** in your browser.

## Module Walkthrough

### 1. Medicine / Inventory (`/`, `/admin`)
- `/` — User searches medicines by name, sees quantity, price, expiry, and status (Available / Low stock / Expired).
- `/admin` — Add new stock (name, dosage, quantity, price, batch, expiry, optional supplier), inline-update dosage/quantity/price, delete a batch.

### 2. Supplier Management (`/suppliers`)
- Add a supplier, search suppliers, edit contact details inline, activate/deactivate, delete (blocked if they still have linked stock).
- Click a supplier's name to see their full stock history (`/suppliers/<id>`).
- The Add Stock form on `/admin` lets you link new stock to an active supplier.

### 3. Sales & Billing / POS (`/sales/new`, `/sales`)
- `/sales/new` — browse in-stock, non-expired medicines, add items to a cart (session-based), adjust quantities, then checkout with customer name, discount, and tax %. Checkout deducts stock and generates an invoice number automatically.
- `/sales` — searchable sales history.
- `/sales/<id>` — invoice detail, with a **Refund** button (restores the stock) and a **Print Invoice** link (clean printable page).

### 4. Reports & Analytics (`/reports`)
- Dashboard with stat cards: total medicines, low-stock count, expired count, revenue (today/week/month).
- Previews of Low Stock, Expired Stock, Top-Selling Medicines, Supplier-wise Stock Value, and a 7-day Sales Trend.
- `/reports/low-stock` and `/reports/expired` — full tables (low-stock threshold is adjustable).
- **Export CSV** links next to each report download the data directly.

## How the Code Works (for your understanding)

- **`app.py`** defines routes (URLs) and talks to SQLite using raw SQL — no ORM, so it's easy to see exactly what's happening.
- **SQLite** stores everything in `pharmacy.db`. Four tables: `medicines`, `suppliers`, `sales`, `sale_items`.
- The **cart** for a sale-in-progress is stored in the Flask `session` (server-side, tied to your browser) until checkout, when it's converted into permanent `sales` + `sale_items` rows and cleared.
- **Jinja2 templates** (`.html` files) insert Python variables into HTML using `{{ }}` and `{% %}`.
- Helper functions (e.g. `get_low_stock_medicines()`, `get_revenue_summary()`) do the actual querying/calculation and are reused by both the dashboard and the CSV export routes, so the numbers always match.

## Ideas to Extend This Further

- Add admin login (username/password) so only admins can reach `/admin`, `/suppliers`, `/sales`, `/reports`.
- Add a purchase-order system (recording incoming stock deliveries from suppliers, separate from current stock).
- Add charts (e.g. using Chart.js) to the Reports dashboard for the sales trend.
- Add email/SMS alerts when stock goes low or a batch is close to expiry.
- Add barcode scanning support for faster POS checkout.

import sqlite3
from datetime import datetime, timedelta
import config


class Database:
    def __init__(self, db_name=None):
        if db_name is None:
            db_name = config.DB_NAME
        self.db_name = db_name
        self.create_tables()

    def connect(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def create_tables(self):
        conn = self.connect()
        conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT,
            target_price REAL,
            availability TEXT,
            added_on TEXT,
            group_id INTEGER)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            created_on TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            price REAL,
            availability TEXT,
            checked_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            message TEXT,
            created_at TEXT)""")
        # older databases don't have group_id yet - add it
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
        if "group_id" not in columns:
            conn.execute("ALTER TABLE products ADD COLUMN group_id INTEGER")
        conn.commit()
        conn.close()

    def add_product(self, url, name, target_price, group_id=None):
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO products (url, name, target_price, availability, added_on, group_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, name, target_price, "Unknown", self.now(), group_id))
        conn.commit()
        product_id = cur.lastrowid
        conn.close()
        return product_id

    def get_all_products(self):
        conn = self.connect()
        rows = conn.execute(
            "SELECT products.*, groups.name AS group_name FROM products "
            "LEFT JOIN groups ON products.group_id = groups.id "
            "ORDER BY products.id").fetchall()
        conn.close()
        products = []
        for row in rows:
            products.append(dict(row))
        return products

    def get_product_by_url(self, url):
        conn = self.connect()
        row = conn.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
        conn.close()
        if row is None:
            return None
        else:
            return dict(row)

    def remove_product(self, product_id):
        conn = self.connect()
        conn.execute("DELETE FROM prices WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM alerts WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()

    def add_price(self, product_id, price, availability):
        conn = self.connect()
        conn.execute(
            "INSERT INTO prices (product_id, price, availability, checked_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, price, availability, self.now()))
        conn.execute("UPDATE products SET availability = ? WHERE id = ?",
                     (availability, product_id))
        conn.commit()
        conn.close()

    def get_price_history(self, product_id):
        conn = self.connect()
        rows = conn.execute(
            "SELECT price, availability, checked_at FROM prices "
            "WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()
        conn.close()
        history = []
        for row in rows:
            history.append(dict(row))
        return history

    def get_last_price(self, product_id):
        conn = self.connect()
        row = conn.execute(
            "SELECT price FROM prices WHERE product_id = ? ORDER BY id DESC LIMIT 1",
            (product_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        else:
            return row["price"]

    def get_lowest_price(self, product_id, days):
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self.connect()
        row = conn.execute(
            "SELECT MIN(price) AS lowest FROM prices "
            "WHERE product_id = ? AND checked_at >= ?", (product_id, since)).fetchone()
        conn.close()
        return row["lowest"]

    def add_alert(self, product_id, message):
        conn = self.connect()
        conn.execute("INSERT INTO alerts (product_id, message, created_at) VALUES (?, ?, ?)",
                     (product_id, message, self.now()))
        conn.commit()
        conn.close()

    def get_alerts(self, limit=50):
        conn = self.connect()
        rows = conn.execute(
            "SELECT alerts.created_at AS time, products.name AS product, alerts.message AS message "
            "FROM alerts JOIN products ON alerts.product_id = products.id "
            "ORDER BY alerts.id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        alerts = []
        for row in rows:
            alerts.append(dict(row))
        return alerts

    # ---------- comparison groups ----------
    def add_group(self, name):
        conn = self.connect()
        cur = conn.execute("INSERT INTO groups (name, created_on) VALUES (?, ?)",
                           (name, self.now()))
        conn.commit()
        group_id = cur.lastrowid
        conn.close()
        return group_id

    def get_group_by_name(self, name):
        conn = self.connect()
        row = conn.execute("SELECT * FROM groups WHERE name = ?", (name,)).fetchone()
        conn.close()
        if row is None:
            return None
        else:
            return dict(row)

    def get_all_groups(self):
        conn = self.connect()
        rows = conn.execute("SELECT * FROM groups ORDER BY id").fetchall()
        conn.close()
        groups = []
        for row in rows:
            groups.append(dict(row))
        return groups

    def get_group_products(self, group_id):
        conn = self.connect()
        rows = conn.execute("SELECT * FROM products WHERE group_id = ? ORDER BY id",
                            (group_id,)).fetchall()
        conn.close()
        products = []
        for row in rows:
            products.append(dict(row))
        return products

    def remove_group(self, group_id):
        conn = self.connect()
        conn.execute("UPDATE products SET group_id = NULL WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
        conn.close()

    def get_group_lowest(self, group_id):
        conn = self.connect()
        row = conn.execute(
            "SELECT MIN(prices.price) AS lowest FROM prices "
            "JOIN products ON prices.product_id = products.id "
            "WHERE products.group_id = ?", (group_id,)).fetchone()
        conn.close()
        return row["lowest"]

    def get_group_lowest_row(self, group_id):
        conn = self.connect()
        row = conn.execute(
            "SELECT prices.price AS price, prices.checked_at AS checked_at, products.url AS url "
            "FROM prices JOIN products ON prices.product_id = products.id "
            "WHERE products.group_id = ? ORDER BY prices.price ASC, prices.id ASC LIMIT 1",
            (group_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        else:
            return dict(row)
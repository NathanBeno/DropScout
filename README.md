# 📉 DropScout: Track. Drop. Save

DropScout is a Python price-tracking application that monitors online store listings, records historical price trends in a local SQLite database, compares prices for the same item across multiple websites, and sends automated desktop or email alerts when prices drop. It includes both an interactive **Streamlit Web Dashboard** (`app.py`) and a **Command-Line Interface** (`main.py`).

## ✨ Features

* **Multi-Site Price Scraping:** Built-in support for Amazon, Flipkart, and Books to Scrape, plus a generic OpenGraph/meta-tag fallback for other online stores.
* **Interactive Web Dashboard:** A 6-page Streamlit interface featuring summary metrics, target-price indicators (`🎯 At/below target`), 30-day low badges (`⭐ 30-day low`), and interactive Plotly price charts.
* **Cross-Site Comparison Groups:** Group the same product across different retailers to automatically highlight the `✅ CHEAPEST NOW` in-stock listing and track the lowest price ever recorded.
* **Automated Background Checking:** Schedule recurring price checks every 1–24 hours using `APScheduler`.
* **Instant Notifications:** Receive desktop pop-up alerts (`plyer`) and SSL email notifications (`smtplib`) when a product hits your target price, drops in price, or sets a new group low.

## 📁 Project Structure

```text
DropScout/
├── app.py                  # Streamlit web dashboard interface
├── main.py                 # Command-line interface (CLI) menu
├── tracker.py              # Core controller connecting database, scraper, and alerts
├── scraper.py              # BeautifulSoup HTML parser and price extractor
├── database.py             # SQLite database manager (products, groups, prices, alerts)
├── notifier.py             # Email (SMTP_SSL) and desktop (plyer) notification sender
├── email_setup.py          # Email validation and settings persistence helper
├── config.py               # Global configuration and HTTP request headers
└── requirements.txt        # Python package dependencies

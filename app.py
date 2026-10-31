import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler

import config
import email_setup
from notifier import Notifier
from tracker import Tracker, site_name

st.set_page_config(page_title="DropScout", page_icon="📉", layout="wide")

JOB_ID = "dropscout_check"

@st.cache_resource
def get_tracker():
    return Tracker()


@st.cache_resource
def get_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.start()
    return scheduler


tracker = get_tracker()
db = tracker.db
scheduler = get_scheduler()


def scheduler_running():
    return scheduler.get_job(JOB_ID) is not None


def start_scheduler(hours):
    if scheduler_running():
        scheduler.remove_job(JOB_ID)
    scheduler.add_job(tracker.check_all, "interval", hours=hours, id=JOB_ID)
    config.CHECK_INTERVAL_HOURS = hours


def stop_scheduler():
    if scheduler_running():
        scheduler.remove_job(JOB_ID)


def flash(kind, text):
    st.session_state["flash"] = (kind, text)


def show_flash():
    if "flash" in st.session_state:
        kind, text = st.session_state.pop("flash")
        getattr(st, kind)(text)


st.sidebar.title("📉 DropScout")
st.sidebar.caption("Track. Drop. Save")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Add product", "Price history", "Compare sites", "Alert log", "Settings"],
)
st.sidebar.divider()
if scheduler_running():
    st.sidebar.success("Auto-check ON (every " + str(config.CHECK_INTERVAL_HOURS) + " h)")
else:
    st.sidebar.info("Auto-check OFF (see Settings)")
st.sidebar.write("Email alerts: **" + ("ON" if config.SEND_EMAIL == "yes" else "OFF") + "**")
st.sidebar.write("Desktop alerts: **" + ("ON" if config.SEND_DESKTOP == "yes" else "OFF") + "**")


def product_label(product):
    return str(product["id"]) + " - " + product["name"][:60]


def pick_product(label="Choose a product"):
    products = db.get_all_products()
    if len(products) == 0:
        st.info("No products tracked yet. Add one from the 'Add product' page.")
        return None
    return st.selectbox(label, products, format_func=product_label)


def price_chart(history, target=None, title=None):
    frame = pd.DataFrame(history)
    frame["checked_at"] = pd.to_datetime(frame["checked_at"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame["checked_at"], y=frame["price"], mode="lines+markers",
        name="Price", line=dict(width=3),
        customdata=frame["availability"],
        hovertemplate="%{x|%d %b %Y %H:%M}<br>Price: %{y}<br>%{customdata}<extra></extra>"))
    if target is not None:
        fig.add_hline(y=target, line_dash="dash", line_color="green",
                      annotation_text="Target " + str(target), annotation_position="top left")
    fig.update_layout(title=title, xaxis_title="Checked at", yaxis_title="Price",
                      hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10))
    return fig


def page_dashboard():
    st.header("Dashboard")
    show_flash()
    products = db.get_all_products()

    top = st.columns([1, 1, 4])
    if top[0].button("🔄 Check prices now", disabled=len(products) == 0):
        with st.spinner("Checking all products..."):
            count = tracker.check_all()
        flash("success", "Checked " + str(count) + " product(s).")
        st.rerun()

    if len(products) == 0:
        st.info("No products tracked yet. Add one from the 'Add product' page.")
        return

    rows = []
    at_target = 0
    for product in products:
        current = db.get_last_price(product["id"])
        low30 = db.get_lowest_price(product["id"], 30)
        hit = current is not None and current <= product["target_price"]
        if hit:
            at_target += 1
        status = ""
        if hit:
            status = "🎯 At/below target"
        if current is not None and low30 is not None and current <= low30:
            status = (status + "  " if status else "") + "⭐ 30-day low"
        rows.append({
            "ID": product["id"],
            "Product": product["name"][:70],
            "Site": site_name(product["url"]),
            "Group": product["group_name"] or "",
            "Current": current,
            "Target": product["target_price"],
            "30-day low": low30,
            "Stock": product["availability"],
            "Status": status,
        })

    metrics = st.columns(3)
    metrics[0].metric("Tracked products", len(products))
    metrics[1].metric("At or below target", at_target)
    metrics[2].metric("Alerts logged", len(db.get_alerts(1000)))

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader("Remove a product")
    with st.form("remove_form"):
        chosen = st.selectbox("Product", products, format_func=product_label)
        confirm = st.checkbox("Yes, delete it and its price history")
        if st.form_submit_button("Remove"):
            if confirm:
                db.remove_product(chosen["id"])
                flash("success", "Removed '" + chosen["name"][:40] + "'.")
                st.rerun()
            else:
                st.warning("Tick the confirmation box first.")


def page_add():
    st.header("Add a product")
    show_flash()
    groups = db.get_all_groups()
    NONE, NEW = "(none - single product)", "+ Create new group"
    group_choices = [NONE, NEW] + [g["name"] for g in groups]

    with st.form("add_form"):
        url = st.text_input("Product URL", placeholder="https://...")
        target = st.number_input("Target price", min_value=0.0, value=0.0, step=1.0)
        choice = st.selectbox(
            "Comparison group (optional - use the same group for the same product on different sites)",
            group_choices)
        new_group = st.text_input("New group name (only if you chose 'Create new group')",
                                  placeholder="e.g. Sony WH-1000XM5")
        submitted = st.form_submit_button("Add product")

    if not submitted:
        return

    group_id = None
    if choice == NEW:
        new_group = new_group.strip()
        if new_group == "":
            st.error("Please type a name for the new group.")
            return
        existing = db.get_group_by_name(new_group)
        group_id = existing["id"] if existing else db.add_group(new_group)
    elif choice != NONE:
        group_id = db.get_group_by_name(choice)["id"]

    with st.spinner("Fetching the page..."):
        errors = tracker.add_product(url, target, group_id)
    if len(errors) == 0:
        st.success("Product added and first price saved!")
    else:
        for error in errors:
            st.error(error)


def page_history():
    st.header("Price history")
    product = pick_product()
    if product is None:
        return
    history = db.get_price_history(product["id"])
    if len(history) == 0:
        st.info("No price history yet for this product.")
        return

    prices = [row["price"] for row in history]
    current = prices[-1]
    low30 = db.get_lowest_price(product["id"], 30)

    cols = st.columns(4)
    cols[0].metric("Current", current)
    cols[1].metric("Target", product["target_price"])
    cols[2].metric("Lowest (30 days)", low30)
    cols[3].metric("Highest (all time)", max(prices))

    if low30 is not None and current <= low30 and len(prices) > 1:
        st.success("⭐ This is the lowest price in the last 30 days.")
    elif current <= product["target_price"]:
        st.success("🎯 Price is at or below your target.")
    else:
        st.info("Current price is " + str(round(current - low30, 2)) + " above the 30-day low.")

    st.plotly_chart(price_chart(history, product["target_price"], product["name"][:80]),
                    width="stretch")
    st.caption(product["url"])
    with st.expander("Raw data"):
        st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)


def page_compare():
    st.header("Compare prices across sites")
    show_flash()
    groups = db.get_all_groups()
    if len(groups) == 0:
        st.info("No comparison groups yet. Create one on the 'Add product' page by choosing "
                "'Create new group'.")
        return

    group = st.selectbox("Group", groups, format_func=lambda g: g["name"])
    buttons = st.columns([1, 1, 4])
    if buttons[0].button("🔄 Refresh prices"):
        with st.spinner("Checking sites..."):
            tracker.check_group(group["id"])
        st.rerun()
    if buttons[1].button("🗑 Delete group"):
        db.remove_group(group["id"])
        flash("success", "Group deleted (its sites are still tracked as single products).")
        st.rerun()

    result = tracker.compare_group(group["id"])
    if len(result["listings"]) == 0:
        st.info("This group has no sites yet.")
        return

    cheapest_id = result["cheapest"]["id"] if result["cheapest"] else None
    rows = []
    for item in result["listings"]:
        rows.append({
            "Site": item["site"],
            "Price": item["price"],
            "Stock": item["availability"],
            "Target": item["target"],
            "": "✅ CHEAPEST NOW" if item["id"] == cheapest_id else "",
            "URL": item["url"],
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if result["cheapest"] is None:
        st.warning("No in-stock listing with a price right now.")
    else:
        st.success("Cheapest in stock: " + str(result["cheapest"]["price"])
                   + " on " + result["cheapest"]["site"])
    best = result["lowest_ever"]
    if best is not None:
        st.write("Lowest price ever recorded across all sites: **" + str(best["price"])
                 + "** on " + site_name(best["url"]) + " (" + best["checked_at"] + ")")

    fig = go.Figure()
    for item in result["listings"]:
        history = db.get_price_history(item["id"])
        if len(history) > 0:
            frame = pd.DataFrame(history)
            fig.add_trace(go.Scatter(x=pd.to_datetime(frame["checked_at"]), y=frame["price"],
                                     mode="lines+markers", name=item["site"]))
    fig.update_layout(title="Price over time by site", xaxis_title="Checked at",
                      yaxis_title="Price", hovermode="x unified",
                      margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("Prices are compared as plain numbers - keep all sites in the same currency.")


def page_alerts():
    st.header("Alert log")
    alerts = db.get_alerts(200)
    if len(alerts) == 0:
        st.info("No alerts yet.")
        return
    frame = pd.DataFrame(alerts).rename(
        columns={"time": "Time", "product": "Product", "message": "Message"})
    st.dataframe(frame, width="stretch", hide_index=True)


def page_settings():
    st.header("Settings")
    show_flash()

    st.subheader("Automatic price checking")
    hours = st.slider("Check every N hours", 1, 24, int(config.CHECK_INTERVAL_HOURS))
    cols = st.columns(2)
    if cols[0].button("▶ Start / apply"):
        start_scheduler(hours)
        flash("success", "Auto-check running every " + str(hours) + " hour(s).")
        st.rerun()
    if cols[1].button("⏹ Stop", disabled=not scheduler_running()):
        stop_scheduler()
        flash("info", "Auto-check stopped.")
        st.rerun()
    st.caption("Runs in the background while this app is running. Closing the app stops it.")

    st.divider()
    st.subheader("Notifications")
    desktop = st.toggle("Desktop notifications", value=config.SEND_DESKTOP == "yes")
    config.SEND_DESKTOP = "yes" if desktop else "no"

    st.markdown("**Email alerts**")
    email_setup.load_settings()
    st.caption("Gmail users: use a 16-character App Password, not your normal password.")
    with st.form("email_form"):
        sender = st.text_input("Sender email", value=config.EMAIL_SENDER)
        same = st.checkbox("Send alerts to the same address",
                           value=config.EMAIL_RECEIVER in ("", config.EMAIL_SENDER))
        receiver = st.text_input("Receiver email (if different)", value=config.EMAIL_RECEIVER)
        password = st.text_input("App password", type="password")
        enable = st.form_submit_button("Test login and enable email")

    if enable:
        receiver = sender if same else receiver
        if not (email_setup.is_valid_email(sender) and email_setup.is_valid_email(receiver)):
            st.error("Please enter valid email addresses.")
        elif password.strip() == "":
            st.error("Please enter the app password.")
        else:
            domain = sender.split("@")[1].lower()
            server, port = email_setup.KNOWN_SERVERS.get(domain, (config.SMTP_SERVER, config.SMTP_PORT))
            config.EMAIL_SENDER, config.EMAIL_RECEIVER = sender, receiver
            config.SMTP_SERVER, config.SMTP_PORT = server, port
            config.EMAIL_PASSWORD = password.replace(" ", "")
            with st.spinner("Testing login..."):
                errors = Notifier().test_login()
            if len(errors) == 0:
                config.SEND_EMAIL = "yes"
                email_setup.save_settings()
                st.success("Email alerts ON: " + sender + " -> " + receiver)
            else:
                config.SEND_EMAIL = "no"
                for error in errors:
                    st.error(error)
    if config.SEND_EMAIL == "yes" and st.button("Turn email alerts off"):
        email_setup.disable_email()
        st.rerun()


PAGES = {
    "Dashboard": page_dashboard,
    "Add product": page_add,
    "Price history": page_history,
    "Compare sites": page_compare,
    "Alert log": page_alerts,
    "Settings": page_settings,
}
PAGES[page]()

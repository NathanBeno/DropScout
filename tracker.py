from datetime import datetime
from urllib.parse import urlparse
from apscheduler.schedulers.blocking import BlockingScheduler
from database import Database
from scraper import Scraper
from notifier import Notifier
import config
import time
import random

def site_name(url):
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


class Tracker:
    def __init__(self):
        self.db = Database()
        self.scraper = Scraper()
        self.notifier = Notifier()

    def add_product(self, url, target_price, group_id=None):
        errors = []
        url = url.strip()

        if not url.startswith("http"):
            errors.append("Please enter a full URL starting with http:// or https://")
        if target_price <= 0:
            errors.append("Target price must be greater than 0.")

        if len(errors) == 0:
            existing = self.db.get_product_by_url(url)
            if existing is not None:
                errors.append("This product is already being tracked.")

        if len(errors) == 0:
            details = self.scraper.get_product_details(url)
            if details["price"] is None:
                errors = errors + details["errors"]
            else:
                product_id = self.db.add_product(url, details["name"], target_price, group_id)
                self.db.add_price(product_id, details["price"], details["availability"])

        return errors

    def check_product(self, product):
        details = self.scraper.get_product_details(product["url"])
        if details["price"] is None:
            print("Skipped '" + product["name"][:40] + "': " + " ".join(details["errors"]))
            return

        new_price = details["price"]
        last_price = self.db.get_last_price(product["id"])
        target = product["target_price"]

        # lowest price on any site in this group BEFORE saving the new price
        group_lowest = None
        if product.get("group_id") is not None:
            group_lowest = self.db.get_group_lowest(product["group_id"])

        self.db.add_price(product["id"], new_price, details["availability"])

        reasons = []
        if new_price <= target:
            if last_price is None or last_price > target:
                reasons.append("Price reached your target of " + str(target))
        if last_price is not None and new_price < last_price:
            reasons.append("Price dropped from " + str(last_price) + " to " + str(new_price))
        if group_lowest is not None and new_price < group_lowest:
            reasons.append("New lowest price across all sites (" + site_name(product["url"]) + ")")

        if len(reasons) > 0:
            message = product["name"] + "\n" + "\n".join(reasons)
            message = message + "\nNow: " + str(new_price) + "\nLink: " + product["url"]
            self.db.add_alert(product["id"], " | ".join(reasons) + " (now " + str(new_price) + ")")
            self.notifier.notify("DropScout: price drop!", message)

    def check_all(self):
        print("Checking prices at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        products = self.db.get_all_products()
        count = 0
        for product in products:
            if count > 0:
                time.sleep(random.uniform(1.5, 3.5))  # Avoid rate-limit bursts
            self.check_product(product)
            count = count + 1
        return count

    def check_group(self, group_id):
        products = self.db.get_all_products()
        count = 0
        for product in products:
            if product["group_id"] == group_id:
                self.check_product(product)
                count = count + 1
        return count

    def compare_group(self, group_id):
        listings = []
        for product in self.db.get_group_products(group_id):
            listings.append({
                "id": product["id"],
                "site": site_name(product["url"]),
                "name": product["name"],
                "price": self.db.get_last_price(product["id"]),
                "availability": product["availability"],
                "target": product["target_price"],
                "url": product["url"],
            })

        priced = [item for item in listings if item["price"] is not None]
        unpriced = [item for item in listings if item["price"] is None]
        priced.sort(key=lambda item: item["price"])

        available = [item for item in priced if item["availability"] != "Out of Stock"]
        cheapest = None
        if len(available) > 0:
            cheapest = available[0]

        return {
            "listings": priced + unpriced,
            "cheapest": cheapest,
            "lowest_ever": self.db.get_group_lowest_row(group_id),
        }

    def run_scheduler(self):
        self.check_all()
        scheduler = BlockingScheduler()
        scheduler.add_job(self.check_all, "interval", hours=config.CHECK_INTERVAL_HOURS)
        print("Scheduler running - checking every " + str(config.CHECK_INTERVAL_HOURS)
              + " hour(s). Press Ctrl+C to stop.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("Scheduler stopped.")
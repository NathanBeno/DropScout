import json
import random
import re
import time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import config

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


SITE_SELECTORS = {
    "amazon": {
        "name": ["#productTitle", "#title"],
        "price": [
            "span.a-price.priceToPay span.a-offscreen",
            "span.apexPriceToPay span.a-offscreen",
            "span.a-price span.a-offscreen",
            "span.a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
        ],
        "availability": ["#availability", "#outOfStock"],
    },
    "flipkart": {
        "name": ["span.VU-ZEz", "span.B_NuCI", "h1._6EBuvT"],
        "price": ["div.Nx9bqj.CxhGGd", "div.Nx9bqj", "div._30jeq3._16Jk6d"],
        "availability": ["div._16FRp0", "div.Z8JjpR"],
    },
    "books.toscrape": {
        "name": ["div.product_main h1"],
        "price": ["p.price_color"],
        "availability": ["p.availability"],
    },
}

BLOCK_INDICATORS = [
    "enter the characters you see below",
    "sorry, we just need to make sure you're not a robot",
    "api-services-support@amazon.com",
    "cf-browser-verification",
    "just a moment...",
    "attention required! | cloudflare",
    "access denied",
    "verify you are human",
]


class Scraper:
    def clean_price(self, text):
        """Turn text like 'Rs. 1,29,999.00' or '£51.77' into a float (or None)."""
        if text is None:
            return None
        text = str(text).strip()
        match = re.search(r"[0-9][0-9,]*\.?[0-9]*", text)
        if match is None:
            return None
        number_text = match.group().replace(",", "").rstrip(".")
        try:
            return float(number_text)
        except ValueError:
            return None

    def clean_availability(self, text):
        """Turn messy availability text into 'In Stock', 'Out of Stock' or 'Unknown'."""
        if not text:
            return "Unknown"
        text = str(text).lower()
        if any(w in text for w in ["out of stock", "sold out", "unavailable", "outofstock", "currently unavailable"]):
            return "Out of Stock"
        elif any(w in text for w in ["in stock", "available", "instock", "only", "left in stock"]):
            return "In Stock"
        return "Unknown"

    def is_blocked(self, html, status_code=200):
        """Detect CAPTCHAs, Cloudflare walls, or empty shells."""
        if status_code in (403, 429, 503):
            return True
        if not html or len(html) < 800:
            return True
        lower_html = html.lower()
        for phrase in BLOCK_INDICATORS:
            if phrase in lower_html and "producttitle" not in lower_html:
                return True
        return False

    def fetch_with_cffi(self, url):
        """Tier 1: Fast request impersonating Chrome's TLS/JA3 fingerprint."""
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        headers = dict(config.REQUEST_HEADERS)
        headers["Referer"] = "https://www.google.com/"
        proxies = {"http": config.PROXY_URL, "https": config.PROXY_URL} if getattr(config, "PROXY_URL", None) else None

        if HAS_CFFI:
            session = cffi_requests.Session(impersonate="chrome124")
            # Warm up session cookies on homepage for Amazon/Flipkart
            if any(k in parsed.netloc.lower() for k in ["amazon", "flipkart"]):
                try:
                    session.get(base_url, headers=headers, timeout=10, proxies=proxies)
                    time.sleep(random.uniform(0.5, 1.2))
                    headers["Referer"] = base_url + "/"
                except Exception:
                    pass
            resp = session.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT, proxies=proxies)
            return resp.text, resp.status_code
        else:
            session = requests.Session()
            resp = session.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT, proxies=proxies)
            return resp.text, resp.status_code

    def fetch_with_playwright(self, url):
        """Tier 2: Full headless browser for JS-heavy or Cloudflare-protected pages."""
        if not HAS_PLAYWRIGHT:
            return None, "Playwright is not installed."
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context_args = {
                    "user_agent": config.REQUEST_HEADERS["User-Agent"],
                    "viewport": {"width": 1366, "height": 768},
                    "locale": "en-US",
                }
                if getattr(config, "PROXY_URL", None):
                    context_args["proxy"] = {"server": config.PROXY_URL}

                context = browser.new_context(**context_args)
                # Hide webdriver property
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=config.REQUEST_TIMEOUT * 1000)
                page.wait_for_timeout(2500)  # Let dynamic prices finish rendering
                html = page.content()
                browser.close()
                return html, None
        except Exception as e:
            return None, str(e)

    def find_site_selectors(self, url):
        for site_key, sel in SITE_SELECTORS.items():
            if site_key in url.lower():
                return sel
        return None

    def get_first_text(self, soup, selectors):
        if isinstance(selectors, str):
            selectors = [selectors] if selectors else []
        for selector in selectors:
            if not selector:
                continue
            tag = soup.select_one(selector)
            if tag is not None:
                text = tag.get_text(" ", strip=True)
                if text:
                    return text
        return ""

    def extract_json_ld(self, soup):
        """Parse Schema.org Product JSON-LD blocks embedded in the page."""
        result = {"name": "", "price": "", "availability": ""}
        scripts = soup.find_all("script", type="application/ld+json")

        def parse_node(node):
            if isinstance(node, list):
                for item in node:
                    parse_node(item)
            elif isinstance(node, dict):
                node_type = str(node.get("@type", "")).lower()
                if "product" in node_type:
                    if not result["name"] and node.get("name"):
                        result["name"] = str(node["name"]).strip()
                    offers = node.get("offers")
                    if offers:
                        parse_offers(offers)
                if "@graph" in node:
                    parse_node(node["@graph"])

        def parse_offers(offers):
            if isinstance(offers, list):
                for offer in offers:
                    parse_offers(offer)
            elif isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                if price and not result["price"]:
                    result["price"] = str(price)
                avail = offers.get("availability")
                if avail and not result["availability"]:
                    result["availability"] = str(avail)

        for script in scripts:
            try:
                raw = script.string or script.get_text()
                if raw:
                    data = json.loads(raw.strip())
                    parse_node(data)
            except Exception:
                continue

        return result

    def get_generic_details(self, soup):
        """Fallback for unknown sites: look at JSON-LD first, then OpenGraph/meta tags."""
        ld_data = self.extract_json_ld(soup)
        name = ld_data["name"]
        price = ld_data["price"]
        availability = ld_data["availability"]

        if not name:
            tag = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "title"})
            if tag and tag.get("content"):
                name = tag["content"].strip()
            elif soup.title and soup.title.string:
                name = soup.title.string.strip()

        if not price:
            possible_tags = [
                {"property": "product:price:amount"},
                {"property": "og:price:amount"},
                {"itemprop": "price"},
                {"name": "twitter:data1"},
            ]
            for attributes in possible_tags:
                tag = soup.find(attrs=attributes)
                if tag is not None:
                    price = tag.get("content") or tag.get_text(strip=True)
                    if price:
                        break

        if not availability:
            avail_tag = soup.find(attrs={"itemprop": "availability"}) or soup.find("meta", attrs={"property": "product:availability"})
            if avail_tag:
                availability = avail_tag.get("content") or avail_tag.get("href") or avail_tag.get_text(strip=True)

        return {"name": name, "price": price, "availability": availability}

    def parse_html(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        selectors = self.find_site_selectors(url)

        name = ""
        price_text = ""
        availability_text = ""

        if selectors is not None:
            name = self.get_first_text(soup, selectors["name"])
            price_text = self.get_first_text(soup, selectors["price"])
            availability_text = self.get_first_text(soup, selectors["availability"])

        if not name or not price_text or not availability_text:
            generic = self.get_generic_details(soup)
            if not name:
                name = generic["name"]
            if not price_text:
                price_text = generic["price"]
            if not availability_text:
                availability_text = generic["availability"]

        price = self.clean_price(price_text)
        availability = self.clean_availability(availability_text)
        if price is not None and availability == "Unknown":
            availability = "In Stock"

        return name, price, availability

    def get_product_details(self, url):
        """Visit the page using TLS impersonation first, falling back to Playwright if blocked."""
        errors = []
        html = None
        blocked = False

        try:
            html, status_code = self.fetch_with_cffi(url)
            blocked = self.is_blocked(html, status_code)
        except Exception as e:
            blocked = True
            errors.append(f"Fast fetch failed: {e}")

        name, price, availability = ("", None, "Unknown")
        if html and not blocked:
            name, price, availability = self.parse_html(html, url)

        if price is None and HAS_PLAYWRIGHT:
            pw_html, pw_err = self.fetch_with_playwright(url)
            if pw_html and not self.is_blocked(pw_html, 200):
                errors.clear()  # Clear earlier fast-fetch error if fallback succeeds
                name, price, availability = self.parse_html(pw_html, url)
            elif pw_err:
                errors.append(f"Browser fallback failed: {pw_err}")

        if price is None:
            errors.append(
                "Could not find a price on the page. The site may require solving a CAPTCHA "
                "or uses a custom layout."
            )
        if not name:
            name = "Unknown product"

        return {"name": name, "price": price, "availability": availability, "errors": errors}
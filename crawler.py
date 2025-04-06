import time
import gzip
import io
import pandas as pd
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


PRODUCT_PATTERNS = ["/product/", "/products/", "/p/", "/item/", "/shop/", "/details/"]
PRODUCT_SITEMAP_PATTERNS = [
    "sitemap-product", "sitemap_products", "products", "inventory",
    "sitemap-v2", "sitemap/pdp", "sitemaps/prod"
]

ALLOWED_SITEMAP_PATTERNS = [
    "category-sitemap", "sitemap-product", "sitemap_products", "products",
    "inventory", "sitemap-v2", "sitemap/pdp", "sitemaps/prod", "prod-"
]


IGNORE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg",
    ".css", ".js", ".webp", ".woff", ".woff2", ".ttf"
)


EXCLUDED_PATTERNS = ["collection", "category", "blog", "cdn", "image", "product-listing"]

# --- Global dictionary to force Selenium for a domain once a 403 is encountered ---
FORCE_SELENIUM = {}

# --- ChromeDriver Setup for Selenium Fallback ---
CHROMEDRIVER_PATH = "/path/to/your/chromedriver"  # update with your actual path
chrome_options = Options()
chrome_options.add_argument('--headless')  # Run in headless mode
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--window-size=1920x1080")
service_obj = Service(CHROMEDRIVER_PATH)


def get_sitemap_content(url):
    """
    Fetch the content of a sitemap URL.
    If the URL ends with .xml.gz, decompress it.
    Otherwise, return the plain text.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    if url.endswith(".xml.gz"):
        buf = io.BytesIO(response.content)
        with gzip.GzipFile(fileobj=buf) as f:
            content = f.read().decode("utf-8")
    else:
        content = response.text
    return content


def get_sitemap_content_with_selenium(url):
    """Fallback: Fetch sitemap content using Selenium."""
    print(f"📄 Selenium fetching content: {url}")
    driver = webdriver.Chrome(service=service_obj, options=chrome_options)
    driver.get(url)
    time.sleep(3)
    content = driver.page_source
    driver.quit()
    return content


def get_sitemap_links_with_selenium(url):
    """Fallback: Fetch sitemap links using Selenium."""
    print(f"📄 Selenium fetching links: {url}")
    driver = webdriver.Chrome(service=service_obj, options=chrome_options)
    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "xml")
    driver.quit()
    return [loc.text.strip() for loc in soup.find_all("loc")]


def get_sitemap_links(url):
    """
    Fetch all links from a given sitemap URL.
    Uses requests (and get_sitemap_content) unless the domain is flagged for Selenium.
    """
    domain = urlparse(url).netloc
    if FORCE_SELENIUM.get(domain, False):
        return get_sitemap_links_with_selenium(url)
    print(f"📄 Fetching: {url}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 403:
            print(f"❌ 403 Forbidden for {url}. Flagging domain {domain} for Selenium fallback.")
            FORCE_SELENIUM[domain] = True
            return get_sitemap_links_with_selenium(url)
        elif response.status_code != 200:
            print(f"❌ Failed to fetch {url} (status code {response.status_code}).")
            return []
    except requests.RequestException as e:
        print(f"❌ Error fetching {url}: {e}. Falling back to Selenium.")
        FORCE_SELENIUM[domain] = True
        return get_sitemap_links_with_selenium(url)
    try:
        content = get_sitemap_content(url)
    except Exception as e:
        print(f"❌ Error processing sitemap content from {url}: {e}")
        return []
    soup = BeautifulSoup(content, "xml")
    return [loc.text.strip() for loc in soup.find_all("loc")]


def is_terminal_sitemap(url):
    try:
        content = get_sitemap_content(url)
    except Exception as e:
        print(f"❌ Error in is_terminal_sitemap for {url}: {e}. Falling back to Selenium.")
        try:
            content = get_sitemap_content_with_selenium(url)
        except Exception as e2:
            print(f"❌ Selenium fallback also failed for {url}: {e2}")
            return False
    soup = BeautifulSoup(content, "xml")
    return bool(soup.find("urlset"))


def should_search_deeper(link):
    """
    Check if the link should be recursively searched.
    """
    parsed = urlparse(link)
    path = parsed.path.lower()
    return ".xml" in path and any(pattern in link.lower() for pattern in PRODUCT_SITEMAP_PATTERNS)


def is_valid_product_link(link, base_domain):
    parsed_url = urlparse(link)
    if base_domain not in parsed_url.netloc:
        return False
    if any(parsed_url.path.lower().endswith(ext) for ext in IGNORE_EXTENSIONS):
        return False
    # Exclude links from known asset/CDN domains
    IGNORED_DOMAINS = ["cdn.shopify.com", "images.ctfassets.net", "assets.adobedtm.com"]
    if any(ignored in parsed_url.netloc for ignored in IGNORED_DOMAINS):
        return False
    # Must match one of the product patterns
    if not any(pattern in parsed_url.path for pattern in PRODUCT_PATTERNS):
        return False
    # Exclude unwanted patterns (e.g., collections, categories, blogs)
    if any(excl in parsed_url.path.lower() for excl in ["collection", "category", "blog"]):
        return False
    return True


def fetch_product_links_from_sitemaps(sitemap_url, visited_sitemaps=None):
    """
    Recursively fetch product links from product sitemaps.
    If the sitemap is terminal (<urlset>), return its links directly (after filtering).
    Otherwise, for each link:
      - If it contains ".xml" and should be searched deeper, process it recursively.
      - Else, if it is a valid product link, add it.
    """
    if visited_sitemaps is None:
        visited_sitemaps = set()
    normalized_sitemap = sitemap_url.rstrip("/")
    if normalized_sitemap in visited_sitemaps:
        print(f"⚠️ Skipping already processed sitemap: {normalized_sitemap}")
        return []
    visited_sitemaps.add(normalized_sitemap)
    base_domain = urlparse(sitemap_url).netloc
    all_links = get_sitemap_links(sitemap_url)
    product_links = set()
    sub_sitemaps = set()
    if is_terminal_sitemap(sitemap_url):
        print(f"📄 Terminal sitemap detected: {normalized_sitemap}")
        for link in all_links:
            if link.startswith("/"):
                link = urljoin(sitemap_url, link)
            normalized_link = link.rstrip("/")
            if is_valid_product_link(normalized_link, base_domain):
                product_links.add(normalized_link)
        return list(product_links)
    else:
        for link in all_links:
            if link.startswith("/"):
                link = urljoin(sitemap_url, link)
            normalized_link = link.rstrip("/")
            if normalized_link == normalized_sitemap:
                continue
            parsed = urlparse(normalized_link)
            path = parsed.path.lower()
            if ".xml" in path and should_search_deeper(normalized_link):
                print(f"🔍 Recursing into sitemap: {normalized_link}")
                sub_sitemaps.add(normalized_link)
            else:
                if is_valid_product_link(normalized_link, base_domain):
                    product_links.add(normalized_link)
        for sub_sitemap in sub_sitemaps:
            product_links.update(fetch_product_links_from_sitemaps(sub_sitemap, visited_sitemaps))
        return list(product_links)


def get_sitemaps_from_robots(website_url):
    robots_url = website_url.rstrip("/") + "/robots.txt"
    print(f"📄 Fetching robots.txt: {robots_url}")
    try:
        response = requests.get(robots_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch robots.txt from {robots_url} (status code {response.status_code})")
            return []
    except requests.RequestException as e:
        print(f"❌ Error fetching robots.txt from {robots_url}: {e}")
        return []
    sitemap_urls = []
    for line in response.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url.endswith(".xml") or sitemap_url.endswith(".xml.gz"):
                sitemap_urls.append(sitemap_url)
    return list(set(sitemap_urls))


def save_to_excel(links, filename="filtered_products.xlsx"):
    """Save product links to an Excel file."""
    df = pd.DataFrame(links, columns=["Product Link"])
    df.to_excel(filename, index=False)
    print(f"✅ Saved {len(links)} product links to {filename}")


def main():
    websites = []

    for website in websites:
        print(f"\n========== Processing {website} ==========")
        sitemaps = get_sitemaps_from_robots(website)
        print(f"🔍 Found {len(sitemaps)} sitemap(s) from robots.txt")
        all_product_links = set()
        domain = urlparse(website).netloc
        currWebsite = domain[4:] if domain.startswith("www.") else domain
        for sitemap_url in sitemaps:
            print(f"\n🔍 Crawling {sitemap_url} for {currWebsite}...")
            start_time = time.time()
            product_links = fetch_product_links_from_sitemaps(sitemap_url)
            elapsed_time = time.time() - start_time
            all_product_links.update(product_links)
            print(f"✅ Found {len(product_links)} valid product links from {sitemap_url} in {elapsed_time:.2f} seconds")
        filename = f"{currWebsite}_products.xlsx"
        save_to_excel(list(all_product_links), filename=filename)


if __name__ == "__main__":
    main()

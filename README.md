
#  Product Link Crawler

A robust and recursive Python crawler that **fetches product links** from e-commerce websites using their **sitemaps** (defined in `robots.txt`). Built to gracefully handle real-world challenges like `403 Forbidden`, compressed `.xml.gz` sitemaps, and dynamic rendering using **Selenium fallback**.

---

## 🚀 Features

- ✅ Parses `robots.txt` to discover all available sitemaps.
- 🔍 Recursively explores both sitemap indexes and terminal sitemaps.
- 🛍️ Filters and returns only **product links** (based on common e-commerce URL patterns).
- 💥 Handles `.xml` and `.xml.gz` sitemap formats.
- 🔐 Smart fallback to **Selenium** for domains that block requests with `403 Forbidden`.
- 🧠 Avoids infinite recursion with visited sitemap tracking.
- 📦 Exports links to clean, ready-to-use Excel files.

---

## 🧠 Approach

### 1. **Start from `robots.txt`**
For a given domain, we fetch `/robots.txt` and extract all sitemap URLs.

```
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap_products_1.xml
```

---

### 2. **Recursive Sitemap Parsing**
Each sitemap is either:
- **Sitemap Index** (`<sitemapindex>`): contains links to other sitemaps → recurse into them
- **Terminal Sitemap** (`<urlset>`): contains actual product/page links → collect them

We recurse only into sitemaps that match product-specific patterns like:
```
sitemap_products, inventory, sitemap-product, etc.
```

---

### 3. **Product Link Detection**
From terminal sitemaps, we collect URLs that look like product pages:
```
/product/, /products/, /item/, /shop/, etc.
```
We skip static assets like `.jpg`, `.css`, etc.

---

### 4. **403 Handling with Selenium**
If a site blocks us (403 error), we flag the domain and **switch to Selenium** for future requests on that domain. Selenium loads the page like a real browser and fetches the raw XML.

---

### 5. **Data Export**
Finally, all valid product links are exported to an Excel file named after the domain:

```
example_products.xlsx
```

## 🛠️ Usage

```bash
python crawler.py
```

Modify the `websites = [...]` list in `main()` to include your target domains.

---

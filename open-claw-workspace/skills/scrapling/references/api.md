# Scrapling API Reference

## Fetchers

### Fetcher — plain HTTP
```python
page = Fetcher.get(url)
page = Fetcher.get(url, headers={"User-Agent": "..."}, timeout=30)
page = Fetcher.post(url, data={"key": "val"})
page = Fetcher.post(url, json={"key": "val"})
```
Fast, no browser. Spoofs TLS fingerprint and browser headers. Use for static HTML.

### StealthyFetcher — Camoufox (patched Firefox)
```python
page = StealthyFetcher.fetch(url, headless=True)
page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
page = StealthyFetcher.fetch(url, headless=True, user_data_dir="/path/to/profile")
```
Launches a real patched Firefox browser. Bypasses Cloudflare Turnstile and most anti-bot systems. Slower — use only when needed.

### DynamicFetcher — Playwright Chromium
```python
page = DynamicFetcher.fetch(url)
page = DynamicFetcher.fetch(url, headless=True, network_idle=True)
```
Chromium-based browser automation. Good for JS rendering when stealth is not critical.

### Sessions — persistent cookies / state
```python
session = FetcherSession()       # HTTP + cookie jar
session = StealthySession()      # Camoufox + persistent state
session = DynamicSession()       # Playwright + persistent state

page = session.fetch(url)        # FetcherSession uses .get() / .post()
page2 = session.fetch(url2)      # cookies carry over automatically
```

---

## Selectors

### CSS
```python
# First match (or None)
el = page.css("h1")
el = page.css(".price")

# All matches
els = page.css(".item")

# Text extraction (Scrapy-style pseudo-elements)
text  = page.css("h1::text").get()          # first text node
texts = page.css(".item::text").getall()    # all text nodes

# Attribute extraction
href = page.css("a::attr(href)").get()
src  = page.css("img::attr(src)").get()

# Chained
for row in page.css("table tr"):
    cells = row.css("td::text").getall()
    print(cells)
```

### XPath
```python
el    = page.xpath("//h1")
text  = page.xpath("//h1/text()").get()
els   = page.xpath("//div[@class='price']")
hrefs = page.xpath("//a/@href").getall()
```

### Text search
```python
el  = page.find("Some text")
els = page.find_all("pattern", regex=True)
```

---

## Element Properties
```python
el.text              # clean inner text (strips tags)
el.html              # raw inner HTML
el.attrib            # dict of all attributes
el.attrib["href"]    # specific attribute
el.tag               # tag name (e.g. "div", "a")
el.parent            # parent element
el.children          # list of direct children
el.siblings          # sibling elements
```

---

## Adaptive Scraping (survives site redesigns)
```python
# Save element fingerprint on first run
items = page.css(".product", auto_save=True)

# On future runs, relocate even if selector/class changed
items = page.css(".product", adaptive=True)
```

---

## Output Patterns

```python
# List of dicts (most useful for structured data)
results = [
    {
        "title": el.css("h2::text").get(),
        "price": el.css(".price::text").get(),
        "url":   el.css("a::attr(href)").get(),
    }
    for el in page.css(".result")
]
for r in results:
    print(r)

# Quick scan of all links
for a in page.css("a"):
    href = a.attrib.get("href", "")
    if href:
        print(a.text.strip(), "->", href)

# Limit large sets
for el in page.css(".item")[:10]:
    print(el.text)
```

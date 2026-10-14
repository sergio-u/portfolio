# Amazon CSS Selectors Reference

Tested and verified 2026-04-17 against Amazon.com.

## Search Results Page (`/s?k=...`)

| Element | Selector | Returns |
|---------|----------|---------|
| Result container | `[data-component-type="s-search-result"]` | Each product card |
| ASIN | `.attrib["data-asin"]` | String, e.g. `B0C3TSQ4VQ` |
| Title | `h2 span::text` | Product title |
| Price | `.a-price .a-offscreen::text` | e.g. `$24.99` |
| Rating | `span.a-icon-alt::text` | e.g. `4.7 out of 5 stars` |
| Review count | `span.a-size-base.s-underline-text::text` | May be null in Fetcher |
| Thumbnail | `img.s-image::attr(src)` | `_AC_UL320_` size |
| Link | `h2 a::attr(href)` | Relative URL (may be null in Fetcher) |

## Product Page (`/dp/<ASIN>`)

### Core Info

| Element | Selector | Notes |
|---------|----------|-------|
| Title | `#productTitle::text` | Needs `.strip()` |
| Price | `.a-price .a-offscreen::text` | First match is current price |
| Rating | `#acrPopover span.a-icon-alt::text` | e.g. `4.7 out of 5 stars` |
| Review count | `#acrCustomerReviewText::text` | e.g. `(2,314)` |
| Brand | `#bylineInfo::text` | e.g. `Visit the tounee Store` |
| Availability | `#availability span::text` | e.g. `In Stock` |
| Feature bullets | `#feature-bullets li span.a-list-item` | Use `.text.strip()` per item |
| Description | `#productDescription p::text` | Often empty |
| Main image | `#landingImage::attr(src)` | Medium-res |

### Images (Hi-Res)

Hi-res images are NOT in the DOM as `<img>` elements. They're in inline `<script>` tags.

**Extraction method:**
```python
import re
hi_res = []
for s in page.css("script::text").getall():
    hi_res.extend(re.findall(r'"hiRes"\s*:\s*"(https://[^"]+)"', s))
```

Returns `_AC_SL1500_` resolution URLs. Typically 5-7 images per product.

**Thumbnail fallback (lower quality):**
```python
thumbs = [img.attrib.get("src", "") for img in page.css("#altImages img")]
# Convert to hi-res by replacing size suffix:
import re
hires = [re.sub(r'\._AC_US\d+_', '._AC_SL1500_', t) for t in thumbs]
```

### Embedded Reviews (on product page)

| Element | Selector | Notes |
|---------|----------|-------|
| Review container | `[data-hook="review"]` | ~10 reviews embedded |
| Title | `[data-hook="review-title"] span::text` | Use `.getall()[-1]` (last span) |
| Rating | `[data-hook="review-star-rating"] span.a-icon-alt::text` | May be null for non-US reviews |
| Body | `[data-hook="review-body"] span::text` | Truncate with `[:300]` |
| Verified badge | `[data-hook="avp-badge"]` | Check with `bool()` |
| Helpful votes | `[data-hook="helpful-vote-statement"]::text` | e.g. `2 people found this helpful` |

## Reviews Page (`/product-reviews/<ASIN>`) — Requires Auth

Only accessible via agent-browser CDP with authenticated session.

**Use JS eval, not CSS selectors** — agent-browser returns an accessibility tree, not HTML.

### Key eval patterns:

```javascript
// Extract all reviews
Array.from(document.querySelectorAll('[data-hook="review"]')).map(r => ({
    title: (() => { const spans = r.querySelectorAll('[data-hook="review-title"] span'); return spans[spans.length-1]?.innerText; })(),
    rating: r.querySelector('[data-hook="review-star-rating"] span')?.innerText,
    date: r.querySelector('[data-hook="review-date"]')?.innerText,
    body: r.querySelector('[data-hook="review-body"] span')?.innerText?.slice(0, 500),
    verified: !!r.querySelector('[data-hook="avp-badge"]'),
    helpful: r.querySelector('[data-hook="helpful-vote-statement"]')?.innerText,
    author: r.querySelector('.a-profile-name')?.innerText,
}))
```

### URL Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `sortBy` | `recent`, `helpful` | Default is helpful |
| `filterByStar` | `all_stars`, `five_star`, `four_star`, `three_star`, `two_star`, `one_star`, `positive`, `critical` | `critical` = 1-3 stars |
| `pageNumber` | Integer | 10 reviews per page |
| `reviewerType` | `all_reviews`, `avp_only_reviews` | `avp_only` = verified purchases |
| `filterByKeyword` | URL-encoded string | Search within reviews |

## camelcamelcamel (`/product/<ASIN>`)

Only accessible via agent-browser CDP (Cloudflare blocks HTTP).

**Price table selector:**
```javascript
document.querySelector('table')?.innerText
```

Returns tab-separated data:
```
Price Type  Lowest Ever  Highest Ever  Current +  Average
Amazon      -            -             -          -
3rd Party New  $39.99 (Feb 08, 2020)  $54.99 (Feb 10, 2021)  ...
```

**Chart image URL (public, no auth needed):**
```
https://charts.camelcamelcamel.com/us/<ASIN>/new.png?force=1&zero=0&w=1022&h=529&desired=false&legend=1&ilt=1&tp=all&fo=0&lang=en
```

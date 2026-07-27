---
name: wechat-content
description: "Extract full text content from WeChat public account (微信公众号) articles — handles anti-crawler captchas, environment checks, and JS-heavy pages that block naive curl and browser tool approaches."
tags: [wechat, 微信公众号, chinese-social-media, content-extraction, anti-bot]
---

# WeChat (微信公众号) Article Content Extraction

Extract full article text, title, metadata, and images from WeChat public account (mp.weixin.qq.com) article URLs — even when the page is behind a captcha, environment check, or aggressive anti-bot protection that blocks the browser tool and standard curl requests.

## When to use

Use this skill when someone shares an `mp.weixin.qq.com/s/...` URL (or any WeChat article link) and asks you to summarize, read, or tell them what it says. WeChat public account articles use aggressive anti-scraping measures including:

- **Environment check ("环境异常")** — captcha page that blocks non-WeChat browsers
- **JSFuck-style obfuscation** — page content is rendered via heavily obfuscated JS
- **Sniffing for MicroMessenger UA** — only the real WeChat in-app browser gets clean access
- **Residential proxy requirements** — datacenter IPs often trigger additional checks

## Quick Reference

| Situation | Approach |
|-----------|----------|
| Browser shows "环境异常" captcha | DON'T try to bypass captcha — switch to curl with MicroMessenger UA |
| curl returns JS soup | Save HTML to file first, then parse with Python — page is 2-3MB of obfuscated JS |
| Article content needed | Extract from `id="js_content"` div after using correct WeChat UA |
| Image URLs in article | They use `mmbiz.qpic.cn` — publicly accessible, can be downloaded separately |

## Step-by-Step Workflow

### 1. First attempt — curl with MicroMessenger User-Agent

Standard browser tool and naive `curl` will almost always fail. The key is to mimic the **WeChat in-app browser**:

```bash
curl -sL "https://mp.weixin.qq.com/s/{ARTICLE_ID}" \
  -A "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36 MicroMessenger/8.0.47" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  -H "Referer: https://mp.weixin.qq.com/" \
  -H "X-Requested-With: com.tencent.mm" \
  --compressed -o /opt/data/tmp/wx_article.html
```

Key headers:
- **User-Agent**: Must include `MicroMessenger/8.0.x` — this is the most critical piece
- **X-Requested-With**: Must be `com.tencent.mm` — signals the request comes from the WeChat app
- **Referer**: `https://mp.weixin.qq.com/` — matches WeChat in-app browsing patterns
- **Accept-Language**: `zh-CN,zh;...` — Chinese language preference

### 2. Save HTML to file before parsing

The page is typically **2-3 MB** of heavily obfuscated JavaScript. Always save to a file first, then parse:

```bash
curl -sL "..." -o /opt/data/tmp/wx_article.html

# Verify file size — should be > 100KB for a real article
ls -la /opt/data/tmp/wx_article.html
```

### 3. Extract content from `id="js_content"` div

The article content is inside a `<div id="js_content">` element. Use Python to extract and clean it:

```python
import re

with open('/opt/data/tmp/wx_article.html', 'r', encoding='utf-8', errors='replace') as f:
    data = f.read()

# Extract the content div
m = re.search(r'id="js_content"[^>]*>(.*?)</div\s*>', data, re.DOTALL)
if not m:
    # Fallback: try rich_media_content class
    m = re.search(r'rich_media_content[^>]*>(.*?)</div\s*>', data, re.DOTALL)

html = m.group(1) if m else data

# Clean HTML tags while preserving structure
# Remove scripts, styles, SVGs
html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)

# Convert structural elements to newlines
for tag in ['section', 'p', 'div', 'br']:
    html = re.sub(rf'<{tag}[^>]*>', '\n', html)
    html = re.sub(rf'</{tag}>', '\n', html)

# Keep markdown formatting from strong/em
html = re.sub(r'<strong[^>]*>', '**', html)
html = re.sub(r'</strong>', '**', html)
html = re.sub(r'<em[^>]*>', '*', html)
html = re.sub(r'</em>', '*', html)

# Strip remaining tags
text = re.sub(r'<[^>]+>', '', html)

# Decode HTML entities
text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')

# Clean up whitespace
lines = [l.strip() for l in text.split('\n')]
lines = [l for l in lines if l]
text = '\n\n'.join(lines)
```

### 4. Extract metadata

Title (from page title or meta tags):

```python
# Page title (may be empty due to JS rendering)
t = re.search(r'<title>(.*?)</title>', data)

# Meta description (often contains summary)
m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', data)

# Author / account name (公众号名称)
a = re.search(r'<em[^>]*class="rich_media_meta_text"[^>]*>(.*?)</em>', data)
```

### 5. Handle images

Images in WeChat articles use `mmbiz.qpic.cn` URLs — these are publicly accessible:

```python
imgs = re.findall(r'<img[^>]+src="(https://mmbiz\.qpic\.cn[^"]+)"', data)
```

You can include these as markdown images or download them for inline display.

### 6. Cleanup

Always remove the temporary file after extraction:

```bash
rm -f /opt/data/tmp/wx_article.html
```

## Common Pitfalls

- **"环境异常" captcha in browser**: The browser tool will almost always trigger WeChat's environment check. Do NOT try to click through captcha — it won't work from a datacenter IP. Switch immediately to curled MicroMessenger UA approach.
- **Empty `js_content` div**: If the parsed content is empty or very short (< 100 chars), the article likely requires JS execution in the WeChat browser. Try a different UA (iOS vs Android) or accept that some articles are truly inaccessible without a real device.
- **3MB+ HTML pages**: The obfuscated JS payload is enormous. Always save to file and parse; don't try to pipe directly into `grep` or inline Python.
- **Title may be empty**: The `<title>` tag is sometimes set to empty string in the HTML, filled later by JS. Check the `og:title` meta tag as a fallback.
- **Rate limiting**: If you fetch multiple articles in quick succession, WeChat may temporarily block your IP. Add a 1-2 second delay between requests.
- **Google cache / Wayback Machine**: These are almost always blocked by WeChat before they can index the page — don't waste time on them.
- **Article URL validation**: The article ID is the path segment after `/s/` — it's a base64-like string. If the URL contains extra params (`?`), strip them before fetching.

## Comparison with douyin-content

This skill differs from `douyin-content` in the core evasion technique:
- **Douyin**: Relies on `browser_vision` to read through login overlays (visual approach)
- **WeChat**: Relies on curl with MicroMessenger UA and headers (protocol-level deception)
- **Reason**: WeChat articles are text-heavy (no video player), so curl+parse works; Douyin video pages require JS execution for video metadata

## Support Files

- `references/session-example.md` — full worked example from an actual extraction session (Anthropic vs OpenAI article)
- `scripts/extract_article.py` — reusable extraction script: save HTML with curl, then run `python3 scripts/extract_article.py /opt/data/tmp/wx_article.html` to get cleaned content (use `--json` for structured output)

#!/usr/bin/env python3
"""
Extract WeChat public account article content from a saved HTML file.

Usage:
    python3 extract_wx_article.py /opt/data/tmp/wx_article.html

Outputs title, metadata, cleaned text content, and image URLs to stdout.
"""

import re
import sys
import json


def extract(data):
    result = {
        'title': '',
        'description': '',
        'author': '',
        'content': '',
        'images': [],
        'word_count': 0,
    }

    # Title
    m = re.search(r'<title>(.*?)</title>', data)
    if m:
        result['title'] = m.group(1).strip()
    if not result['title']:
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', data)
        if m:
            result['title'] = m.group(1)

    # Meta description
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', data)
    if m:
        result['description'] = m.group(1)

    # Author / account name
    m = re.search(r'<em[^>]*class="rich_media_meta_text"[^>]*>(.*?)</em>', data)
    if m:
        result['author'] = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    # Images (mmbiz.qpic.cn)
    result['images'] = re.findall(
        r'<img[^>]+src="(https://mmbiz\.qpic\.cn[^"]+)"', data
    )

    # Main content
    m = re.search(r'id="js_content"[^>]*>(.*?)</div\s*>', data, re.DOTALL)
    if not m:
        m = re.search(
            r'rich_media_content[^>]*>(.*?)</div\s*>', data, re.DOTALL
        )

    html = m.group(1) if m else data

    # Remove non-content blocks
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)

    # Convert block elements to newlines
    for tag in ['section', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'li']:
        html = re.sub(rf'<{tag}[^>]*>', '\n', html)
        html = re.sub(rf'</{tag}>', '\n', html)
    html = re.sub(r'<br\s*/?>', '\n', html)

    # Preserve markdown formatting from inline tags
    html = re.sub(r'<strong[^>]*>', '**', html)
    html = re.sub(r'</strong>', '**', html)
    html = re.sub(r'<em[^>]*>', '*', html)
    html = re.sub(r'</em>', '*', html)

    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', html)

    # Decode HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'&#\d+;', '', text)

    # Clean whitespace
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if l]
    result['content'] = '\n\n'.join(lines)
    result['word_count'] = len(result['content'])

    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 extract_wx_article.py <html_file> [--json]', file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8', errors='replace') as f:
        data = f.read()

    result = extract(data)
    use_json = '--json' in sys.argv

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"标题: {result['title']}")
        print(f"作者: {result['author']}")
        if result['description']:
            print(f"描述: {result['description'][:200]}")
        print(f"图片数: {len(result['images'])}")
        print(f"字数: {result['word_count']}")
        print("\n" + "=" * 60)
        print(result['content'])

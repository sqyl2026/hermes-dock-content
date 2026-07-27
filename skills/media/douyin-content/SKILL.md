---
name: douyin-content
description: "Extract text content, descriptions, metadata, and chapter info from Douyin (抖音) video share links using browser and web techniques. Covers anti-bot evasion through login overlays."
tags: [douyin, tiktok, chinese-social-media, video, content-extraction]
---

# Douyin (抖音) Content Extraction

Extract video title, description, author, engagement stats, tags, and chapter breakdowns from Douyin video share links — even when the page is behind a login overlay or bot-protected.

## When to use

Use this skill any time someone shares a `douyin.com` or `iesdouyin.com` video URL and asks you to summarize, describe, or tell them what the video says. Douyin is the Chinese version of TikTok and has aggressive anti-bot measures, so naive curl/browser approaches often fail.

## Quick Reference

| Situation | Approach |
|-----------|----------|
| Page loads but login overlay blocks DOM | `browser_vision` with Chinese prompt — reads visible content through the overlay |
| Page shell shows "视频数据加载中" | Scroll down, then retry browser_console or browser_vision |
| Title / meta description needed | `browser_console` → `document.title`, `meta[name="description"]` |
| Full transcript / chapters needed | `browser_console` → TreeWalker to collect all visible text |
| Direct API access | ❌ Blocked from datacenter IPs — skip this path |

## Step-by-Step Workflow

### 1. Normalize the URL

Share links often come through `iesdouyin.com` — they redirect to `douyin.com`. Either form works:

```
https://www.iesdouyin.com/share/video/{VIDEO_ID}/...many-params...
→ redirects to https://www.douyin.com/video/{VIDEO_ID}
```

Navigate to the clean `douyin.com/video/{VIDEO_ID}` URL via `browser_navigate`.

### 2. First pass — extract metadata (browser_console)

```javascript
// Page title (usually contains the video's main text)
document.title

// Meta description (contains full description + author + likes count)
document.querySelector('meta[name="description"]')?.content
```

The meta description is the most reliable source — Douyin embeds it server-side and it's available even when the rest of the page is blocked.

### 3. Second pass — full visible text (browser_console TreeWalker)

When the login overlay doesn't fully block the DOM, extract all visible text:

```javascript
const texts = [];
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
let node;
while (node = walker.nextNode()) {
  const t = node.textContent.trim();
  if (t.length > 5) texts.push(t);
}
```

This captures chapter titles, video description text, author info, and any other UI text that's rendered.

### 4. Fallback — browser_vision through login overlay (most reliable)

When login overlay, empty DOM, or bot detection blocks everything else, `browser_vision` can still read the visible pixels on screen through the overlay:

```
browser_vision(question="这个抖音视频页面显示了什么内容？视频标题、描述、作者、评论等信息是什么？")
```

**Chinese prompt works best.** English prompts sometimes get less detailed responses from the vision model on Chinese UIs.

This approach reliably reveals:
- Video title/description (visible behind the login modal)
- Author name and follower count
- Like/comment/save/share counts
- Related video recommendations

### 5. (Optional) curl with mobile User-Agent

```bash
curl -sL "https://m.douyin.com/video/{VIDEO_ID}" \
  -H "User-Agent: Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"
```

This sometimes works when the desktop page is blocked, but frequently returns 404 for videos that were deleted or made private.

## Common Pitfalls

- **Login overlay blocks everything**: Douyin shows a large "登录后免费畅享高清视频" modal that prevents DOM access. `browser_console` returns empty arrays. **This is the most common failure mode** — immediately jump to step 4 (browser_vision).
- **"视频数据加载中" hangs**: The page shell loads but video data never renders due to anti-bot. Scroll down once (`browser_scroll(direction="down")`) to trigger lazy-loading, then retry.
- **API is blocked**: The `aweme/v1/web/aweme/detail/` API endpoint returns literal `"blocked"` from datacenter IPs. Do not attempt this path from a non-residential IP.
- **iesdouyin.com JS obfuscation**: Heavy JSFuck-style obfuscation prevents curl extraction of embedded data on third-party parser sites.
- **Deleted/private videos**: Some URLs return 404 on the mobile version even when the desktop page loads. Check with both desktop and mobile approaches.
- **Blank first screenshot**: If browser_vision returns a blank/empty analysis, navigate again or scroll first — the page may not have painted yet.
- **Douyin redirect chain**: The iesdouyin URL includes many tracking params (`u_code`, `did`, `iid`, `share_sign`, etc.). These are irrelevant for content extraction — use the clean video ID.

## Example Session

```
1. User shares: https://www.iesdouyin.com/share/video/7618952945069816730/...

2. browser_navigate(url="https://www.douyin.com/video/7618952945069816730")
   → Page shows "视频数据加载中"

3. browser_scroll(direction="down")
   → Triggers content render

4. browser_console(expression="document.title")
   → "腾讯龙虾挺好！用 #腾讯 - 抖音"

5. browser_console(expression='document.querySelector(\'meta[name="description"]\')?.content')
   → "腾讯龙虾挺好！用 #腾讯 - 乐弟长远投资（AI硬件板块）于20260319发布在抖音，已经收获了57.5万个喜欢..."

6. browser_console(TreeWalker) — if DOM is accessible
   → Chapters: "安装方式：支持一键安装", "多平台短视频批量发布", etc.

7. If login overlay blocks step 6, use:
   browser_vision(question="这个抖音视频页面显示了什么内容？")
   → Vision reads title, author, stats through the overlay
```

## References

- Douyin video ID is the numeric segment: `/video/{VIDEO_ID}`
- Share links use `iesdouyin.com` → redirects to `douyin.com`
- Mobile version: `m.douyin.com` (UA-dependent rendering)

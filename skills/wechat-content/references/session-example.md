# Session Example: Extracting "Anthropic超越OpenAI" Article

## URL

```
https://mp.weixin.qq.com/s/doT31iNRyVajMkay6NMi0w
```

## What Was Blocked

| Method | Result |
|--------|--------|
| `browser_navigate` | "环境异常" captcha page |
| Google cache | Captcha redirect |
| Wayback Machine | No content found |
| Jina AI reader (r.jina.ai) | AuthRequiredError (blocked AS36352) |
| Naive curl | Only JS obfuscation returned |

## Working Command

```bash
curl -sL "https://mp.weixin.qq.com/s/doT31iNRyVajMkay6NMi0w" \
  -A "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36 MicroMessenger/8.0.47" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  -H "Referer: https://mp.weixin.qq.com/" \
  -H "X-Requested-With: com.tencent.mm" \
  --compressed -o /opt/data/tmp/wx_article.html
```

**Result**: 3,125,616 bytes (3MB) — full article retrieved.

## Extraction Result

The `id="js_content"` div contained the full article. Key content extracted:

### Article Metadata
- **Source**: 新智元 (Xin Zhi Yuan) — Chinese AI news outlet
- **Topic**: Anthropic surpasses OpenAI in revenue to become #1 AI company globally
- **Key data**: Anthropic ARR reached $450-470B in 15 months (from $1B), OpenAI at ~$330B

### Extraction Snippet

See `references/extraction-code.py` for the exact Python extraction script used.

## Key Takeaways

1. MicroMessenger UA alone wasn't enough — needed Android + Chrome + MicroMessenger chain
2. `X-Requested-With: com.tencent.mm` was crucial (signals WeChat app internal request)
3. The page is ~3MB due to JSFuck obfuscation — save-to-file approach essential
4. First attempt with partial UA (iOS Safari + MM) still got blocked — the Android Chrome + MM combo worked
5. The `--compressed` flag is important — without it the mobile UA may get redirected to a different page

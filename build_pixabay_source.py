#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pixabay_source.py — 生成 Pixabay 免费视频 JSON 片源（苹果 CMS 格式）

数据来源：Pixabay Videos API（免费可商用许可，需 key）
用法：
    python build_pixabay_source.py --key YOUR_KEY
    python build_pixabay_source.py --key YOUR_KEY --limit 40 --out pixabay-source.json

说明：
    - Pixabay API 需要免费 key（https://pixabay.com/api/docs/ 申请）；
    - 接口 CORS 为 *，可直接用 pixabay-maker.html 在浏览器生成（填入你的 key）；
    - 不填 key 时输出空列表 + 说明，请先生成再上传覆盖本文件。
"""
import json
import sys
import urllib.request
import urllib.parse

OUT = "pixabay-source.json"
TOPICS = ["nature", "sky", "ocean", "forest", "city", "animal", "flower", "mountain", "cloud", "water"]


def get(url, key):
    req = urllib.request.Request(url, headers={"User-Agent": "OuonnkiTV/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    global OUT
    key = ""
    limit = 40
    for a in sys.argv[1:]:
        if a.startswith("--key"):
            key = a.split("=")[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
        elif a.startswith("--out"):
            OUT = a.split("=")[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
        elif a.startswith("--limit"):
            limit = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])

    items = []
    if not key:
        print("未提供 key，输出空列表（请用 --key 重跑，或用 pixabay-maker.html 生成）。")
    else:
        seen = {}
        for t in TOPICS:
            if len(items) >= limit:
                break
            try:
                url = ("https://pixabay.com/api/videos/?key=%s&q=%s&per_page=20&safesearch=true"
                       % (urllib.parse.quote(key), urllib.parse.quote(t)))
                d = get(url, key)
            except Exception as e:
                print("  [skip] query 失败:", t, e)
                continue
            for h in d.get("hits", []):
                hid = h.get("id")
                if hid in seen:
                    continue
                seen[hid] = 1
                vids = h.get("videos") or {}
                best = vids.get("large") or vids.get("medium") or vids.get("small") or {}
                u = best.get("url")
                if not u:
                    continue
                tags = (h.get("tags") or "").replace(",", " ").strip()
                items.append({
                    "vod_id": "pixabay-%s" % hid,
                    "vod_name": tags.split(" ")[0] if tags else ("Pixabay 视频 %s" % hid),
                    "type_name": "Pixabay 素材",
                    "vod_year": "",
                    "vod_remarks": "Pixabay 许可（免费可商用）",
                    "vod_pic": h.get("previewURL") or "",
                    "vod_play_from": "Pixabay",
                    "vod_play_url": "正片$%s" % u,
                    "vod_content": "Pixabay 免费视频，标签：%s；作者：%s。" % (tags, h.get("user", "未知")),
                })

    out = {
        "code": 1,
        "msg": "Pixabay 免费视频（需 key 生成；用 pixabay-maker.html 或 build_pixabay_source.py）",
        "page": 1, "pagecount": 1, "limit": len(items), "total": len(items),
        "list": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已写入 %s，共 %d 条" % (OUT, len(items)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_nasa_source.py — 生成 NASA 公有领域影音 JSON 片源（苹果 CMS 格式）

数据来源：NASA 官方 images-api.nasa.gov（美国联邦政府作品，公有领域，无需 key）
用法：
    python build_nasa_source.py                 # 生成 nasa-source.json
    python build_nasa_source.py --limit 80      # 控制总条数上限
    python build_nasa_source.py --out xxx.json

说明：
    - 搜索多个航天/自然主题，取视频条目；
    - 每条解析 collection.json，挑出 mp4 直链 + 一张图片做海报；
    - 全部为公有领域内容，浏览器/客户端可直接播放，无需代理、无需 key。
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse

UA = "OuonnkiTV/1.0 (public-domain video aggregator; +https://github.com/1333555777/OuonnkiTV)"
OUT = "nasa-source.json"
LIMIT = 60

QUERIES = [
    "moon", "mars", "earth", "rocket launch", "space station", "sun",
    "galaxy", "saturn", "black hole", "nebula", "solar system", "astronaut",
    "jupiter", "comet", "aurora", "iss", "telescope", "eclipse",
]


def get(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def pick_video_and_poster(urls):
    """NASA collection.json 是一个 URL 字符串数组。挑 mp4（优先 ~large）+ 一张图片做海报。"""
    mp4 = None
    large = None
    poster = None
    for u in urls:
        ul = u.lower()
        if ul.endswith(".mp4"):
            if large is None and "~large" in ul:
                large = u
            if mp4 is None and "~orig" not in ul:
                mp4 = u
        elif ul.endswith((".jpg", ".jpeg", ".png")) and poster is None:
            poster = u
    if not mp4 and large:
        mp4 = large
    if not mp4:
        for u in urls:
            if u.lower().endswith((".mov", ".webm", ".m4v", ".ogg")):
                mp4 = u
                break
    if mp4:
        mp4 = mp4.replace("http://", "https://").replace(" ", "%20")
    if poster:
        poster = poster.replace("http://", "https://").replace(" ", "%20")
    return mp4, poster


def main():
    limit = LIMIT
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        elif a.startswith("--out"):
            global OUT
            OUT = a.split("=")[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]

    seen = {}
    items = []
    for q in QUERIES:
        if len(items) >= limit:
            break
        try:
            url = "https://images-api.nasa.gov/search?q=%s&media_type=video" % urllib.parse.quote(q)
            d = get(url)
        except Exception as e:
            print("  [skip] query 失败:", q, e)
            continue
        for it in d.get("collection", {}).get("items", []):
            if len(items) >= limit:
                break
            data = (it.get("data") or [{}])[0]
            nasa_id = data.get("nasa_id")
            href = it.get("href", "")
            if not nasa_id or not href or nasa_id in seen:
                continue
            try:
                m = get(href.replace(" ", "%20"))
            except Exception:
                continue
            files = m.get("collection", {}).get("items", []) if isinstance(m, dict) else m
            mp4, poster = pick_video_and_poster(files)
            if not mp4:
                continue
            title = (data.get("title") or nasa_id).strip()
            desc = re.sub(r"\s+", " ", (data.get("description") or "")).strip()
            year = (data.get("date_created") or "")[:4]
            items.append({
                "vod_id": nasa_id,
                "vod_name": title,
                "type_name": "NASA 影像",
                "vod_year": year,
                "vod_remarks": "美国联邦政府作品 · 公有领域",
                "vod_pic": poster or "",
                "vod_play_from": "NASA官方",
                "vod_play_url": "正片$%s" % mp4,
                "vod_content": desc[:500],
            })
            seen[nasa_id] = 1
            time.sleep(0.2)
        time.sleep(0.4)

    out = {
        "code": 1,
        "msg": "NASA 公有领域影音库（images-api.nasa.gov 自动生成，无 key / 直链 mp4）",
        "page": 1, "pagecount": 1, "limit": len(items), "total": len(items),
        "list": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已写入 %s，共 %d 条" % (OUT, len(items)))


if __name__ == "__main__":
    main()

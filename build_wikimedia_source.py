#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_wikimedia_source.py — 生成 Wikimedia Commons 公有领域 / CC 视频 JSON 片源

数据来源：Wikimedia Commons API（CC / 公有领域视频，无需 key）
用法：
    python build_wikimedia_source.py
    python build_wikimedia_source.py --limit 60 --out wikimedia-source.json

说明：
    - 按多个主题搜索 Commons 上的视频文件（filetype:video）；
    - 取原始视频直链（webm/ogv）与一张缩略图做海报；
    - 注意：Commons 视频多为 webm/ogv，Chromium(Edge/Chrome) 原生支持，
      Safari 对 webm 支持有限，可能需在 Safari 之外播放。
    - 接口有频率限制，已做 429 退避重试。
"""
import json
import sys
import time
import urllib.request
import urllib.parse

UA = "OuonnkiTV/1.0 (public-domain video aggregator; contact: user@example.com)"
OUT = "wikimedia-source.json"
LIMIT = 50

TOPICS = [
    "space", "earth", "nature", "wildlife", "city", "ocean", "mountain",
    "time lapse", "clouds", "river", "forest", "desert", "volcano",
    "aurora", "galaxy", "wild animals", "sunset", "storm",
]


def get(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (i + 1))
                last = e
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def main():
    global OUT
    limit = LIMIT
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        elif a.startswith("--out"):
            OUT = a.split("=")[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]

    seen = {}
    items = []
    for t in TOPICS:
        if len(items) >= limit:
            break
        try:
            q = "filetype:video %s" % t
            url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                   "&list=search&srsearch=%s&srnamespace=6&srlimit=%d" % (
                       urllib.parse.quote(q), 8))
            d = get(url)
        except Exception as e:
            print("  [skip] search 失败:", t, e)
            continue
        for s in d.get("query", {}).get("search", []):
            if len(items) >= limit:
                break
            title = s.get("title")
            if not title or title in seen:
                continue
            seen[title] = 1
            try:
                iu = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                      "&titles=%s&prop=imageinfo&iiprop=url|mime|size|thumburl&iiurlwidth=480" % (
                          urllib.parse.quote(title)))
                info = get(iu)
            except Exception:
                continue
            pages = list(info.get("query", {}).get("pages", {}).values())
            if not pages:
                continue
            ii = (pages[0].get("imageinfo") or [{}])[0]
            mime = (ii.get("mime") or "").lower()
            if not mime.startswith("video"):
                continue
            vurl = ii.get("url")
            thumb = ii.get("thumburl") or ""
            name = title.replace("File:", "").rsplit(".", 1)[0]
            items.append({
                "vod_id": title,
                "vod_name": name,
                "type_name": "Wikimedia 视频",
                "vod_year": "",
                "vod_remarks": "CC / 公有领域（Wikimedia Commons）",
                "vod_pic": thumb,
                "vod_play_from": "Commons",
                "vod_play_url": "正片$%s" % vurl,
                "vod_content": "来自 Wikimedia Commons 的公开授权视频（webm/ogv 格式）。",
            })
            time.sleep(0.4)
        time.sleep(0.6)

    out = {
        "code": 1,
        "msg": "Wikimedia Commons 公有领域/CC 视频（自动生成，无 key / webm 直链）",
        "page": 1, "pagecount": 1, "limit": len(items), "total": len(items),
        "list": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已写入 %s，共 %d 条" % (OUT, len(items)))


if __name__ == "__main__":
    main()

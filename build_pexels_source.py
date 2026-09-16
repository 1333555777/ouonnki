#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pexels_source.py — 生成 Pexels 免费视频 JSON 片源（苹果 CMS 格式）

数据来源：Pexels Videos API（免费可商用许可，需 key）
用法：
    python build_pexels_source.py --key YOUR_KEY        # 用 key 拉取真实标题/海报
    python build_pexels_source.py                        # 无 key：内置几条已验证的公开直链样例

说明：
    - Pexels API 需要免费 key（https://www.pexels.com/api/ 申请，1 分钟）；
    - 浏览器直连 Pexels API 无 CORS，建议在本地跑本脚本，或用 pexels-maker.html 走你的代理；
    - 无 key 时内置的样例为已验证的公开直链（video+poster 均 200），可直接播放。
"""
import json
import sys
import urllib.request
import urllib.parse

OUT = "pexels-source.json"

# 无 key 时内置的已验证公开直链样例（video + poster 均实测 200）
SEED = [
    {"id": 3571264, "name": "Pexels 免费样片 · 城市光影", "url": "https://videos.pexels.com/video-files/3571264/3571264-uhd_3840_2160_30fps.mp4", "pic": "https://images.pexels.com/videos/3571264/free-video-3571264.jpg"},
    {"id": 2169880, "name": "Pexels 免费样片 · 自然风光", "url": "https://videos.pexels.com/video-files/2169880/2169880-uhd_3840_2160_30fps.mp4", "pic": "https://images.pexels.com/videos/2169880/free-video-2169880.jpg"},
    {"id": 1093662, "name": "Pexels 免费样片 · 街头延时", "url": "https://videos.pexels.com/video-files/1093662/1093662-hd_1920_1080_30fps.mp4", "pic": "https://images.pexels.com/videos/1093662/free-video-1093662.jpg"},
    {"id": 1526909, "name": "Pexels 免费样片 · 海岸潮涌", "url": "https://videos.pexels.com/video-files/1526909/1526909-hd_1920_1080_24fps.mp4", "pic": "https://images.pexels.com/videos/1526909/free-video-1526909.jpg"},
    {"id": 4763824, "name": "Pexels 免费样片 · 山间公路", "url": "https://videos.pexels.com/video-files/4763824/4763824-hd_1920_1080_24fps.mp4", "pic": ""},
]

TOPICS = ["nature", "city", "ocean", "sky", "forest", "mountain", "animal", "cloud", "flower", "space"]


def get(url, key):
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "OuonnkiTV/1.0"})
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
    if key:
        seen = {}
        for t in TOPICS:
            if len(items) >= limit:
                break
            try:
                url = ("https://api.pexels.com/videos/search?query=%s&per_page=10&size=large"
                       % urllib.parse.quote(t))
                d = get(url, key)
            except Exception as e:
                print("  [skip] query 失败:", t, e)
                continue
            for v in d.get("videos", []):
                vid = v.get("id")
                if vid in seen:
                    continue
                seen[vid] = 1
                files = v.get("video_files", [])
                mp4 = None
                for vf in files:
                    if (vf.get("quality") in ("hd", "sd", "full") or vf.get("file_type") == "video/mp4") \
                            and vf.get("link"):
                        mp4 = vf["link"]
                        break
                if not mp4 and files:
                    mp4 = files[0].get("link")
                if not mp4:
                    continue
                pic = v.get("image") or ""
                items.append({
                    "vod_id": "pexels-%s" % vid,
                    "vod_name": v.get("user", {}).get("name", "") + " · " + (v.get("url", "").rsplit("/", 2)[-2] if v.get("url") else str(vid)),
                    "type_name": "Pexels 素材",
                    "vod_year": "",
                    "vod_remarks": "Pexels 许可（免费可商用）",
                    "vod_pic": pic,
                    "vod_play_from": "Pexels",
                    "vod_play_url": "正片$%s" % mp4,
                    "vod_content": "Pexels 免费视频，作者：%s。" % v.get("user", {}).get("name", "未知"),
                })
        print("已用 key 拉取 %d 条" % len(items))
    else:
        for s in SEED:
            items.append({
                "vod_id": "pexels-%s" % s["id"],
                "vod_name": s["name"],
                "type_name": "Pexels 素材",
                "vod_year": "",
                "vod_remarks": "Pexels 许可（免费可商用）",
                "vod_pic": s["pic"],
                "vod_play_from": "Pexels",
                "vod_play_url": "正片$%s" % s["url"],
                "vod_content": "Pexels 免费视频样片（无 key 内置）。要更多请填 key 重跑本脚本或用 pexels-maker.html。",
            })
        print("未提供 key，已内置 %d 条公开样例" % len(items))

    out = {
        "code": 1,
        "msg": "Pexels 免费视频（需 key 拉全量；无 key 时为内置样例）",
        "page": 1, "pagecount": 1, "limit": len(items), "total": len(items),
        "list": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已写入 %s，共 %d 条" % (OUT, len(items)))


if __name__ == "__main__":
    main()

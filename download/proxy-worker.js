// ============================================================
// OuonnkiTV 跨域代理 · Cloudflare Worker
// 部署后把  https://xxxxx.workers.dev/?url=  填进站点
// 「片源设置 → 代理前缀」，即可直连任意片源。
//
// 能力：
//   · 加 CORS 头，让浏览器能跨域读取片源接口
//   · 透传 Range 请求（视频拖动进度条必需）
//   · 自动改写 m3u8 里的分片/密钥地址，让它们也走代理
//   · 拒绝内网地址，避免被当成 SSRF 跳板
//   · 可选域名白名单，防止被别人拿去当公开代理
// ============================================================

const DEFAULT_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Expose-Headers": "*",
  "Access-Control-Max-Age": "86400",
};

function json(obj, status) {
  return new Response(JSON.stringify(obj, null, 2), {
    status: status,
    headers: Object.assign({ "content-type": "application/json; charset=utf-8" }, CORS),
  });
}

// 是否内网 / 本机地址（SSRF 防护）
function isPrivate(host) {
  const h = host.toLowerCase();
  if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) return true;
  if (h === "::1" || h === "0.0.0.0" || h === "[::1]") return true;
  if (/^127\./.test(h)) return true;
  if (/^10\./.test(h)) return true;
  if (/^192\.168\./.test(h)) return true;
  if (/^169\.254\./.test(h)) return true; // 含云厂商元数据地址
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(h)) return true;
  if (/^(fc|fd)/.test(h)) return true; // IPv6 私网
  return false;
}

// 把目标地址包一层代理
function toProxy(target, selfUrl) {
  return selfUrl.origin + selfUrl.pathname + "?url=" + encodeURIComponent(target);
}

// 改写 m3u8：相对地址补全、绝对地址全部改成走代理
function rewriteM3U8(text, base, selfUrl) {
  const abs = (u) => {
    try {
      return toProxy(new URL(u, base).href, selfUrl);
    } catch (e) {
      return u;
    }
  };
  return text
    .split(/\r?\n/)
    .map((line) => {
      const s = line.trim();
      if (!s) return "";
      if (s.startsWith("#")) {
        // 处理 #EXT-X-KEY:METHOD=AES-128,URI="..." 之类带地址的属性
        return s.replace(/URI="([^"]+)"/g, (m, u) => 'URI="' + abs(u) + '"');
      }
      return abs(s);
    })
    .join("\n");
}

export default {
  async fetch(request, env) {
    const selfUrl = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // 根路径：返回一段使用说明，方便确认是否部署成功
    if (selfUrl.pathname === "/" && !selfUrl.searchParams.get("url")) {
      return json({
        ok: true,
        service: "OuonnkiTV CORS Proxy",
        usage: selfUrl.origin + "/?url=" + encodeURIComponent("https://example.com/api.php/provide/vod/?ac=videolist&wd=关键词"),
        tip: "把这个地址填进站点「片源设置 → 代理前缀」： " + selfUrl.origin + "/?url=",
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return json({ error: "只支持 GET / HEAD" }, 405);
    }

    const target = selfUrl.searchParams.get("url");
    if (!target) return json({ error: "缺少 url 参数" }, 400);

    let t;
    try {
      t = new URL(target);
    } catch (e) {
      return json({ error: "url 不是合法地址" }, 400);
    }
    if (t.protocol !== "http:" && t.protocol !== "https:") {
      return json({ error: "只支持 http / https" }, 400);
    }
    if (isPrivate(t.hostname)) {
      return json({ error: "内网地址已被拒绝：" + t.hostname }, 403);
    }

    // 可选白名单：在 Worker 设置里加环境变量 ALLOWED_HOSTS，逗号分隔，例如
    //   a.com,b.com
    // 留空表示不限制（不推荐，容易被别人当公开代理薅流量）
    const allowed = String((env && env.ALLOWED_HOSTS) || "")
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    if (
      allowed.length &&
      !allowed.some((h) => t.hostname === h || t.hostname.endsWith("." + h))
    ) {
      return json({ error: "域名不在白名单内：" + t.hostname }, 403);
    }

    // 透传必要请求头（Range 决定视频能否拖动）
    const headers = new Headers();
    const passList = ["range", "if-range", "accept", "accept-language", "referer", "origin", "cookie"];
    passList.forEach((k) => {
      const v = request.headers.get(k);
      if (v) headers.set(k, v);
    });
    if (!headers.has("user-agent")) headers.set("user-agent", DEFAULT_UA);
    if (!headers.has("referer")) headers.set("referer", t.origin + "/");

    let upstream;
    try {
      upstream = await fetch(t.href, {
        method: request.method,
        headers: headers,
        redirect: "follow",
      });
    } catch (e) {
      return json({ error: "上游请求失败：" + e.message }, 502);
    }

    const ct = (upstream.headers.get("content-type") || "").toLowerCase();
    const isM3U8 =
      ct.includes("mpegurl") || ct.includes("x-mpegurl") || t.pathname.endsWith(".m3u8");

    if (isM3U8 && upstream.status === 200) {
      const text = await upstream.text();
      const body = rewriteM3U8(text, t, selfUrl);
      const h = new Headers(upstream.headers);
      h.delete("content-length");
      h.delete("content-encoding");
      Object.keys(CORS).forEach((k) => h.set(k, CORS[k]));
      h.set("content-type", "application/vnd.apple.mpegurl; charset=utf-8");
      h.set("cache-control", "no-store");
      return new Response(body, { status: 200, headers: h });
    }

    const h = new Headers(upstream.headers);
    Object.keys(CORS).forEach((k) => h.set(k, CORS[k]));
    h.set("accept-ranges", "bytes");
    h.delete("content-security-policy");
    return new Response(request.method === "HEAD" ? null : upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: h,
    });
  },
};

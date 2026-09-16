# -*- coding: utf-8 -*-
"""OuonnkiTV 本地跨域代理（无需 Cloudflare，标准库实现）

用法：
    python proxy_local.py            # 默认监听 8787
    python proxy_local.py 9000       # 指定端口

然后在站点「片源设置 → 代理前缀」填：
    http://127.0.0.1:8787/?url=

特性：CORS、Range 透传（视频可拖动）、m3u8 地址改写、拒绝内网地址。
仅用于本机自用，请不要暴露到公网。
"""
import sys
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PASS_HEADERS = ("range", "if-range", "accept", "accept-language", "referer", "cookie")
TIMEOUT = 25


def is_private(host: str) -> bool:
    h = host.lower().strip("[]")
    if h in ("localhost", "::1", "0.0.0.0") or h.endswith((".localhost", ".local", ".internal")):
        return True
    for pat in (r"^127\.", r"^10\.", r"^192\.168\.", r"^169\.254\.", r"^(fc|fd)"):
        if re.match(pat, h):
            return True
    m = re.match(r"^172\.(\d+)\.", h)
    if m and 16 <= int(m.group(1)) <= 31:
        return True
    return False


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "OuonnkiLocalProxy/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Expose-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, obj, status=200):
        import json

        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_HEAD(self):
        self._proxy(head_only=True)

    def do_GET(self):
        self._proxy(head_only=False)

    def _proxy(self, head_only=False):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        target = (qs.get("url") or [""])[0]

        if not target:
            self._json(
                {
                    "ok": True,
                    "service": "OuonnkiTV Local CORS Proxy",
                    "usage": "http://127.0.0.1:%d/?url=%s"
                    % (self.server.server_address[1], urllib.parse.quote("https://example.com", safe="")),
                    "tip": "把 http://127.0.0.1:%d/?url= 填进站点「片源设置 → 代理前缀」"
                    % self.server.server_address[1],
                }
            )
            return

        try:
            t = urllib.parse.urlparse(target)
        except Exception:
            self._json({"error": "url 解析失败"}, 400)
            return
        if t.scheme not in ("http", "https"):
            self._json({"error": "只支持 http / https"}, 400)
            return
        if not t.hostname or is_private(t.hostname):
            self._json({"error": "内网地址已被拒绝：%s" % t.hostname}, 403)
            return

        req = urllib.request.Request(target, method="HEAD" if head_only else "GET")
        req.add_header("User-Agent", UA)
        for k in PASS_HEADERS:
            v = self.headers.get(k)
            if v:
                req.add_header(k, v)
        if not self.headers.get("referer"):
            req.add_header("Referer", "%s://%s/" % (t.scheme, t.netloc))

        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception as e:
            self._json({"error": "上游请求失败：%s" % e}, 502)
            return

        ctype = (resp.headers.get("Content-Type") or "").lower()
        is_m3u8 = "mpegurl" in ctype or t.path.endswith(".m3u8")

        if is_m3u8 and getattr(resp, "status", 200) == 200 and not head_only:
            try:
                text = resp.read().decode("utf-8", "replace")
                body = rewrite_m3u8(text, target, self)
            except Exception:
                body = ""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(getattr(resp, "status", 200))
        for k, v in resp.headers.items():
            if k.lower() in ("transfer-encoding", "connection", "content-encoding", "content-length"):
                continue
            if k.lower() in ("content-security-policy", "x-frame-options"):
                continue
            self.send_header(k, v)
        self.send_header("Accept-Ranges", "bytes")
        self._cors()
        self.end_headers()

        if head_only:
            return
        try:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] %s - %s\n" % (self.address_string(), fmt % args))


def rewrite_m3u8(text, base, handler):
    host, port = handler.server.server_address[0], handler.server.server_address[1]

    def to_proxy(u):
        absolute = urllib.parse.urljoin(base, u)
        return "http://127.0.0.1:%d/?url=%s" % (port, urllib.parse.quote(absolute, safe=""))

    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            out.append(re.sub(r'URI="([^"]+)"', lambda m: 'URI="%s"' % to_proxy(m.group(1)), s))
        else:
            out.append(to_proxy(s))
    return "\n".join(out)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    with Server(("127.0.0.1", port), ProxyHandler) as httpd:
        print("OuonnkiTV 本地代理已启动： http://127.0.0.1:%d" % port)
        print("填进站点设置的代理前缀： http://127.0.0.1:%d/?url=" % port)
        print("Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


if __name__ == "__main__":
    main()

"""Screenshot every SabzBank page and log browser problems, through one headless Chrome (CDP).

Usage:
    backend/.venv/bin/python scripts/screenshots.py BASE_URL OUT_DIR [--chrome PATH]
    backend/.venv/bin/python scripts/screenshots.py http://127.0.0.1:3126 /tmp/shots

Writes OUT_DIR/<page>-<light|dark>-<fa|en>-<mobile|desktop>.png (390x844 and 1280x800, 3 s after content loads),
rewards-redeem-* (confirm sheet, mobile), pickup-done-* (success sheet), home-*-narrow (320x640 tab bar),
and for light/fa one real redeem: rewards-code-* (code sheet) and rewards-mycodes-* (the saved-codes list); OUT_DIR/issues.json:
console errors/warnings, exceptions, CSP/audit issues, failed or >=400 requests, horizontal overflow.
The pickup step creates 2 pickups per run (the API allows 5 a day) and the redeem spends points, so point it at a
throwaway stack. Needs the stdlib and `websockets` (not in the requirements files: `pip install websockets` into the venv).
"""
import argparse, asyncio, base64, itertools, json, re, shutil, socket, subprocess, tempfile, time, urllib.request
from collections import defaultdict
from pathlib import Path

try:
    import websockets
except ImportError:
    raise SystemExit("needs websockets: backend/.venv/bin/pip install websockets")

PAGES = {"home": "/", "pickup": "/pickup", "rewards": "/rewards", "missions": "/missions", "activity": "/activity", "city": "/city"}
SIZES = {"mobile": (390, 844), "desktop": (1280, 800)}
NARROW = (320, 640)  # smallest phone width the tab bar must fit
BAD = {"error", "warning", "assert"}


class Cdp:
    def __init__(self, ws):
        self.ws, self.ids, self.waiting, self.events = ws, itertools.count(1), {}, []

    async def pump(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if "id" in m:
                self.waiting.pop(m["id"]).set_result(m)
            else:
                self.events.append(m)

    async def send(self, method, **params):
        i = next(self.ids)
        fut = self.waiting[i] = asyncio.get_running_loop().create_future()
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        m = await fut
        if "error" in m:
            raise RuntimeError(f"{method}: {m['error']}")
        return m["result"]

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True)
        return r["result"].get("value")

    async def wait_event(self, name, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if any(e["method"] == name for e in self.events):
                return
            await asyncio.sleep(0.1)


def problems(events):
    """Turn raw CDP events into (kind, text) pairs worth reporting."""
    urls, out = {}, []
    for e in events:
        m, p = e["method"], e["params"]
        if m == "Network.requestWillBeSent":
            urls[p["requestId"]] = p["request"]["url"]
        elif m == "Runtime.consoleAPICalled" and p["type"] in BAD:
            out.append(("console." + p["type"], " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])[:300]))
        elif m == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            out.append(("exception", (d.get("exception", {}).get("description") or d["text"])[:300]))
        elif m == "Log.entryAdded" and p["entry"]["level"] in BAD:
            out.append(("log." + p["entry"]["source"], f'{p["entry"]["text"]} {p["entry"].get("url", "")}'[:300]))
        elif m == "Audits.issueAdded":
            ids = re.compile(r'"(violatingNodeId|scriptId)": "?\d+"?,? ?')  # per-load ids would make every report look distinct
            out.append(("audit", f'{p["issue"]["code"]} {ids.sub("", json.dumps(p["issue"]["details"]))[:240]}'))
        elif m == "Network.loadingFailed" and not p.get("canceled"):
            out.append(("request.failed", f'{p["errorText"]} {urls.get(p["requestId"], "")}'))
        elif m == "Network.responseReceived" and p["response"]["status"] >= 400:
            out.append(("request.http", f'{p["response"]["status"]} {p["response"]["url"]}'))
    return out


async def run(base, out, chrome):
    out.mkdir(parents=True, exist_ok=True)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    prof = tempfile.mkdtemp(prefix="shots-")
    proc = subprocess.Popen([chrome, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--no-first-run",
                             "--disable-gpu", "--disable-dev-shm-usage", "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen = defaultdict(set)  # (kind, text) -> labels where it showed up
    try:
        for _ in range(100):
            try:
                tab = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
                break
            except Exception:
                await asyncio.sleep(0.2)
        else:
            raise SystemExit(f"chrome ({chrome}) exposed no page tab on port {port}")
        async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None, ping_interval=None) as ws:
            c = Cdp(ws)
            pump = asyncio.create_task(c.pump())
            for d in ("Page", "Runtime", "Log", "Network", "Audits"):
                await c.send(d + ".enable")

            async def setup(theme, lang, size):
                w, h = NARROW if size == "narrow" else SIZES[size]
                await c.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=size == "mobile")
                await c.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": theme}])
                if lang == "en":
                    await c.send("Network.setCookie", name="lang", value="en", url=base)
                else:
                    await c.send("Network.deleteCookies", name="lang", url=base)

            async def load(path):
                c.events.clear()
                await c.send("Page.navigate", url=base + path)
                await c.wait_event("Page.loadEventFired")
                for _ in range(100):  # skeletons gone = data is in; then let entrance animations finish
                    if await c.js("!document.querySelector('.skeleton')"):
                        break
                    await asyncio.sleep(0.15)
                await asyncio.sleep(3)

            async def shot(name):
                data = (await c.send("Page.captureScreenshot", format="png"))["data"]
                (out / f"{name}.png").write_bytes(base64.b64decode(data))

            def note(label):
                for k, t in problems(c.events):
                    seen[(k, t)].add(label)

            for theme in ("light", "dark"):
                for lang in ("fa", "en"):
                    for size in SIZES:
                        await setup(theme, lang, size)
                        for page, path in PAGES.items():
                            name = f"{page}-{theme}-{lang}-{size}"
                            await load(path)
                            await shot(name)
                            wide = await c.js("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&!e.closest('[class*=overflow-x-auto]')).slice(0,3).map(e=>e.tagName+'.'+e.className)")
                            if await c.js("document.documentElement.scrollWidth>innerWidth"):
                                seen[("overflow", f"scrollWidth>innerWidth; wide: {wide}")].add(name)
                            note(name)
                    # sheets: redeem on every theme/lang (mobile); pickup success twice (see docstring)
                    await setup(theme, lang, "mobile")
                    name = f"rewards-redeem-{theme}-{lang}-mobile"
                    await load("/rewards")
                    await c.js("document.querySelector('article button:not([disabled])').click()")
                    await asyncio.sleep(1.2)
                    await shot(name)
                    note(name)
                    if (theme, lang) == ("light", "fa"):  # spend once: the code sheet, then the code kept under "my codes"
                        await c.js("document.querySelector('dialog[open] .btn-primary').click()")
                        await asyncio.sleep(2)
                        await shot(f"rewards-code-{theme}-{lang}-mobile")
                        await c.js("document.querySelector('dialog[open] .btn-primary').click()")
                        await asyncio.sleep(1.2)
                        await shot(f"rewards-mycodes-{theme}-{lang}-mobile")
                        note(f"rewards-code-{theme}-{lang}-mobile")
                    await setup(theme, lang, "narrow")
                    await load("/")
                    await shot(f"home-{theme}-{lang}-narrow")
                    note(f"home-{theme}-{lang}-narrow")
                    if (theme, lang) in (("light", "fa"), ("dark", "en")):
                        size = "mobile" if theme == "light" else "desktop"
                        await setup(theme, lang, size)
                        name = f"pickup-done-{theme}-{lang}-{size}"
                        await load("/pickup")
                        await c.js("""document.querySelector('.chip button.block').click();
                            const a=document.querySelector('textarea'); if(!a.value){Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(a,'Tehran, Valiasr St');a.dispatchEvent(new Event('input',{bubbles:true}))}""")
                        await asyncio.sleep(0.5)
                        await c.js("[...document.querySelectorAll('aside .btn-primary')].find(b=>b.offsetParent&&!b.disabled).click()")
                        await asyncio.sleep(1.5)
                        await shot(name)
                        note(name)
            pump.cancel()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)
    rows = [{"kind": k, "text": t, "seen_on": sorted(v)} for (k, t), v in sorted(seen.items())]
    (out / "issues.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"{len(list(out.glob('*.png')))} screenshots, {len(rows)} distinct issues -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="frontend base URL, e.g. http://127.0.0.1:3126")
    ap.add_argument("out", type=Path, help="output directory for the PNGs and issues.json")
    ap.add_argument("--chrome", default="/usr/bin/google-chrome", help="Chrome or Chromium binary")
    a = ap.parse_args()
    asyncio.run(run(a.base.rstrip("/"), a.out, a.chrome))

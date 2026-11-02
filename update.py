"""Собирает VLESS-ключи из sources.txt, проверяет доступность и пишет keys.txt, sub.txt, README.md."""
import base64
import concurrent.futures as cf
import datetime as dt
import os
import socket
import urllib.parse
import urllib.request

BOT = os.getenv("BOT", "@vless_bounty_bot")
CHANNEL = os.getenv("CHANNEL", "@bounty_configs")
MAX_KEYS = int(os.getenv("MAX_KEYS", "200"))
TIMEOUT = 3
PROTOCOLS = ("vless://", "trojan://", "ss://", "hysteria2://", "hy2://")
REPO = os.getenv("GITHUB_REPOSITORY", "OWNER/REPO")
BRANCH = os.getenv("GITHUB_REF_NAME", "main")


def read_sources() -> list[str]:
    lines = []
    with open("sources.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def decode_maybe_b64(text: str) -> str:
    if any(p in text for p in PROTOCOLS):
        return text
    try:
        padded = text.strip() + "=" * (-len(text.strip()) % 4)
        return base64.b64decode(padded).decode("utf-8", "ignore")
    except Exception:
        return ""


def fetch(url: str) -> list[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[!] {url}: {e}")
        return []
    return [l.strip() for l in decode_maybe_b64(text).splitlines() if l.strip().startswith(PROTOCOLS)]


def collect() -> list[str]:
    keys = []
    for src in read_sources():
        if src.startswith(PROTOCOLS):
            keys.append(src)
        elif src.startswith(("http://", "https://")):
            keys += fetch(src)
    # дедуп по всему, кроме имени после #
    seen, uniq = set(), []
    for k in keys:
        base = k.split("#", 1)[0]
        if base not in seen:
            seen.add(base)
            uniq.append(base)
    return uniq


def host_port(key: str):
    try:
        u = urllib.parse.urlsplit(key)
        return u.hostname, u.port or 443
    except ValueError:
        return None, None


def alive(key: str) -> bool:
    host, port = host_port(key)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True
    except OSError:
        return False


def rename(key: str, i: int) -> str:
    name = f"🔑 {i:03d} | Ещё ключи в TG {BOT}"
    return f"{key}#{urllib.parse.quote(name)}"


def main() -> None:
    keys = collect()
    print(f"Собрано уникальных: {len(keys)}")
    with cf.ThreadPoolExecutor(64) as ex:
        ok = [k for k, a in zip(keys, ex.map(alive, keys)) if a][:MAX_KEYS]
    print(f"Живых: {len(ok)}")
    final = [rename(k, i) for i, k in enumerate(ok, 1)]

    body = "\n".join(final) + ("\n" if final else "")
    old = open("keys.txt", encoding="utf-8").read() if os.path.exists("keys.txt") else None
    readme_ok = os.path.exists("README.md") and f"/{REPO}/" in open("README.md", encoding="utf-8").read()
    if old == body and readme_ok:
        print("Ключи не изменились")
        return
    open("keys.txt", "w", encoding="utf-8").write(body)
    open("sub.txt", "w", encoding="utf-8").write(base64.b64encode(body.encode()).decode())

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%d.%m.%Y %H:%M МСК")
    raw = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
    tpl = open("README.template.md", encoding="utf-8").read()
    readme = (
        tpl.replace("{{BOT}}", BOT)
        .replace("{{BOT_URL}}", f"https://t.me/{BOT.lstrip('@')}")
        .replace("{{CHANNEL}}", CHANNEL)
        .replace("{{CHANNEL_URL}}", f"https://t.me/{CHANNEL.lstrip('@')}")
        .replace("{{COUNT}}", str(len(final)))
        .replace("{{UPDATED}}", now)
        .replace("{{SUB_URL}}", f"{raw}/sub.txt")
        .replace("{{KEYS_URL}}", f"{raw}/keys.txt")
    )
    open("README.md", "w", encoding="utf-8").write(readme)
    print("Обновлено")


if __name__ == "__main__":
    main()

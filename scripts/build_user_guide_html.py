"""Build docs/USER_GUIDE.html from docs/USER_GUIDE.md.

The Markdown file is the source; the HTML is generated so the two never drift.
Screenshots live in docs/images/user-guide/ and are referenced relatively, so
open the HTML from a checkout (or the docs folder) and the images load.

    uv run --with markdown python scripts/build_user_guide_html.py

Links to other documents in the repository point at GitHub, because the other
guides are Markdown and a browser would show them as plain text.
"""
from __future__ import annotations

import argparse
import html
import re
import unicodedata
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "USER_GUIDE.md"
OUT = ROOT / "docs" / "USER_GUIDE.html"
REPO = "https://github.com/mkashyap00/retirement-optimizer/blob/main"


def github_slug(value: str, separator: str = "-") -> str:
    """GitHub's heading anchors: lowercase, punctuation dropped, spaces to
    hyphens. Keeps every existing `#anchor` link in the guide working."""
    value = unicodedata.normalize("NFKC", html.unescape(value)).strip().lower()
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^\w\- ]", "", value)
    return value.replace(" ", separator)


def rewrite_links(body: str) -> str:
    """Point links to other repository files at GitHub; leave anchors,
    images and absolute URLs alone."""
    def fix(m: re.Match[str]) -> str:
        href = m.group(1)
        if href.startswith(("http:", "https:", "mailto:", "#", "images/")):
            return m.group(0)
        path, _, frag = href.partition("#")
        target = (Path("docs") / path).as_posix()
        target = re.sub(r"[^/]+/\.\./", "", target)  # docs/../LICENSE -> LICENSE
        url = f"{REPO}/{target}" + (f"#{frag}" if frag else "")
        return f'href="{url}"'
    return re.sub(r'href="([^"]+)"', fix, body)


def figures(body: str) -> str:
    """An image paragraph followed by an italic caption becomes a <figure>;
    the image links to its full-size file."""
    pat = re.compile(
        r'<p><img alt="([^"]*)" src="([^"]+)" ?/?>\s*(?:<br ?/?>)?\s*<em>(.*?)</em></p>', re.S
    )
    return pat.sub(
        lambda m: (
            f'<figure><a href="{m.group(2)}" target="_blank" rel="noopener">'
            f'<img alt="{m.group(1)}" src="{m.group(2)}" loading="lazy"></a>'
            f"<figcaption>{m.group(3)}</figcaption></figure>"
        ),
        body,
    )


CSS = """
:root{--bg:#F3EFE4;--paper:#FBFAF5;--ink:#1F2A2E;--muted:#55656A;--green:#0B4F3C;
--gold:#C29A3F;--line:#DED8C8;--code:#EFEADD;--note:#FFF8E6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121A18;--paper:#18221F;
--ink:#E6E2D6;--muted:#A3B0AB;--green:#7CC7A8;--gold:#D9B25E;--line:#2D3A36;--code:#22302C;
--note:#2A2717}}
:root[data-theme="dark"]{--bg:#121A18;--paper:#18221F;--ink:#E6E2D6;--muted:#A3B0AB;
--green:#7CC7A8;
--gold:#D9B25E;--line:#2D3A36;--code:#22302C;--note:#2A2717}
*{box-sizing:border-box}
html{scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 "Manrope","IBM Plex Sans",system-ui,sans-serif}
.layout{display:grid;grid-template-columns:280px minmax(0,1fr);max-width:1280px;margin:0 auto;
gap:40px;padding:32px 24px}
nav.toc{position:sticky;top:24px;align-self:start;max-height:calc(100vh - 48px);overflow:auto;
font-size:14px}
nav.toc .brand{font-weight:700;color:var(--green);font-size:18px;
border-left:4px solid var(--gold);padding-left:10px;margin-bottom:16px}
nav.toc ul{list-style:none;margin:0;padding-left:0}
nav.toc ul ul{padding-left:14px;margin:2px 0 6px}
nav.toc a{color:var(--muted);text-decoration:none;display:block;padding:2px 0}
nav.toc a:hover{color:var(--green)}
main{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:40px 56px;
min-width:0}
h1{font-size:34px;color:var(--green);border-left:5px solid var(--gold);padding-left:14px;
margin-top:0;line-height:1.2}
h2{font-size:26px;color:var(--green);margin-top:56px;padding-top:12px;
border-top:1px solid var(--line)}
h3{font-size:20px;color:var(--green);margin-top:36px}
h4{font-size:17px;margin-top:28px}
a{color:var(--green)}
table{border-collapse:collapse;width:100%;margin:16px 0;font-size:14.5px;display:block;
overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:var(--code);font-weight:600}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em}
pre{background:var(--code);padding:14px;border-radius:8px;overflow:auto}
pre code{background:none;padding:0}
blockquote{margin:20px 0;padding:14px 20px;background:var(--note);
border-left:4px solid var(--gold);border-radius:6px}
blockquote p:first-child{margin-top:0} blockquote p:last-child{margin-bottom:0}
figure{margin:24px 0 32px}
figure img{width:100%;height:auto;border:1px solid var(--line);border-radius:10px;
box-shadow:0 2px 10px rgba(0,0,0,.08);display:block}
figcaption{color:var(--muted);font-size:14px;margin-top:8px;font-style:italic}
hr{border:0;border-top:1px solid var(--line);margin:40px 0}
.meta{color:var(--muted);font-size:13px;margin-top:48px}
@media (max-width:900px){.layout{grid-template-columns:1fr;padding:16px}nav.toc{position:static;
max-height:none}
main{padding:24px 16px}}
@media print{nav.toc{display:none}.layout{display:block}main{border:0}}
"""


def build(src: Path, out: Path) -> None:
    text = src.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": github_slug, "toc_depth": "2-3"}},
        output_format="html5",
    )
    body = md.convert(text)
    body = figures(rewrite_links(body))
    toc = md.toc  # type: ignore[attr-defined]
    title = "Retirement Optimizer User Guide"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>User Guide</title>
<style>{CSS}</style></head>
<body><div class="layout">
<nav class="toc" aria-label="Contents"><div class="brand">{title}</div>{toc}</nav>
<main>{body}
<p class="meta">Generated from docs/USER_GUIDE.md on {date.today():%d %B %Y} by
scripts/build_user_guide_html.py. Edit the Markdown file and re-run the script.</p>
</main></div></body></html>
"""
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(page) // 1024} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    build(a.src, a.out)


if __name__ == "__main__":
    main()

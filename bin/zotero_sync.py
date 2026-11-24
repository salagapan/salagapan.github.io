#!/usr/bin/env python3
"""Rebuild _bibliography/papers.bib and other.bib from a Zotero collection.

Run by .github/workflows/zotero-sync.yml. Can also be run locally:

    ZOTERO_USER_ID=5299189 ZOTERO_COLLECTION=8HPPG5Y4 python3 bin/zotero_sync.py

Environment:
    ZOTERO_USER_ID     Zotero user ID (numeric)
    ZOTERO_COLLECTION  collection key (8 characters, from the collection URL)
    ZOTERO_API_KEY     optional; needed unless the library is public
    FORCE              set to 1 to write even if the item count dropped sharply

How items are sorted into the two files:
    other.bib   Zotero item types in OTHER_TYPES (posters/presentations, patents,
                blog/magazine/newspaper pieces, web pages), or any item tagged
                "website-other".
    papers.bib  everything else (journal articles, conference papers, preprints,
                theses, book chapters), or any item tagged "website-main".
    (skipped)   items tagged "website-hide".

Badges, "selected", and links come from _data/bib_extras.yml.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPERS = os.path.join(ROOT, "_bibliography", "papers.bib")
OTHER = os.path.join(ROOT, "_bibliography", "other.bib")
EXTRAS = os.path.join(ROOT, "_data", "bib_extras.yml")

OTHER_TYPES = {
    "presentation", "patent", "blogPost", "magazineArticle", "newspaperArticle",
    "webpage", "podcast", "videoRecording", "interview", "forumPost",
}
SKIP_TYPES = {"note", "attachment", "annotation"}
DROP_FIELDS = {"file", "urldate", "language", "keywords", "shorttitle"}
SITE_FIELDS = ["abbr", "selected", "html", "pdf", "code", "arxiv", "website", "slides", "poster", "video", "preview"]
TEXT_FIXES = {"ӧ": "ö", "Ӧ": "Ö"}  # Cyrillic look-alikes that sneak in via copy/paste


def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"::warning::{msg}", flush=True)


def fetch_items(user_id, collection, api_key):
    base = (
        f"https://api.zotero.org/users/{user_id}/collections/{collection}/items/top"
        "?format=json&include=bibtex,data&limit=100"
    )
    headers = {"Zotero-API-Version": "3"}
    if api_key:
        headers["Zotero-API-Key"] = api_key
    items, start = [], 0
    while True:
        req = urllib.request.Request(f"{base}&start={start}", headers=headers)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    total = int(r.headers.get("Total-Results", "0"))
                    batch = json.load(r)
                    backoff = r.headers.get("Backoff")
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    sys.exit(
                        f"Zotero returned {e.code}. Check ZOTERO_USER_ID / ZOTERO_COLLECTION, and that "
                        "ZOTERO_API_KEY is set (with library read access) if the library is not public."
                    )
                if attempt == 3:
                    raise
                time.sleep(int(e.headers.get("Retry-After", "5")))
        items.extend(batch)
        start += len(batch)
        if backoff:
            time.sleep(int(backoff))
        if not batch or start >= total:
            return items


def norm(s):
    return re.sub(r"[{}]", "", s or "").strip().lower()


def entry_key(bib):
    m = re.match(r"\s*@\w+\s*\{\s*([^,\s]+)\s*,", bib)
    return m.group(1) if m else None


def set_key(bib, key):
    return re.sub(r"(@\w+\s*\{\s*)[^,\s]+(\s*,)", lambda m: m.group(1) + key + m.group(2), bib, count=1)


def field(bib, name):
    m = re.search(rf"^\s*{name}\s*=\s*\{{(.*)\}},?\s*$", bib, re.M | re.I)
    return m.group(1) if m else None


def drop_fields(bib, names):
    out = [l for l in bib.split("\n") if not (re.match(r"\s*(\w+)\s*=", l) and re.match(r"\s*(\w+)\s*=", l).group(1).lower() in names)]
    return "\n".join(out)


def add_fields(bib, kv):
    body = bib.rstrip()
    assert body.endswith("}"), bib
    body = body[:-1].rstrip()
    if not body.endswith(","):
        body += ","
    for k, v in kv.items():
        v = "true" if v is True else str(v)
        body += f"\n\t{k} = {{{v}}},"
    return body + "\n}"


def sort_key(item):
    d = (item.get("meta", {}).get("parsedDate") or "") + "-00-00"
    y, m, dd = (d.split("-") + ["00", "00"])[:3]
    return (y if y.isdigit() else "0000", m.zfill(2), dd.zfill(2), item["data"].get("title", ""))


def existing_count(path):
    try:
        return len(re.findall(r"^@", open(path, encoding="utf-8").read(), re.M))
    except FileNotFoundError:
        return 0


def main():
    user_id = os.environ.get("ZOTERO_USER_ID", "").strip()
    collection = os.environ.get("ZOTERO_COLLECTION", "").strip()
    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    if not user_id or not collection:
        sys.exit("ZOTERO_USER_ID and ZOTERO_COLLECTION must be set.")

    extras = yaml.safe_load(open(EXTRAS, encoding="utf-8")) or {}
    venues = {norm(k): v for k, v in (extras.get("venues") or {}).items()}
    type_badges = extras.get("item_types") or {}
    per_entry = extras.get("entries") or {}

    items = fetch_items(user_id, collection, api_key)
    log(f"Fetched {len(items)} top-level items from Zotero.")
    if not items:
        sys.exit("No items returned; refusing to overwrite the bibliography.")

    items.sort(key=sort_key, reverse=True)
    papers, other, seen = [], [], {}
    for it in items:
        data = it.get("data", {})
        itype = data.get("itemType", "")
        tags = {t.get("tag", "").strip().lower() for t in data.get("tags", [])}
        bib = (it.get("bibtex") or "").strip()
        if itype in SKIP_TYPES or "website-hide" in tags or not bib:
            continue
        for a, b in TEXT_FIXES.items():
            bib = bib.replace(a, b)
        bib = drop_fields(bib, DROP_FIELDS)

        key = entry_key(bib)
        if key is None:
            warn(f"Could not read a BibTeX key for '{data.get('title')}'; skipped.")
            continue
        if key in seen:
            n = 2
            while f"{key}-{n}" in seen:
                n += 1
            warn(f"Duplicate key '{key}' ('{data.get('title')}'); using '{key}-{n}'. Is this a duplicate item in Zotero?")
            key = f"{key}-{n}"
            bib = set_key(bib, key)
        seen[key] = True

        is_other = ("website-other" in tags or itype in OTHER_TYPES) and "website-main" not in tags
        conf = dict(per_entry.get(key) or {})
        add = {}
        abbr = conf.pop("abbr", None)
        if not abbr:
            for cand in (field(bib, "journal"), field(bib, "booktitle"), data.get("repository"), data.get("publicationTitle")):
                if cand and norm(cand) in venues:
                    abbr = venues[norm(cand)]
                    break
        abbr = abbr or type_badges.get(itype)
        if abbr:
            add["abbr"] = abbr
        if not is_other:
            add["bibtex_show"] = True
        for f in SITE_FIELDS:
            if f in conf and f != "abbr" and field(bib, f) is None:
                add[f] = conf[f]
        bib = add_fields(bib, add)
        (other if is_other else papers).append(bib)

    for k in per_entry:
        if k not in seen:
            warn(f"_data/bib_extras.yml entry '{k}' matches no Zotero item (title/year edited, or item removed?).")

    old = existing_count(PAPERS) + existing_count(OTHER)
    new = len(papers) + len(other)
    if old and new < 0.5 * old and os.environ.get("FORCE") != "1":
        sys.exit(f"Item count dropped from {old} to {new}; not writing. Re-run with FORCE=1 if this is intended.")

    header = "---\n---\n\n"
    for path, entries in ((PAPERS, papers), (OTHER, other)):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n\n".join(entries) + "\n")
    log(f"Wrote {len(papers)} entries to papers.bib and {len(other)} to other.bib.")


if __name__ == "__main__":
    main()

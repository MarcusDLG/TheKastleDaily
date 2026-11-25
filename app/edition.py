"""Build an EPUB from an editorial plan and reviewed, source-backed drafts."""

import argparse
import hashlib
import json
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""

CSS = """
body { margin: 0 4%; line-height: 1.45; }
h1 { font-family: serif; line-height: 1.17; font-size: 1.6em; }
.story-header { break-inside: avoid; page-break-inside: avoid; }
.story-header h1, .story-header p { break-after: avoid; page-break-after: avoid; }
figure { margin: .8em 0; }
figure img, .cover img { display: block; height: auto; max-width: 100%; margin: auto; }
figure img { width: 82%; }
.cover { text-align: center; }
.note { font-size: .85em; }
li { margin-bottom: .35em; }
"""


def xhtml(title, body):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
lang="en" xml:lang="en">
<head><title>{escape(title)}</title><link rel="stylesheet" href="edition.css"/></head>
<body>{body}</body></html>
"""


def link(url, label):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(char.isspace() for char in url)
    ):
        raise ValueError("Source links must be absolute HTTP or HTTPS URLs")
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def read_photo(directory, name):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Image paths must stay inside the draft directory")
    with path.open("rb") as photo:
        payload = photo.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("Each image must be 4 MiB or smaller")
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg", payload
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png", payload
    raise ValueError("Images must be JPEG or PNG")


def story_body(selected, draft, photo_name):
    headline = draft["headline"].strip()
    paragraphs = [value.strip() for value in draft["paragraphs"] if value.strip()]
    if not headline or len(paragraphs) < 2:
        raise ValueError(
            "Each draft needs a headline and at least two nonempty paragraphs"
        )
    category = selected["category"].replace("_", " ").title()
    publisher = selected["publisher"]
    byline = f"{category} · {publisher}"
    if selected.get("archived"):
        byline += " · From the archive"
    opening = (
        f'<div class="story-header"><p class="note">{escape(byline)}</p>'
        f"<h1>{escape(headline)}</h1>"
    )
    if photo_name:
        photo = draft["photo"]
        opening += (
            f'<figure><img src="{photo_name}" alt="{escape(photo["alt"], quote=True)}"/>'
            f'<figcaption class="note">{escape(photo["credit"])}</figcaption></figure>'
        )
    body = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
    provenance = [link(selected["url"], publisher)]
    provenance.extend(
        link(source["url"], source["label"]) for source in draft.get("sources", [])
    )
    return xhtml(
        headline,
        opening
        + "</div>"
        + body
        + '<p class="note">Sources: '
        + ", ".join(provenance)
        + "</p>",
    )


def render_epub(plan, drafts, directory, output):
    edition_date = date.fromisoformat(plan["edition_date"])
    if plan["coverage_floor_met"] is not True:
        raise ValueError("Edition is missing its reserved Sim Racing or Maker story")
    selected = plan["stories"]
    if not selected or len(selected) > plan["target"]:
        raise ValueError("Edition has an invalid number of selected stories")
    identifiers = {item["article_id"] for item in selected}
    if len(identifiers) != len(selected) or not any(
        item.get("reserved") and item["category"] in {"sim_racing", "maker_radio"}
        for item in selected
    ):
        raise ValueError(
            "Plan must contain distinct articles and a valid reserved story"
        )

    by_id = {draft["article_id"]: draft for draft in drafts["stories"]}
    if len(by_id) != len(drafts["stories"]) or by_id.keys() != identifiers:
        raise ValueError(
            "Drafts must contain exactly one matching entry for each selected article"
        )

    title = f"The Kastle Daily | {edition_date.strftime('%B %d, %Y')}"
    if label := drafts.get("edition_label"):
        title += f" — {label.strip()}"
    manifest = []
    spine = []
    entries = {}
    toc = []

    def add(filename, content, media_type, *, properties="", reading_order=False):
        item_id = f"item-{len(manifest) + 1}"
        entries[filename] = content.encode() if isinstance(content, str) else content
        extra = f' properties="{properties}"' if properties else ""
        manifest.append(
            f'<item id="{item_id}" href="{filename}" media-type="{media_type}"{extra}/>'
        )
        if reading_order:
            spine.append(f'<itemref idref="{item_id}"/>')

    add("edition.css", CSS, "text/css")
    banner = f"<h1>The Kastle Daily</h1><p>{edition_date.strftime('%B %d, %Y')}</p>"
    if cover := drafts.get("cover"):
        suffix, media, payload = read_photo(directory, cover)
        add(f"cover.{suffix}", payload, media, properties="cover-image")
        banner = f'<img src="cover.{suffix}" alt="{escape(title, quote=True)}"/>'
    add(
        "cover.xhtml",
        xhtml(title, f'<div class="cover">{banner}</div>'),
        "application/xhtml+xml",
        reading_order=True,
    )
    add(
        "contents.xhtml",
        "",
        "application/xhtml+xml",
        properties="nav",
        reading_order=True,
    )
    for number, item in enumerate(selected, 1):
        draft = by_id[item["article_id"]]
        photo_name = None
        if photo := draft.get("photo"):
            suffix, media, payload = read_photo(directory, photo["file"])
            photo_name = f"photo-{number}.{suffix}"
            add(photo_name, payload, media)
        filename = f"story-{number}.xhtml"
        add(
            filename,
            story_body(item, draft, photo_name),
            "application/xhtml+xml",
            reading_order=True,
        )
        toc.append((filename, draft["headline"].strip()))

    rows = "".join(
        f"<li>{escape(key.replace('_', ' ').title())}: {value['selected']} of {value['target']}</li>"
        for key, value in plan["coverage"].items()
    )
    coverage = f"<h1>Edition coverage</h1><p>{len(selected)} of {plan['target']} stories.</p><ul>{rows}</ul>"
    add(
        "coverage.xhtml",
        xhtml("Edition coverage", coverage),
        "application/xhtml+xml",
        reading_order=True,
    )
    toc.append(("coverage.xhtml", "Edition coverage"))
    navigation = "".join(
        f'<li><a href="{filename}">{escape(label)}</a></li>' for filename, label in toc
    )
    entries["contents.xhtml"] = xhtml(
        "Contents", f'<nav epub:type="toc"><h1>Contents</h1><ol>{navigation}</ol></nav>'
    ).encode()

    digest = hashlib.sha256()
    for filename, payload in entries.items():
        digest.update(filename.encode())
        digest.update(hashlib.sha256(payload).digest())
    package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="edition-id"
xml:lang="en">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="edition-id">urn:sha256:{digest.hexdigest()}</dc:identifier>
<dc:title>{escape(title)}</dc:title><dc:creator>The Kastle Daily</dc:creator>
<dc:language>en</dc:language><dc:date>{edition_date}</dc:date>
<meta property="dcterms:modified">{edition_date}T00:00:00Z</meta>
</metadata><manifest>{"".join(manifest)}</manifest><spine>{"".join(spine)}</spine>
</package>"""

    def write(archive, filename, contents, compression=ZIP_DEFLATED):
        archive.writestr(ZipInfo(filename), contents, compress_type=compression)

    with ZipFile(output, "w") as archive:
        write(archive, "mimetype", "application/epub+zip", ZIP_STORED)
        write(archive, "META-INF/container.xml", CONTAINER)
        write(archive, "EPUB/package.opf", package)
        for filename, payload in entries.items():
            write(archive, f"EPUB/{filename}", payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".epub":
        parser.error("--out must end in .epub")
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        drafts = json.loads(args.drafts.read_text(encoding="utf-8"))
        render_epub(plan, drafts, args.drafts.parent, args.out)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Edition build failed: {error}\n")
    print(f"Rendered EPUB: {args.out}")


if __name__ == "__main__":
    main()

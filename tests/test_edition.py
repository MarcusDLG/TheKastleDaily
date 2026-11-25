import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

import pytest

from app.edition import read_photo, render_epub

FIXTURES = Path(__file__).parent / "fixtures" / "edition"


@pytest.fixture
def inputs():
    return tuple(
        json.loads((FIXTURES / filename).read_text())
        for filename in ("plan.json", "drafts.json")
    )


def test_offline_story_order_and_contents(tmp_path, inputs):
    output = tmp_path / "test.epub"
    render_epub(*inputs, FIXTURES, output)
    with ZipFile(output) as book:
        first = book.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == ZIP_STORED
        assert book.testzip() is None
        ns = {"o": "http://www.idpf.org/2007/opf"}
        package = ET.fromstring(book.read("EPUB/package.opf"))
        manifest = {
            item.get("id"): item.get("href")
            for item in package.findall(".//o:item", ns)
        }
        spine = [
            manifest[item.get("idref")] for item in package.findall(".//o:itemref", ns)
        ]
        assert spine == [
            "cover.xhtml",
            "contents.xhtml",
            "story-1.xhtml",
            "story-2.xhtml",
            "coverage.xhtml",
        ]
        assert b"the full story body" in book.read("EPUB/story-1.xhtml")
        assert b"project-notes" in book.read("EPUB/story-2.xhtml")
        assert b"story-2.xhtml" in book.read("EPUB/contents.xhtml")

    repeated = tmp_path / "again.epub"
    render_epub(*inputs, FIXTURES, repeated)
    assert repeated.read_bytes() == output.read_bytes()


def test_incomplete_draft_is_rejected(tmp_path, inputs):
    plan, drafts = inputs
    drafts["stories"].pop()
    with pytest.raises(ValueError, match="exactly one"):
        render_epub(plan, drafts, FIXTURES, tmp_path / "test.epub")


def test_missing_reserve_is_rejected(tmp_path, inputs):
    plan, drafts = inputs
    plan["coverage_floor_met"] = False
    with pytest.raises(ValueError, match="reserved"):
        render_epub(plan, drafts, FIXTURES, tmp_path / "test.epub")


def test_photo_cannot_escape_draft_directory(tmp_path):
    with pytest.raises(ValueError, match="inside the draft directory"):
        read_photo(tmp_path, "../secret.jpg")

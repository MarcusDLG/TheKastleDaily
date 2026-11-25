"""Operations dashboard — WEB_ADMIN.md phases 1 and 2.

Reads: editions, drafting-run detail, feed health, deliveries.
Writes (phase 2): feed management — add a source, flip approval state.
Stdlib http.server only; a fresh session per request keeps the page
live. Runs as an opt-in compose service (`profiles: [admin]`) — the
worker's no-ports posture is preserved. The process binds the container
interface; exposure is a host-side publish decision (`127.0.0.1:8080`
in the repo compose; the NAS overrides to the LAN).

Auth contract: when ADMIN_PASSWORD is set, HTTP Basic auth gates every
route except /healthz, and writes additionally require a per-process
form token (CSRF). When unset, reads stay open and every POST fails
closed with 403 — a passwordless deployment is read-only.
"""

import argparse
import base64
import hmac
import json
import os
import socket
from datetime import UTC, datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse
from uuid import UUID, uuid4

import yaml
from sqlalchemy import func, select

from app.models import (
    Article,
    Delivery,
    DeliveryAttempt,
    Edition,
    EditionStory,
    EditorialRun,
    EditorialStory,
    IngestionRun,
    Source,
)
from app.secrets import secret

PAGE_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; margin: 2rem auto;
       max-width: 60rem; padding: 0 1rem; color: #1a1a1a; }
.masthead { text-align: center; border-bottom: 3px double #333;
            padding-bottom: .5rem; }
.masthead h1 { font-variant: small-caps; letter-spacing: .08em;
               margin: 0; font-size: 2rem; }
.masthead .dateline { color: #555; font-size: .85rem; font-style: italic; }
h2 { font-variant: small-caps; border-bottom: 1px solid #999;
     font-size: 1.15rem; margin-top: 1.6rem; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th { text-align: left; border-bottom: 1px solid #333; padding: .3rem .5rem;
     font-variant: small-caps; font-weight: normal; }
td { padding: .3rem .5rem; border-bottom: 1px solid #ddd;
     vertical-align: top; }
.status { font-family: monospace; font-size: .82rem; }
.ok { color: #1a6b1a; } .warn { color: #8a5a00; } .bad { color: #a11; }
.muted { color: #666; font-size: .82rem; }
.reason { font-family: monospace; font-size: .78rem; white-space: pre-wrap;
          word-break: break-word; }
"""

STATUS_CLASS = {
    "validated": "ok", "smtp_accepted": "ok", "succeeded": "ok",
    "extracted": "ok", "approved": "ok", "draft": "muted",
    "pending": "warn", "sending": "warn", "running": "warn",
    "ambiguous": "warn", "failed": "bad", "disabled": "bad",
}


def _pill(status: str | None) -> str:
    text = escape(str(status) if status else "—")
    cls = STATUS_CLASS.get(status or "", "muted")
    return f'<span class="status {cls}">{text}</span>'


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


APPROVAL_STATES = ("pending", "approved", "disabled")
SOURCE_KINDS = ("rss", "youtube")


def editorial_categories(config_path="config/editorial.yaml") -> list[str]:
    """Valid feed categories — the genre weights in editorial config."""
    try:
        config = yaml.safe_load(open(config_path).read()) or {}
    except OSError:
        return []
    return sorted(config.get("weights", {}).keys())


def admin_credentials() -> tuple[str, str | None]:
    """(username, password); password None means writes stay disabled."""
    return (
        (secret("ADMIN_USERNAME") or "admin").strip() or "admin",
        secret("ADMIN_PASSWORD") or None,
    )


def add_source(session, fields: dict, categories: list) -> None:
    """Insert an approved feed. Raises ValueError on bad input."""
    endpoint = fields.get("endpoint", "").strip()
    publisher = fields.get("publisher", "").strip()
    category = fields.get("category", "").strip()
    kind = fields.get("kind", "rss").strip()
    note = fields.get("licensing_note", "").strip()
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("endpoint must be an http(s) URL")
    if not publisher:
        raise ValueError("publisher is required")
    if categories and category not in categories:
        raise ValueError(f"unknown category: {category}")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if session.scalar(
        select(func.count()).select_from(Source).where(Source.endpoint == endpoint)
    ):
        raise ValueError("endpoint already registered")
    session.add(
        Source(
            kind=kind,
            endpoint=endpoint,
            publisher=publisher,
            category=category,
            licensing_note=note or "Added via admin",
            approval="approved",
        )
    )


def set_source_state(session, source_id: str, approval: str) -> None:
    """Flip a feed's approval state. Raises ValueError on bad input."""
    if approval not in APPROVAL_STATES:
        raise ValueError(f"unknown approval state: {approval}")
    try:
        source = session.get(Source, UUID(source_id))
    except ValueError:
        source = None
    if source is None:
        raise ValueError("unknown source")
    source.approval = approval


def dashboard_data(session) -> dict:
    """Assemble the four dashboard sections from live rows."""
    editions = session.scalars(
        select(Edition).order_by(Edition.edition_date.desc()).limit(7)
    ).all()
    story_counts = dict(
        session.execute(
            select(EditionStory.edition_id, func.count()).group_by(
                EditionStory.edition_id
            )
        ).all()
    )
    deliveries_by_edition: dict = {}
    for delivery in session.scalars(
        select(Delivery).order_by(Delivery.created_at.desc()).limit(20)
    ):
        deliveries_by_edition.setdefault(delivery.edition_id, []).append(delivery)
    attempt_counts = dict(
        session.execute(
            select(DeliveryAttempt.delivery_id, func.count()).group_by(
                DeliveryAttempt.delivery_id
            )
        ).all()
    )

    run = session.scalars(
        select(EditorialRun).order_by(EditorialRun.created_at.desc()).limit(1)
    ).first()
    drafting = None
    if run is not None:
        reasons = []
        if run.error_detail:
            try:
                reasons = json.loads(run.error_detail)
            except ValueError:
                reasons = [{"rank": "?", "reason": run.error_detail}]
        drafting = {
            "run": run,
            "drafted": session.scalar(
                select(func.count())
                .select_from(EditorialStory)
                .where(EditorialStory.editorial_run_id == run.id)
            ),
            "reasons": reasons,
        }

    feeds = []
    for source in session.scalars(select(Source).order_by(Source.publisher)):
        recent = session.scalars(
            select(IngestionRun)
            .where(IngestionRun.source_id == source.id)
            .order_by(IngestionRun.created_at.desc())
            .limit(10)
        ).all()
        streak = 0
        for item in recent:
            if item.status == "failed":
                streak += 1
            else:
                break
        feeds.append({"source": source, "latest": recent[0] if recent else None,
                      "streak": streak})

    day_ago = datetime.now(UTC) - timedelta(hours=24)
    stats = {
        "articles_total": session.scalar(select(func.count()).select_from(Article)),
        "articles_24h": session.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.created_at >= day_ago)
        ),
        "sources_pending": session.scalar(
            select(func.count()).select_from(Source).where(
                Source.approval == "pending"
            )
        ),
    }
    return {
        "editions": editions,
        "story_counts": story_counts,
        "deliveries": deliveries_by_edition,
        "attempts": attempt_counts,
        "drafting": drafting,
        "feeds": feeds,
        "stats": stats,
        "generated_at": datetime.now(UTC),
    }


def render_html(
    data: dict, *, token: str, writable: bool, categories: list, flash=None
) -> str:
    stats = data["stats"]
    mode = "read + write" if writable else "read-only"
    rows = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>The Kastle Daily — Operations</title>",
        f"<style>{PAGE_CSS}</style></head><body>",
        "<div class='masthead'><h1>The Kastle Daily</h1>",
        f"<div class='dateline'>Operations desk — {mode} — generated "
        f"{_fmt_dt(data['generated_at'])} UTC · "
        f"{stats['articles_total']} articles ({stats['articles_24h']} in 24h) · "
        f"{stats['sources_pending']} feeds pending approval</div></div>",
    ]
    if flash:
        kind, message = flash
        cls = "ok" if kind == "ok" else "bad"
        rows.append(f"<p class='{cls}'>{escape(message)}</p>")
    rows.append(
        "<h2>Editions</h2><table><tr><th>Date</th><th>Status</th>"
        "<th>Stories</th><th>SHA-256</th><th>Delivery</th></tr>"
    )
    for edition in data["editions"]:
        sha = (edition.epub_sha256 or "—")[:12]
        deliveries = data["deliveries"].get(edition.id, [])
        delivery_cell = ", ".join(
            f"{escape(d.destination_key)} {_pill(d.status)}"
            f" <span class='muted'>({data['attempts'].get(d.id, 0)} tries)</span>"
            for d in deliveries
        ) or "<span class='muted'>—</span>"
        rows.append(
            f"<tr><td>{edition.edition_date}</td><td>{_pill(edition.status)}</td>"
            f"<td>{data['story_counts'].get(edition.id, 0)}</td>"
            f"<td class='status muted'>{escape(sha)}</td>"
            f"<td>{delivery_cell}</td></tr>"
        )
    rows.append("</table>")

    drafting = data["drafting"]
    if drafting:
        run = drafting["run"]
        rows.append(
            f"<h2>Latest drafting run</h2><table>"
            f"<tr><td>Edition</td><td>{run.edition_date}</td></tr>"
            f"<tr><td>Model</td><td class='status'>{escape(run.model)}</td></tr>"
            f"<tr><td>Status</td><td>{_pill(run.status)}</td></tr>"
            f"<tr><td>Drafted / blocked</td><td>{drafting['drafted']} / "
            f"{len(drafting['reasons'])}</td></tr>"
            f"<tr><td>Cost</td><td class='status'>"
            f"${run.estimated_cost_usd} "
            f"<span class='muted'>({run.input_tokens}+{run.output_tokens} "
            f"tokens)</span></td></tr></table>"
        )
        if drafting["reasons"]:
            rows.append("<h2>Blocked stories</h2><table>"
                        "<tr><th>Rank</th><th>Reason</th></tr>")
            for reason in drafting["reasons"]:
                rows.append(
                    f"<tr><td>{escape(str(reason.get('rank', '?')))}</td>"
                    f"<td class='reason'>{escape(str(reason.get('reason', '')))}"
                    f"</td></tr>"
                )
            rows.append("</table>")

    actions = "<th>Actions</th>" if writable else ""
    rows.append(
        "<h2>Feed health</h2><table><tr><th>Publisher</th><th>Category</th>"
        "<th>Approval</th><th>Last ingest</th><th>Detail</th>"
        f"<th>Fail streak</th>{actions}</tr>"
    )
    for feed in data["feeds"]:
        source, latest = feed["source"], feed["latest"]
        streak = feed["streak"]
        streak_cell = (
            f'<span class="status bad">{streak}</span>' if streak
            else '<span class="muted">0</span>'
        )
        action_cell = ""
        if writable:
            buttons = []
            for state in APPROVAL_STATES:
                if state != source.approval:
                    buttons.append(
                        "<form method='post' action='/sources/state' "
                        "style='display:inline'>"
                        f"<input type='hidden' name='token' value='{token}'>"
                        f"<input type='hidden' name='id' value='{source.id}'>"
                        f"<input type='hidden' name='approval' value='{state}'>"
                        f"<button type='submit'>{state}</button></form>"
                    )
            action_cell = "<td>" + " ".join(buttons) + "</td>"
        rows.append(
            f"<tr><td>{escape(source.publisher)}</td>"
            f"<td class='muted'>{escape(source.category)}</td>"
            f"<td>{_pill(source.approval)}</td>"
            f"<td>{_pill(latest.status if latest else None)} "
            f"<span class='muted'>{_fmt_dt(latest.finished_at if latest else None)}"
            f"</span></td>"
            f"<td class='reason'>{escape(latest.error_code or '—') if latest else '—'}"
            f"</td><td>{streak_cell}</td>{action_cell}</tr>"
        )
    rows.append("</table>")
    if writable:
        options = "".join(
            f"<option value='{escape(c)}'>{escape(c)}</option>" for c in categories
        )
        kinds = "".join(
            f"<option value='{k}'>{k}</option>" for k in SOURCE_KINDS
        )
        rows.append(
            "<h2>Add feed</h2>"
            "<form method='post' action='/sources/add'>"
            f"<input type='hidden' name='token' value='{token}'>"
            "<table>"
            "<tr><td>Endpoint</td><td><input name='endpoint' size='48' "
            "placeholder='https://…/feed.xml' required></td></tr>"
            "<tr><td>Publisher</td><td><input name='publisher' required></td></tr>"
            "<tr><td>Category</td><td><select name='category'>"
            f"{options}</select></td></tr>"
            "<tr><td>Kind</td><td><select name='kind'>"
            f"{kinds}</select></td></tr>"
            "<tr><td>Licensing note</td><td><input name='licensing_note'>"
            "</td></tr>"
            "<tr><td></td><td><button type='submit'>Add feed</button></td></tr>"
            "</table></form>"
        )
    else:
        rows.append(
            "<p class='muted'>Set ADMIN_PASSWORD to enable feed management."
            "</p>"
        )
    rows.append("<p class='muted'>Refresh: reload the page.</p></body></html>")
    return "".join(rows)


def make_handler(factory, *, token: str, username: str, password: str | None,
                 categories: list):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _authed(self) -> bool:
            if password is None:
                return False
            header = self.headers.get("Authorization", "")
            if not header.startswith("Basic "):
                return False
            try:
                decoded = base64.b64decode(header[6:]).decode()
            except ValueError:
                return False
            user, _, pw = decoded.partition(":")
            return hmac.compare_digest(user, username) and hmac.compare_digest(
                pw, password
            )

        def _unauthorized(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="kastle"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _redirect(self, kind: str, message: str):
            self.send_response(303)
            self.send_header("Location", f"/?{kind}={quote(message)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _fields(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 8192:
                return {}
            body = self.rfile.read(length).decode(errors="replace")
            return {
                key: values[0]
                for key, values in parse_qs(body).items()
                if values
            }

        def _writable(self, fields: dict) -> bool:
            """Auth + CSRF gate for every write."""
            if not self._authed():
                self._unauthorized()
                return False
            supplied = fields.get("token", "")
            if not supplied or not hmac.compare_digest(supplied, token):
                self._respond(403, "text/plain", b"bad form token")
                return False
            return True

        def do_GET(self):
            if self.path == "/healthz":
                self._respond(200, "application/json", b'{"status":"ok"}')
                return
            if password is not None and not self._authed():
                self._unauthorized()
                return
            parsed = urlparse(self.path)
            if parsed.path not in ("/", "/index.html"):
                self._respond(404, "text/plain", b"not found")
                return
            params = parse_qs(parsed.query)
            flash = None
            for kind in ("ok", "err"):
                if params.get(kind):
                    flash = (kind, params[kind][0])
            with factory() as session:
                body = render_html(
                    dashboard_data(session),
                    token=token,
                    writable=password is not None,
                    categories=categories,
                    flash=flash,
                ).encode()
            self._respond(200, "text/html; charset=utf-8", body)

        def do_POST(self):
            if password is None:
                self._respond(
                    403, "text/plain",
                    b"writes disabled - set ADMIN_PASSWORD"
                )
                return
            fields = self._fields()
            if not self._writable(fields):
                return
            path = urlparse(self.path).path
            try:
                with factory() as session:
                    if path == "/sources/add":
                        add_source(session, fields, categories)
                        session.commit()
                        self._redirect("ok", "feed added")
                    elif path == "/sources/state":
                        set_source_state(
                            session, fields.get("id", ""),
                            fields.get("approval", ""),
                        )
                        session.commit()
                        self._redirect("ok", "feed updated")
                    else:
                        self._respond(404, "text/plain", b"not found")
            except ValueError as error:
                self._redirect("err", str(error))

        def _respond(self, code, content_type, body):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return DashboardHandler


def container_host() -> str:
    """The container's own interface — narrower than a wildcard bind:
    published ports reach it while the container's loopback stays
    unexposed. Falls back to the wildcard address where the hostname
    does not resolve (bare-metal dev runs)."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("ADMIN_PORT", "8080"))
    )
    parser.add_argument("--host", default=container_host())
    args = parser.parse_args(argv)

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from app.database import database_path, session_factory

    # NullPool: each request's session opens and closes its connection on the
    # same handler thread — pooled connections can't cross threads.
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path()}",
        poolclass=NullPool,
        hide_parameters=True,
    )
    username, password = admin_credentials()
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            session_factory(engine),
            token=uuid4().hex,
            username=username,
            password=password,
            categories=editorial_categories(),
        ),
    )
    mode = "read+write" if password else "read-only (set ADMIN_PASSWORD to enable writes)"
    print(f"admin dashboard on {args.host}:{args.port} [{mode}]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

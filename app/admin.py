"""Read-only dashboard for pipeline state — WEB_ADMIN.md phase 1.

One page: editions, drafting-run detail, feed health, and deliveries.
Stdlib http.server only; a fresh session per request keeps the page
live. Runs as an opt-in compose service (`profiles: [admin]`) — the
worker's no-ports posture is preserved. The process binds the container
interface; exposure is a host-side publish decision (`127.0.0.1:8080`).
"""

import argparse
import json
import os
import socket
from datetime import UTC, datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def render_html(data: dict) -> str:
    stats = data["stats"]
    rows = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<meta http-equiv='refresh' content='300'>",
        "<title>The Kastle Daily — Operations</title>",
        f"<style>{PAGE_CSS}</style></head><body>",
        "<div class='masthead'><h1>The Kastle Daily</h1>",
        "<div class='dateline'>Operations desk — read-only — generated "
        f"{_fmt_dt(data['generated_at'])} UTC · "
        f"{stats['articles_total']} articles ({stats['articles_24h']} in 24h) · "
        f"{stats['sources_pending']} feeds pending approval</div></div>",
        "<h2>Editions</h2><table><tr><th>Date</th><th>Status</th>"
        "<th>Stories</th><th>SHA-256</th><th>Delivery</th></tr>",
    ]
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

    rows.append(
        "<h2>Feed health</h2><table><tr><th>Publisher</th><th>Category</th>"
        "<th>Approval</th><th>Last ingest</th><th>Detail</th>"
        "<th>Fail streak</th></tr>"
    )
    for feed in data["feeds"]:
        source, latest = feed["source"], feed["latest"]
        streak = feed["streak"]
        streak_cell = (
            f'<span class="status bad">{streak}</span>' if streak
            else '<span class="muted">0</span>'
        )
        rows.append(
            f"<tr><td>{escape(source.publisher)}</td>"
            f"<td class='muted'>{escape(source.category)}</td>"
            f"<td>{_pill(source.approval)}</td>"
            f"<td>{_pill(latest.status if latest else None)} "
            f"<span class='muted'>{_fmt_dt(latest.finished_at if latest else None)}"
            f"</span></td>"
            f"<td class='reason'>{escape(latest.error_code or '—') if latest else '—'}"
            f"</td><td>{streak_cell}</td></tr>"
        )
    rows.append("</table>")
    rows.append(
        "<p class='muted'>Refresh every 5 minutes. No state is modified "
        "by this service.</p></body></html>"
    )
    return "".join(rows)


def make_handler(factory):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                self._respond(200, "application/json", b'{"status":"ok"}')
                return
            if self.path not in ("/", "/index.html"):
                self._respond(404, "text/plain", b"not found")
                return
            with factory() as session:
                body = render_html(dashboard_data(session)).encode()
            self._respond(200, "text/html; charset=utf-8", body)

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
    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(session_factory(engine))
    )
    print(f"admin dashboard on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import asyncio
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Database
from integrations.problem_reports import AdminView, MediaView, ProblemReportFlow


def test_legacy_database_is_migrated_once(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (discord_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    async def run():
        db = Database(str(path))
        await db.connect()
        columns = {row[1] for row in await (await db.conn.execute("PRAGMA table_info(users)")).fetchall()}
        assert {"created_at", "overseerr_id", "overseerr_plex_username", "updated_at"}.issubset(columns)
        migrations = [row[0] for row in await (await db.conn.execute("SELECT version FROM schema_migrations ORDER BY version")).fetchall()]
        assert migrations == ["001_legacy_users", "002_problem_report_sources"]
        await db.conn.close()

    asyncio.run(run())


def test_problem_report_persistence(tmp_path):
    async def run():
        db = Database(str(tmp_path / "reports.db"))
        await db.connect()
        report_id = await db.create_problem_report(
            discord_id="1",
            discord_username="member",
            category="video",
            subcategory=None,
            media_type="movie",
            media_id=10,
            media_title="Film",
            season_number=None,
            episode_number=None,
            episode_title=None,
            description="Image noire",
            reported_at="2026-01-01T00:00:00",
        )
        report = await db.get_problem_report(report_id)
        assert report["status"] == "open"
        assert report["source"] == "discord"
        assert (await db.get_open_problem_reports())[0]["id"] == report_id
        await db.update_problem_report(report_id, status="resolved", resolved_at="2026-01-02T00:00:00")
        assert await db.get_open_problem_reports() == []
        await db.conn.close()

    asyncio.run(run())


def test_media_view_paginates_options_above_discord_limit():
    results = [{"id": index, "title": f"Film {index}"} for index in range(26)]
    view = MediaView(object(), {"media_type": "movie"}, results)
    select = view.children[0]
    assert len(select.options) == 25
    assert [item.label for item in view.children[1:]] == ["Suivant"]

    second_page = MediaView(object(), {"media_type": "movie"}, results, page=1)
    assert len(second_page.children[0].options) == 1
    assert [item.label for item in second_page.children[1:]] == ["Précédent"]


def test_report_embed_labels_original_description():
    flow = object.__new__(ProblemReportFlow)
    embed = flow.embed({
        "id": 7,
        "status": "open",
        "discord_id": "1",
        "category": "video",
        "source": "discord",
        "reported_at": "2026-01-01T00:00:00",
        "description": "L'image reste noire.",
    })
    assert [(field.name, field.value) for field in embed.fields if field.name == "Description du problème"] == [
        ("Description du problème", "L'image reste noire.")
    ]


def test_admin_view_uses_report_specific_custom_ids():
    bridge = type("Bridge", (), {"admin_id": 1})()
    flow = type("Flow", (), {"admin_id": 1, "bridge": bridge})()
    view = AdminView(flow, 42)
    assert [item.custom_id for item in view.children] == ["report:42:reply", "report:42:resolve"]

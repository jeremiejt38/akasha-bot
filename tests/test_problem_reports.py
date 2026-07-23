import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Database
from integrations.problem_reports import AdminView


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
        assert (await db.get_open_problem_reports())[0]["id"] == report_id
        await db.update_problem_report(report_id, status="resolved", resolved_at="2026-01-02T00:00:00")
        assert await db.get_open_problem_reports() == []
        await db.conn.close()

    asyncio.run(run())


def test_admin_view_uses_report_specific_custom_ids():
    bridge = type("Bridge", (), {"admin_id": 1})()
    flow = type("Flow", (), {"admin_id": 1, "bridge": bridge})()
    view = AdminView(flow, 42)
    assert [item.custom_id for item in view.children] == ["report:42:reply", "report:42:resolve"]

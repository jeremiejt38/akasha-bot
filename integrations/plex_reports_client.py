import os
import aiohttp


class PlexReportsClient:
    endpoint = "https://community.plex.tv/api"

    def __init__(self, token=None):
        self.token = token or os.getenv("PLEX_TOKEN", "")
        self.session = None

    async def _request(self, query, variables=None, operation_name=None):
        if not self.token:
            raise RuntimeError("PLEX_TOKEN must be configured")
        if self.session is None:
            self.session = aiohttp.ClientSession()
        headers = {
            "Content-Type": "application/json",
            "X-Plex-Token": self.token,
            "X-Plex-Product": "Akasha-bot",
            "X-Plex-Client-Identifier": "akasha-bot-reports",
            "X-Plex-Version": "1.0",
        }
        payload = {"query": query, "variables": variables or {}, "operationName": operation_name}
        async with self.session.post(self.endpoint, headers=headers, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        if data.get("errors"):
            raise RuntimeError(data["errors"][0].get("message", "Plex GraphQL error"))
        return data.get("data", {})

    async def list_reports(self, first=25, after=None):
        data = await self._request(
            "query reports($first: PaginationInt, $after: String) { reports(first: $first, after: $after) { nodes { id message url date commentCount user { id username displayName } } pageInfo { hasNextPage endCursor } } }",
            {"first": max(2, min(first, 100)), "after": after},
            "reports",
        )
        return data["reports"]

    async def get_report_comments(self, report_id, first=25, after=None):
        data = await self._request(
            "query reportComments($id: ID!, $first: PaginationInt, $after: String) { reportComments(id: $id, first: $first, after: $after) { nodes { id message status date user { id username displayName } } pageInfo { hasNextPage endCursor } } }",
            {"id": report_id, "first": max(2, min(first, 100)), "after": after},
            "reportComments",
        )
        return data["reportComments"]

    async def create_comment(self, report_id, message):
        data = await self._request(
            "mutation createReportComment($input: CreateReportCommentInput!) { createReportComment(input: $input) { id message status date } }",
            {"input": {"report": report_id, "message": message}},
            "createReportComment",
        )
        return data["createReportComment"]

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

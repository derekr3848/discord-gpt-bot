# asana_integration.py

import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

import aiohttp

ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_TEMPLATE_GID = os.getenv("ASANA_TEMPLATE_GID")

ASANA_API_BASE = "https://app.asana.com/api/1.0"

# Where we store user -> project mapping on disk so it's not lost on restart
ASANA_MAPPING_FILE = "asana_user_projects.json"


def _load_mapping() -> Dict[str, str]:
    try:
        with open(ASANA_MAPPING_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_mapping(mapping: Dict[str, str]) -> None:
    try:
        with open(ASANA_MAPPING_FILE, "w") as f:
            json.dump(mapping, f)
    except Exception:
        # Don't crash the bot if saving fails
        pass


@dataclass
class WeeklySummary:
    text: str
    overdue_task_gids: List[str]


class AsanaClient:
    def __init__(self) -> None:
        if not ASANA_ACCESS_TOKEN:
            raise RuntimeError("ASANA_ACCESS_TOKEN is not set")
        if not ASANA_TEMPLATE_GID:
            raise RuntimeError("ASANA_TEMPLATE_GID is not set")

        self.token = ASANA_ACCESS_TOKEN
        self.template_gid = ASANA_TEMPLATE_GID
        self._user_projects: Dict[str, str] = _load_mapping()

    # ---------- low-level HTTP ----------

    async def _request(self, method: str, path: str, session: aiohttp.ClientSession, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        headers["Content-Type"] = "application/json"

        url = f"{ASANA_API_BASE}{path}"
        async with session.request(method, url, headers=headers, **kwargs) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Asana API error {resp.status}: {text}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {}

    # ---------- project template instantiation ----------

    async def create_project_for_user(
        self,
        session: aiohttp.ClientSession,
        discord_user_id: int,
        client_name: str,
    ) -> str:
        """
        Instantiate a project from the template for this Discord user.
        Returns the new project gid.
        """
        user_key = str(discord_user_id)
        # If we already created one before, reuse it
        if user_key in self._user_projects:
            return self._user_projects[user_key]

        project_name = f"{client_name} – 6 Month Scale Plan"

        payload = {
            "data": {
                "name": project_name,
                # You can add start_on/due_on in future if you want
            }
        }

        # POST /project_templates/{project_template_gid}/instantiateProject
        data = await self._request(
            "POST",
            f"/project_templates/{self.template_gid}/instantiateProject",
            session,
            json=payload,
        )

        # Asana returns a "job" – we grab the new project GID from it
        job = data.get("data", {})
        new_project = job.get("new_project") or job.get("project") or {}
        project_gid = new_project.get("gid")
        if not project_gid:
            raise RuntimeError(f"Could not find new project gid in Asana response: {data}")

        self._user_projects[user_key] = project_gid
        _save_mapping(self._user_projects)
        return project_gid

    def get_project_for_user(self, discord_user_id: int) -> Optional[str]:
        return self._user_projects.get(str(discord_user_id))

    # ---------- task reading ----------

    async def _get_project_tasks(
        self,
        session: aiohttp.ClientSession,
        project_gid: str,
    ) -> List[dict]:
        """
        Get tasks for a project with important fields.
        """
        params = {
            "project": project_gid,
            "opt_fields": (
                "name,completed,completed_at,due_on,permalink_url,"
                "memberships.section.name"
            ),
            "limit": 100,
        }

        data = await self._request("GET", "/tasks", session, params=params)
        return data.get("data", [])

    @staticmethod
    def _parse_due_on(due_on: Optional[str]) -> Optional[date]:
        if not due_on:
            return None
        try:
            return datetime.strptime(due_on, "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _parse_completed_at(completed_at: Optional[str]) -> Optional[date]:
        if not completed_at:
            return None
        try:
            # Asana timestamps look like "2025-01-01T12:34:56.000Z"
            return datetime.fromisoformat(completed_at.replace("Z", "+00:00")).date()
        except Exception:
            return None

    # ---------- daily agenda ----------

    async def build_daily_agenda(
        self,
        session: aiohttp.ClientSession,
        discord_user_id: int,
    ) -> Optional[str]:
        project_gid = self.get_project_for_user(discord_user_id)
        if not project_gid:
            return None

        tasks = await self._get_project_tasks(session, project_gid)

        today = date.today()
        week_ahead = today + timedelta(days=7)

        due_today = []
        overdue = []
        upcoming = []

        for t in tasks:
            if t.get("completed"):
                continue

            due_on = self._parse_due_on(t.get("due_on"))
            name = t.get("name", "Untitled task")
            url = t.get("permalink_url")
            memberships = t.get("memberships") or []
            section_name = None
            if memberships:
                section = memberships[0].get("section") or {}
                section_name = section.get("name")

            entry = {
                "name": name,
                "url": url,
                "due_on": due_on,
                "section": section_name,
            }

            if due_on is None:
                # No due date – skip from daily/weekly logic
                continue
            elif due_on < today:
                overdue.append(entry)
            elif due_on == today:
                due_today.append(entry)
            elif today < due_on <= week_ahead:
                upcoming.append(entry)

        if not due_today and not overdue and not upcoming:
            return None

        lines = ["**📅 Your Asana Agenda For Today**\n"]

        if due_today:
            lines.append("**✅ Due Today:**")
            for e in due_today:
                sec = f" ({e['section']})" if e["section"] else ""
                link = f" – [Open in Asana]({e['url']})" if e["url"] else ""
                lines.append(f"- {e['name']}{sec}{link}")
            lines.append("")

        if overdue:
            lines.append("**⚠️ Overdue:**")
            for e in overdue:
                sec = f" ({e['section']})" if e["section"] else ""
                when = f" (was due {e['due_on'].isoformat()})" if e["due_on"] else ""
                link = f" – [Open in Asana]({e['url']})" if e["url"] else ""
                lines.append(f"- {e['name']}{sec}{when}{link}")
            lines.append("")

        if upcoming:
            lines.append("**📆 Coming Up (next 7 days):**")
            for e in upcoming:
                sec = f" ({e['section']})" if e["section"] else ""
                when = f" (due {e['due_on'].isoformat()})" if e["due_on"] else ""
                link = f" – [Open in Asana]({e['url']})" if e["url"] else ""
                lines.append(f"- {e['name']}{sec}{when}{link}")
            lines.append("")

        lines.append(
            "_Mark tasks complete in Asana or tell me here when you finish something and I'll help you decide what's next._"
        )

        return "\n".join(lines)

    # ---------- weekly summary + reschedule ----------

    async def build_weekly_summary(
        self,
        session: aiohttp.ClientSession,
        discord_user_id: int,
    ) -> Optional[WeeklySummary]:
        """
        Build a weekly summary text and collect overdue task gids.
        """
        project_gid = self.get_project_for_user(discord_user_id)
        if not project_gid:
            return None

        tasks = await self._get_project_tasks(session, project_gid)

        today = date.today()
        week_start = today - timedelta(days=7)

        completed_this_week = 0
        overdue_tasks: List[dict] = []

        for t in tasks:
            name = t.get("name", "Untitled task")
            url = t.get("permalink_url")
            memberships = t.get("memberships") or []
            section_name = None
            if memberships:
                section = memberships[0].get("section") or {}
                section_name = section.get("name")

            completed = t.get("completed", False)
            due_on = self._parse_due_on(t.get("due_on"))
            completed_at = self._parse_completed_at(t.get("completed_at"))

            if completed and completed_at and week_start <= completed_at <= today:
                completed_this_week += 1

            if (not completed) and due_on and due_on < today:
                overdue_tasks.append(
                    {
                        "gid": t.get("gid"),
                        "name": name,
                        "url": url,
                        "section": section_name,
                        "due_on": due_on,
                    }
                )

        lines: List[str] = []
        lines.append("**📆 Weekly Review (Asana Program)**\n")

        lines.append(f"**✅ Tasks completed this week:** {completed_this_week}")
        lines.append(f"**⚠️ Tasks currently overdue:** {len(overdue_tasks)}")
        lines.append("")

        if overdue_tasks:
            lines.append("Here are some of the overdue tasks:")
            for e in overdue_tasks[:8]:
                sec = f" ({e['section']})" if e["section"] else ""
                when = f" (was due {e['due_on'].isoformat()})"
                link = f" – [Open in Asana]({e['url']})" if e["url"] else ""
                lines.append(f"- {e['name']}{sec}{when}{link}")
            lines.append("")

        # Light faith / hybrid tone
        if completed_this_week == 0 and overdue_tasks:
            lines.append(
                "_This week was slower. That's okay — but let's recommit. Steward the work God has given you and let's move these forward._"
            )
        elif completed_this_week > 0 and overdue_tasks:
            lines.append(
                "_Good progress, but there's still weight on the board. Let's clear these overdue tasks so you can step into the next level._"
            )
        elif completed_this_week > 0 and not overdue_tasks:
            lines.append(
                "_Great job staying on top of your roadmap this week. Keep being faithful with the work in front of you._"
            )
        else:
            lines.append(
                "_This week was quiet. Let's make next week a focused one with clear, completed actions._"
            )

        overdue_gids = [t["gid"] for t in overdue_tasks if t.get("gid")]

        text = "\n".join(lines)
        if len(text) > 1800:
            text = text[:1800] + "\n\n_(truncated)_"

        return WeeklySummary(text=text, overdue_task_gids=overdue_gids)

    async def reschedule_tasks(
        self,
        session: aiohttp.ClientSession,
        task_gids: List[str],
        days: int = 3,
    ) -> None:
        """
        Push overdue tasks forward by `days` days from today.
        """
        if not task_gids:
            return
        new_due = (date.today() + timedelta(days=days)).isoformat()
        for gid in task_gids:
            try:
                await self._request(
                    "PUT",
                    f"/tasks/{gid}",
                    session,
                    json={"data": {"due_on": new_due}},
                )
            except Exception as e:
                print(f"[Asana] Failed to reschedule task {gid}: {e}")

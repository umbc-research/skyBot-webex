"""
Session Manager for SkyBot WebEx

Manages observing session threads within a single WebEx Space.
Each night gets a parent message, with updates posted as threaded replies.
"""

import datetime
from typing import Optional, List, Dict
from webex_client import WebExClient


class SessionManager:
    """Manages observing session threads within a single WebEx Space."""

    DATE_FORMAT = "%Y-%m-%d"

    def __init__(self, client: WebExClient, space_id: str):
        """
        Initialize the session manager.

        Args:
            client: WebEx client instance
            space_id: ID of the "Observing Nights" Space
        """
        self.client = client
        self.space_id = space_id

    def create_session_space(
        self,
        date: datetime.date,
        operator_message: str,
        operator_emails: List[str],
        team_id: str = None
    ) -> str:
        """
        Create a new private space for an observing session.

        Args:
            date: The date of the observing session
            operator_message: Initial message with operator assignments
            operator_emails: List of operator emails to add to the space
            team_id: Optional team ID to create the space within

        Returns:
            The space ID of the new session space
        """
        date_str = date.strftime(self.DATE_FORMAT)
        title = f"Observing Session {date_str}"

        space_id = self.client.create_space(title, team_id=team_id)
        print(f"Created session space: {title} (ID: {space_id})")

        # Add operators as members
        for email in operator_emails:
            self.client.add_person_to_space(space_id, email)

        # Post operator assignments
        self.client.send_message(space_id, operator_message, markdown=operator_message)

        # Ask about openscope
        self.client.send_message(
            space_id,
            "Are the ES operators good with this being an openscope session where the community is invited to attend?"
        )

        return space_id

    def post_to_session(self, space_id: str, text: str, markdown: str = None) -> str:
        """Post an update to a session space."""
        return self.client.send_message(room_id=space_id, text=text, markdown=markdown)

    def post_weather_update(self, space_id: str, weather_text: str) -> str:
        """Post a weather update to a session space."""
        return self.post_to_session(space_id, weather_text, weather_text)

    def post_status_go(self, space_id: str) -> str:
        """Post a GO status to a session space."""
        return self.post_to_session(space_id, "Status: GO", "**Status: GO**")

    def post_status_cancelled(self, space_id: str, reason: str = None) -> str:
        """Post a CANCELLED status to a session space."""
        text = "Status: CANCELLED"
        if reason:
            text += f" - {reason}"
        return self.post_to_session(space_id, text, f"**{text}**")

    def post_status_looks_bad(self, space_id: str) -> str:
        """Post a 'looks bad' warning to a session space."""
        return self.post_to_session(
            space_id,
            "Looks bad for observing session",
            "**Looks bad for observing session**"
        )

    def post_observing_hours(self, space_id: str, hours_text: str) -> str:
        """Post observing hours to a session space."""
        return self.post_to_session(space_id, hours_text, f"**{hours_text}**")

    def post_uncancelled(self, space_id: str) -> str:
        """Post an uncancellation notice to a session space."""
        return self.post_to_session(space_id, "Observing session has been uncancelled.", "**Observing session has been uncancelled.**")


class SessionStateManager:
    """Manages session state persistence (replaces threads.csv)."""

    def __init__(self, filepath: str = "data/sessions.csv"):
        self.filepath = filepath
        # State for next 4 days (indices 0-3)
        self.session_parent_ids: List[Optional[str]] = [None, None, None, None]
        self.clear_night_list: List[bool] = [False, False, False, False]
        self.cancelled_night_list: List[bool] = [False, False, False, False]

    def write_sessions(self):
        """Write current session states to sessions.csv"""
        with open(self.filepath, "w") as f:
            for i in range(4):
                parent_id = self.session_parent_ids[i] or ''
                date = (datetime.date.today() + datetime.timedelta(days=i)).strftime('%Y-%m-%d')
                is_clear = '1' if self.clear_night_list[i] else '0'
                is_cancelled = '1' if self.cancelled_night_list[i] else '0'
                f.write(f"{parent_id},{date},{is_clear},{is_cancelled}\n")

    def read_sessions(self):
        """Read session states from sessions.csv"""
        try:
            with open(self.filepath, "r") as f:
                lines = f.read().splitlines()
                for i, line in enumerate(lines[:4]):
                    parts = line.split(',')
                    self.session_parent_ids[i] = parts[0] if parts[0] else None
                    # Date is informational, recalculated on load
                    self.clear_night_list[i] = parts[2] == '1'
                    self.cancelled_night_list[i] = parts[3] == '1'
        except FileNotFoundError:
            # Initialize with empty state
            self.write_sessions()

    def shift_sessions(self):
        """Shift session data at start of new day (called by dailyCheck)."""
        # Shift everything left (day 0 falls off, day 3 becomes empty)
        self.session_parent_ids[0] = self.session_parent_ids[1]
        self.session_parent_ids[1] = self.session_parent_ids[2]
        self.session_parent_ids[2] = self.session_parent_ids[3]
        self.session_parent_ids[3] = None

        self.clear_night_list[0] = self.clear_night_list[1]
        self.clear_night_list[1] = self.clear_night_list[2]
        self.clear_night_list[2] = self.clear_night_list[3]
        self.clear_night_list[3] = False

        self.cancelled_night_list[0] = self.cancelled_night_list[1]
        self.cancelled_night_list[1] = self.cancelled_night_list[2]
        self.cancelled_night_list[2] = self.cancelled_night_list[3]
        self.cancelled_night_list[3] = False

    def get_session_for_day(self, day: int) -> Dict:
        """
        Get session info for a specific day.

        Args:
            day: 1=tonight, 2=tomorrow, 3=day after tomorrow

        Returns:
            Dict with parent_id, is_clear, is_cancelled
        """
        idx = day - 1
        return {
            'parent_id': self.session_parent_ids[idx],
            'is_clear': self.clear_night_list[idx],
            'is_cancelled': self.cancelled_night_list[idx],
            'date': datetime.date.today() + datetime.timedelta(days=idx)
        }

    def set_session_for_day(
        self,
        day: int,
        parent_id: str = None,
        is_clear: bool = None,
        is_cancelled: bool = None
    ):
        """Update session info for a specific day."""
        idx = day - 1
        if parent_id is not None:
            self.session_parent_ids[idx] = parent_id
        if is_clear is not None:
            self.clear_night_list[idx] = is_clear
        if is_cancelled is not None:
            self.cancelled_night_list[idx] = is_cancelled

    def find_day_by_parent_id(self, parent_id: str) -> Optional[int]:
        """Find which day a parent_id belongs to (returns 1-4 or None)."""
        for i, pid in enumerate(self.session_parent_ids):
            if pid == parent_id:
                return i + 1
        return None

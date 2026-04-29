"""
WebEx API Client Wrapper for SkyBot

Provides a simplified interface to the WebEx Teams SDK.
"""

from webexteamssdk import WebexTeamsAPI
from typing import Optional, List


class WebExClient:
    """Wrapper around WebEx Teams API for SkyBot operations."""

    def __init__(self, token: str):
        """
        Initialize the WebEx client.

        Args:
            token: WebEx Bot access token
        """
        self.api = WebexTeamsAPI(access_token=token)
        self.bot_id = None
        self.bot_email = None
        self._init_bot_info()

    def _init_bot_info(self):
        """Get the bot's info from the API using the token."""
        try:
            me = self.api.people.me()
            self.bot_id = me.id
            self.bot_email = me.emails[0] if me.emails else None
            print(f"Bot initialized: {me.displayName} (ID: {self.bot_id})")
        except Exception as e:
            print(f"Warning: Could not get bot info: {e}")

    # === Message Operations ===

    def send_message(
        self,
        room_id: str,
        text: str,
        markdown: str = None,
        parent_id: str = None,
        files: list = None
    ) -> str:
        """
        Send a message to a space.

        Args:
            room_id: The Space ID to send to
            text: Plain text message
            markdown: Optional markdown-formatted message
            parent_id: Optional parent message ID (for threading)
            files: Optional list of file URLs to attach (images, etc.)

        Returns:
            The message ID of the sent message
        """
        kwargs = {"roomId": room_id, "text": text}
        if markdown:
            kwargs["markdown"] = markdown
        if parent_id:
            kwargs["parentId"] = parent_id
        if files:
            kwargs["files"] = files

        message = self.api.messages.create(**kwargs)
        return message.id

    def get_message(self, message_id: str):
        """Get a message by ID."""
        return self.api.messages.get(message_id)

    def delete_message(self, message_id: str):
        """Delete a message by ID."""
        self.api.messages.delete(message_id)

    def list_messages(
        self,
        room_id: str,
        parent_id: str = None,
        max_results: int = 50
    ) -> List:
        """
        List messages in a space.

        Args:
            room_id: The Space ID
            parent_id: Optional - only get replies to this parent
            max_results: Maximum number of messages to return

        Returns:
            List of message objects
        """
        kwargs = {"roomId": room_id, "max": max_results}
        if parent_id:
            kwargs["parentId"] = parent_id

        return list(self.api.messages.list(**kwargs))

    # === Space Operations ===

    def create_space(self, title: str, team_id: str = None) -> str:
        """
        Create a new space, optionally within a team.

        Args:
            title: The space title
            team_id: Optional team ID to create the space within

        Returns:
            The Space ID
        """
        kwargs = {"title": title}
        if team_id:
            kwargs["teamId"] = team_id
        room = self.api.rooms.create(**kwargs)
        return room.id

    def get_team_id_by_name(self, name: str) -> str:
        """Look up a team ID by its name."""
        for team in self.api.teams.list():
            if team.name == name:
                return team.id
        return None

    def get_space(self, room_id: str):
        """Get a space by ID."""
        return self.api.rooms.get(room_id)

    def list_spaces(self) -> List:
        """List all spaces the bot is in."""
        return list(self.api.rooms.list())

    def delete_space(self, room_id: str):
        """Delete a space by ID."""
        self.api.rooms.delete(room_id)

    # === Membership Operations ===

    def add_person_to_space(self, room_id: str, email: str) -> bool:
        """
        Add a person to a space.

        Args:
            room_id: The Space ID
            email: The person's email

        Returns:
            True if successful, False otherwise
        """
        try:
            self.api.memberships.create(roomId=room_id, personEmail=email)
            return True
        except Exception as e:
            print(f"Failed to add {email} to space: {e}")
            return False

    def remove_person_from_space(self, room_id: str, email: str) -> bool:
        """Remove a person from a space."""
        try:
            memberships = self.api.memberships.list(roomId=room_id, personEmail=email)
            for membership in memberships:
                self.api.memberships.delete(membership.id)
            return True
        except Exception as e:
            print(f"Failed to remove {email} from space: {e}")
            return False

    # === People Operations ===

    def get_person_by_email(self, email: str):
        """Look up a person by email."""
        people = list(self.api.people.list(email=email))
        return people[0] if people else None

    def mention_person(self, email: str) -> str:
        """
        Generate a mention string for a person.

        Args:
            email: The person's email

        Returns:
            Markdown mention string
        """
        return f"<@personEmail:{email}>"

    # === Webhook Operations ===

    def create_webhook(self, name: str, target_url: str, resource: str = "messages", event: str = "created") -> str:
        """
        Create a webhook for receiving events.

        Args:
            name: Webhook name
            target_url: HTTPS URL to receive events
            resource: Resource type (messages, memberships, etc.)
            event: Event type (created, deleted, etc.)

        Returns:
            Webhook ID
        """
        webhook = self.api.webhooks.create(
            name=name,
            targetUrl=target_url,
            resource=resource,
            event=event
        )
        return webhook.id

    def list_webhooks(self) -> List:
        """List all webhooks."""
        return list(self.api.webhooks.list())

    def delete_webhook(self, webhook_id: str):
        """Delete a webhook."""
        self.api.webhooks.delete(webhook_id)

    def delete_all_webhooks(self):
        """Delete all existing webhooks (useful for cleanup)."""
        for webhook in self.list_webhooks():
            self.delete_webhook(webhook.id)
            print(f"Deleted webhook: {webhook.name}")

    # === Utility ===

    def is_from_bot(self, person_id: str) -> bool:
        """Check if a message is from the bot itself."""
        return person_id == self.bot_id

    def is_authorized(self, email: str, allowed_emails: List[str]) -> bool:
        """Check if an email is in the authorized list."""
        return email.lower() in [e.lower().strip() for e in allowed_emails]

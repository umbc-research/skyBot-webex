"""
SkyBot WebEx - Main Entry Point

Observatory session management bot for WebEx.
"""

import os
import sys
import socket
import datetime
from threading import Thread

import dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from webex_client import WebExClient
from session_manager import SessionManager, SessionStateManager
from webhook_server import app, set_bot

# Add parent directory to path for importing shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from WeatherCompiler import WeatherCompiler
from ScheduleReader import ScheduleReader

# Load environment variables
dotenv.load_dotenv()


class SkyBotWebEx:
    """Main SkyBot WebEx bot class."""

    def __init__(self):
        """Initialize the bot."""
        # WebEx client (bot email is fetched automatically from the token)
        self.client = WebExClient(token=os.getenv("WEBEX_BOT_TOKEN"))

        # Session manager (handles threaded messages)
        self.session_manager = SessionManager(
            client=self.client,
            space_id=os.getenv("WEBEX_OBSERVING_SPACE_ID")
        )

        # Session state (tracks parent IDs for each day)
        self.state = SessionStateManager()
        self.state.read_sessions()

        # Schedule reader (shared with Discord version)
        self.sr = ScheduleReader()
        self.sr.readScheduleFile()

        # Configuration
        self.include_midnight_shifts = False
        self.authorized_shifters = self._load_authorized_shifters()
        self.observing_space_id = os.getenv("WEBEX_OBSERVING_SPACE_ID")

        # Schedule coordinator email (for uncancel notifications)
        self.schedule_coordinator_email = os.getenv(
            "SCHEDULE_COORDINATOR_EMAIL",
            "coordinator@umbc.edu"
        )

        self._read_config()
        print("SkyBot WebEx initialized")

    def _load_authorized_shifters(self) -> list:
        """Load list of authorized shifter emails."""
        shifters_str = os.getenv("AUTHORIZED_SHIFTERS", "")
        return [e.strip() for e in shifters_str.split(",") if e.strip()]

    def _read_config(self):
        """Read configuration from config.csv"""
        try:
            with open("data/config.csv", "r") as f:
                for line in f.read().splitlines():
                    parts = line.split(',')
                    if parts[0] == "midnight_shifts_enabled":
                        self.include_midnight_shifts = parts[1] == '1'
        except FileNotFoundError:
            self._write_config()

    def _write_config(self):
        """Write configuration to config.csv"""
        with open("data/config.csv", "w") as f:
            ms_enabled = '1' if self.include_midnight_shifts else '0'
            f.write(f"midnight_shifts_enabled,{ms_enabled}\n")

    # === Command Handling ===

    def handle_message(
        self,
        room_id: str,
        message_text: str,
        person_email: str,
        message_id: str,
        parent_id: str = None
    ):
        """
        Handle an incoming message.

        Args:
            room_id: Space where message was sent
            message_text: The message content
            person_email: Email of sender
            message_id: ID of the message
            parent_id: Parent message ID if this is a reply
        """
        cmd = message_text.lower().strip()

        # Basic commands (anyone can use)
        if cmd == 'skybot ping':
            self._cmd_ping(room_id)
        elif cmd == 'skybot help' or cmd == 'skybot':
            self._cmd_help(room_id)
        elif cmd == 'skybot graph':
            self._cmd_graph(room_id)
        elif cmd == 'skybot details':
            self._cmd_details(room_id, extended=False)
        elif cmd == 'skybot details extended':
            self._cmd_details(room_id, extended=True)
        elif cmd == 'skybot details today':
            self._cmd_details_today(room_id)
        elif cmd == 'skybot popscope':
            self._cmd_popscope(room_id)
        elif cmd == 'skybot sessions':
            self._cmd_sessions(room_id)

        # Shifter-only commands
        elif cmd == 'skybot cancel':
            if self._check_shifter(person_email, room_id):
                self._cmd_cancel(room_id, parent_id)
        elif cmd == 'skybot uncancel':
            if self._check_shifter(person_email, room_id):
                self._cmd_uncancel(room_id, parent_id)
        elif cmd == 'skybot enable ms':
            if self._check_shifter(person_email, room_id):
                self._cmd_enable_ms(room_id)
        elif cmd == 'skybot disable ms':
            if self._check_shifter(person_email, room_id):
                self._cmd_disable_ms(room_id)
        elif cmd.startswith('skybot schedule'):
            if self._check_shifter(person_email, room_id):
                self._cmd_schedule(room_id, cmd)

    def _check_shifter(self, email: str, room_id: str) -> bool:
        """Check if user is authorized and send error if not."""
        if self.client.is_authorized(email, self.authorized_shifters):
            return True
        self.client.send_message(room_id, "You do not have permission to use this command.")
        return False

    # === Command Implementations ===

    def _cmd_ping(self, room_id: str):
        """Handle ping command."""
        hostname = socket.getfqdn(socket.gethostname())
        self.client.send_message(room_id, f"O lord, he runnin on {hostname}")

    def _cmd_help(self, room_id: str):
        """Handle help command."""
        wc = WeatherCompiler()
        # Use the existing help text but could be customized for WebEx
        help_text = wc.getHelp()
        # Replace Discord-specific mentions if any
        help_text = help_text.replace("<@&", "@")
        self.client.send_message(room_id, help_text)

    def _cmd_graph(self, room_id: str):
        """Handle graph command - send weather graph URL."""
        from time import time
        url = f"https://forecast.weather.gov/meteograms/Plotter.php?lat=39.2906&lon=-76.6093&wfo=LWX&zcode=MDZ011&gset=18&gdiff=3&unit=0&tinfo=EY5&ahour=0&pcmd=00000100100000000000000000000000000000000000000000000000000&lg=en&indu=1!1!1!&dd=&bw=&hrspan=48&pqpfhr=6&psnwhr=6={int(time())}"
        self.client.send_message(room_id, url)

    def _cmd_details(self, room_id: str, extended: bool = False):
        """Handle details command."""
        wc = WeatherCompiler()
        for day in [1, 2, 3]:
            details = wc.ccForecast(day, extended)
            self.client.send_message(room_id, details, f"```\n{details}\n```")

    def _cmd_details_today(self, room_id: str):
        """Handle details today command."""
        wc = WeatherCompiler()
        details = wc.ccForecast(1, False)
        self.client.send_message(room_id, details, f"```\n{details}\n```")

    def _cmd_popscope(self, room_id: str):
        """Handle popscope command."""
        wc = WeatherCompiler()
        for day in [1, 2, 3]:
            details = wc.popScopeForecast(day)
            self.client.send_message(room_id, details)

    def _cmd_sessions(self, room_id: str):
        """Handle sessions command - list recent sessions."""
        lines = ["**Recent Sessions:**", ""]
        for i in range(4):
            date = (datetime.date.today() + datetime.timedelta(days=i)).strftime('%Y-%m-%d')
            session = self.state.get_session_for_day(i + 1)
            if session['parent_id']:
                if session['is_cancelled']:
                    status = "CANCELLED"
                elif session['is_clear']:
                    status = "GO"
                else:
                    status = "Pending"
                lines.append(f"{date}: {status}")
            else:
                lines.append(f"{date}: No session created")

        self.client.send_message(room_id, "\n".join(lines))

    def _cmd_cancel(self, room_id: str, parent_id: str = None):
        """Handle cancel command."""
        # Find which day this message belongs to
        day = None
        if parent_id:
            day = self.state.find_day_by_parent_id(parent_id)

        if day is None:
            # Try to find by room context (if in observing space)
            self.client.send_message(
                room_id,
                "Please reply to a session thread to cancel it, or use this command in a session thread."
            )
            return

        session = self.state.get_session_for_day(day)
        if session['is_cancelled']:
            self.client.send_message(room_id, "This session is already cancelled.")
            return

        # Cancel the session
        self.state.set_session_for_day(day, is_cancelled=True, is_clear=False)
        self.state.write_sessions()

        # Post to the session thread
        self.session_manager.post_status_cancelled(session['parent_id'])
        self.client.send_message(room_id, "Session has been cancelled.")

    def _cmd_uncancel(self, room_id: str, parent_id: str = None):
        """Handle uncancel command."""
        day = None
        if parent_id:
            day = self.state.find_day_by_parent_id(parent_id)

        if day is None:
            self.client.send_message(
                room_id,
                "Please reply to a session thread to uncancel it."
            )
            return

        session = self.state.get_session_for_day(day)
        if not session['is_cancelled']:
            self.client.send_message(room_id, "This session is not currently cancelled.")
            return

        # Uncancel the session
        self.state.set_session_for_day(day, is_cancelled=False, is_clear=True)
        self.state.write_sessions()

        # Post to the session thread
        self.session_manager.post_uncancelled(
            session['parent_id'],
            self.schedule_coordinator_email
        )
        self.client.send_message(room_id, "Session has been uncancelled.")

    def _cmd_enable_ms(self, room_id: str):
        """Enable midnight shifts."""
        self.include_midnight_shifts = True
        self._write_config()
        self.client.send_message(
            room_id,
            "Midnight shifts enabled - MS operators will be pinged in new observing session threads"
        )

    def _cmd_disable_ms(self, room_id: str):
        """Disable midnight shifts."""
        self.include_midnight_shifts = False
        self._write_config()
        self.client.send_message(
            room_id,
            "Midnight shifts disabled - MS operators will NOT be pinged in new observing session threads"
        )

    def _cmd_schedule(self, room_id: str, cmd: str):
        """Handle schedule command."""
        result = self.sr.changeSchedule(cmd)
        self.client.send_message(room_id, result)

    # === Scheduled Tasks ===

    def daily_check(self):
        """
        Daily weather check - runs at 12:05 UTC.
        Creates new session threads and updates existing ones.
        """
        print("Running daily check...")
        wc = WeatherCompiler()

        # Shift sessions (day 0 becomes yesterday, etc.)
        self.state.shift_sessions()

        # Check each of the next 3 days
        for day in [1, 2, 3]:
            self._check_session(day, wc)

        self.state.write_sessions()
        self.client.send_message(
            self.observing_space_id,
            "Daily checks have been completed"
        )
        print("Daily check complete")

    def obs_sess_check(self):
        """
        Evening session check - runs at 15:05 UTC.
        Updates today's session with latest weather.
        """
        print("Running obs session check...")
        wc = WeatherCompiler()

        session = self.state.get_session_for_day(1)
        if session['is_clear'] and session['parent_id']:
            # Post weather update
            details = wc.ccForecast(1, False)
            self.session_manager.post_weather_update(session['parent_id'], details)

            # Check if still good
            clear_hours = wc.ccAverage(1)
            if clear_hours[0]:
                # Calculate observing hours
                hours_text = self._calculate_observing_hours(clear_hours, wc, 1)
                self.session_manager.post_observing_hours(session['parent_id'], hours_text)
            else:
                self.session_manager.post_status_cancelled(
                    session['parent_id'],
                    "Cloud cover too high"
                )
                self.state.set_session_for_day(1, is_cancelled=True)

        self.state.write_sessions()
        print("Obs session check complete")

    def _check_session(self, day: int, wc: WeatherCompiler):
        """Check/update a session for a specific day."""
        session = self.state.get_session_for_day(day)
        thread_date = datetime.date.today() + datetime.timedelta(days=day - 1)
        clear_hours = wc.ccAverage(day)

        if session['parent_id'] is None:
            # No thread exists yet
            if clear_hours[0] and not session['is_cancelled']:
                # Weather is good - create session thread
                parent_id = self._create_session_thread(day, wc)
                self.state.set_session_for_day(day, parent_id=parent_id, is_clear=True)
            else:
                # Weather is bad
                self.state.set_session_for_day(day, is_clear=False)
        else:
            # Thread already exists - post update
            if not session['is_cancelled']:
                details = wc.ccForecast(day, False)
                self.session_manager.post_weather_update(session['parent_id'], details)

                if clear_hours[0]:
                    self.session_manager.post_status_go(session['parent_id'])
                    hours_text = self._calculate_observing_hours(clear_hours, wc, day)
                    self.session_manager.post_observing_hours(session['parent_id'], hours_text)
                    self.state.set_session_for_day(day, is_clear=True)
                else:
                    self.session_manager.post_status_looks_bad(session['parent_id'])
                    self.state.set_session_for_day(day, is_clear=False)

    def _create_session_thread(self, day: int, wc: WeatherCompiler) -> str:
        """Create a new session thread for a day."""
        obs_date = datetime.date.today() + datetime.timedelta(days=day - 1)
        schedule = self.sr.getSchedule(obs_date.weekday())
        operator_message = self._build_operator_message(schedule)

        parent_id = self.session_manager.create_session_thread(
            date=obs_date,
            operator_message=operator_message
        )

        # Post initial weather
        details = wc.ccForecast(day, False)
        self.session_manager.post_weather_update(parent_id, details)

        return parent_id

    def _build_operator_message(self, schedule) -> str:
        """Build operator assignment message with mentions."""
        lines = []
        shift_names = ['ES1', 'ES2', 'MS1', 'MS2', 'GS1', 'GS2']

        for i, shift in enumerate(shift_names):
            # Skip MS shifts if disabled
            if i in [2, 3] and not self.include_midnight_shifts:
                continue

            email = schedule[i][1]
            if email == '1':
                lines.append(f"{shift}: Operator needed")
            else:
                mention = self.client.mention_person(email)
                lines.append(f"{shift}: {mention}")

        return "\n".join(lines)

    def _calculate_observing_hours(self, clear_hours, wc, day: int) -> str:
        """Calculate and format observing hours."""
        hours = "Observing hours("
        sunset = wc.sunsetTime(datetime.date.today() + datetime.timedelta(days=day - 1)).hour
        length = len(clear_hours)
        index = 4
        cont = False
        first = True

        while index < length:
            if (clear_hours[index - 1] and clear_hours[index - 2] and
                    clear_hours[index - 3] and clear_hours[index]):
                if not cont:
                    if not first:
                        hours += ", "
                    hours += f"{(index + sunset - 4) % 24}:00 - "
                    cont = True
                    first = False
                if index == length - 1:
                    hours += f"{(index + sunset - 1) % 24}:00"
                elif not clear_hours[index + 1]:
                    hours += f"{(index + sunset - 1) % 24}:00"
                    cont = False
            index += 1

        hours += ")"
        return hours


def setup_scheduler(bot: SkyBotWebEx) -> BackgroundScheduler:
    """Set up scheduled jobs."""
    scheduler = BackgroundScheduler()

    # Daily weather check at 12:05 UTC
    scheduler.add_job(
        bot.daily_check,
        CronTrigger(hour=12, minute=5),
        id='daily_check',
        name='Daily Weather Check'
    )

    # Evening session check at 15:05 UTC
    scheduler.add_job(
        bot.obs_sess_check,
        CronTrigger(hour=15, minute=5),
        id='obs_sess_check',
        name='Evening Session Check'
    )

    return scheduler


def main():
    """Main entry point."""
    print("Starting SkyBot WebEx...")

    # Initialize bot
    bot = SkyBotWebEx()

    # Register bot with webhook server
    set_bot(bot)

    # Set up scheduler
    scheduler = setup_scheduler(bot)
    scheduler.start()
    print("Scheduler started")

    # Run webhook server
    port = int(os.getenv('FLASK_PORT', 8080))
    print(f"Starting webhook server on port {port}")
    print("Bot is ready!")

    # Run Flask in the main thread
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()

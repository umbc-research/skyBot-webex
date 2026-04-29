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

# Store directories
WEBEX_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.join(WEBEX_DIR, '..')

# Add parent directory to path for importing shared modules
sys.path.insert(0, PARENT_DIR)
from WeatherCompiler import WeatherCompiler
from ScheduleReader import ScheduleReader

# Load environment variables
dotenv.load_dotenv(os.path.join(WEBEX_DIR, '.env'))


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
        self.state = SessionStateManager(
            filepath=os.path.join(WEBEX_DIR, "data/sessions.csv")
        )
        self.state.read_sessions()

        # Schedule reader - use WebEx-specific schedule.csv in data/
        original_dir = os.getcwd()
        os.chdir(os.path.join(WEBEX_DIR, 'data'))
        self.sr = ScheduleReader()
        self.sr.readScheduleFile()
        os.chdir(original_dir)

        # Configuration
        self.include_midnight_shifts = False
        self.authorized_shifters = self._load_authorized_shifters()
        self.observing_space_id = os.getenv("WEBEX_OBSERVING_SPACE_ID")
        self.team_id = self.client.get_team_id_by_name("UMBC Observatory")
        if self.team_id:
            print(f"Found team: UMBC Observatory (ID: {self.team_id})")
        else:
            print("WARNING: Could not find team 'UMBC Observatory' - sessions will not be added to the team")

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
            with open(os.path.join(WEBEX_DIR, "data/config.csv"), "r") as f:
                for line in f.read().splitlines():
                    parts = line.split(',')
                    if parts[0] == "midnight_shifts_enabled":
                        self.include_midnight_shifts = parts[1] == '1'
        except FileNotFoundError:
            self._write_config()

    def _write_config(self):
        """Write configuration to config.csv"""
        with open(os.path.join(WEBEX_DIR, "data/config.csv"), "w") as f:
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
        # WebEx strips the @mention in group spaces, so the bot may receive
        # "ping" instead of "skybot ping". Strip the "skybot" prefix if present.
        cmd = message_text.lower().strip()
        if cmd.startswith('skybot '):
            cmd = cmd[7:]  # Remove "skybot " prefix
        elif cmd == 'skybot':
            cmd = 'help'

        # Basic commands (anyone can use)
        if cmd == 'ping':
            self._cmd_ping(room_id, parent_id)
        elif cmd == 'help':
            self._cmd_help(room_id, parent_id)
        elif cmd == 'graph':
            self._cmd_graph(room_id, parent_id)
        elif cmd == 'details':
            self._cmd_details(room_id, extended=False, parent_id=parent_id)
        elif cmd == 'details extended':
            self._cmd_details(room_id, extended=True, parent_id=parent_id)
        elif cmd == 'details today':
            self._cmd_details_today(room_id, parent_id)
        elif cmd == 'popscope':
            self._cmd_popscope(room_id, parent_id)
        elif cmd == 'sessions':
            self._cmd_sessions(room_id, parent_id)
        elif cmd == 'testcheck':
            if self._check_shifter(person_email, room_id, parent_id):
                self.daily_check()

        # Shifter-only commands
        elif cmd.startswith('create session'):
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_create_session(room_id, cmd, parent_id)
        elif cmd == 'cancel':
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_cancel(room_id, parent_id)
        elif cmd == 'uncancel':
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_uncancel(room_id, parent_id)
        elif cmd == 'enable ms':
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_enable_ms(room_id, parent_id)
        elif cmd == 'disable ms':
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_disable_ms(room_id, parent_id)
        elif cmd.startswith('schedule'):
            if self._check_shifter(person_email, room_id, parent_id):
                self._cmd_schedule(room_id, cmd, parent_id)

    def _check_shifter(self, email: str, room_id: str, parent_id: str = None) -> bool:
        """Check if user is authorized and send error if not."""
        if self.client.is_authorized(email, self.authorized_shifters):
            return True
        self.client.send_message(room_id, "You do not have permission to use this command.", parent_id=parent_id)
        return False

    # === Command Implementations ===

    def _cmd_ping(self, room_id: str, parent_id: str = None):
        """Handle ping command."""
        hostname = socket.getfqdn(socket.gethostname())
        self.client.send_message(room_id, f"O lord, he runnin on {hostname}", parent_id=parent_id)

    def _cmd_help(self, room_id: str, parent_id: str = None):
        """Handle help command with WebEx-formatted markdown."""
        help_md = (
            "**skyBot** - UMBC Observatory Bot\n"
            "git: https://github.com/outyprouty/skyBot\n\n"
            "skyBot uses NOAA to gather sky data and organize it for easy viewing.\n\n"
            "---\n"
            "**Automatic Actions**\n\n"
            "- **Daily Checks**: Every day at 12:05, skyBot checks the average cloud cover for the next three nights. "
            "It sends a summary and creates observing session threads if the night is clear.\n"
            "- **Obs Session Check**: Every day at 15:05, if an obs session is scheduled, skyBot rechecks cloud cover "
            "and reports if it's still clear.\n"
            "- **Popscope Check**: Every day at 12:04, sends summary of whether the next three days are good for a Popscope event.\n\n"
            "A clear night = NOAA says a 4-hour rolling average of cloud cover (sunset to sunrise) is 30% or less.\n\n"
            "---\n"
            "**General Commands** (anyone)\n\n"
            "- **graph** - Weather graph for the next 48 hours\n"
            "- **details** - Cloud cover for dark hours, next 3 days\n"
            "- **details today** - Cloud cover for dark hours, today only\n"
            "- **details extended** - Cloud cover 18:00-05:00, then 05:00-10:00\n"
            "- **popscope** - Cloud cover sunset to 21:00, next 3 days\n"
            "- **ping** - Show host running skyBot\n"
            "- **help** - This message\n"
            "- **sessions** - Show recent session status\n\n"
            "---\n"
            "**Shifter Commands** (authorized only)\n\n"
            "- **create session YYYY-MM-DD** - Manually create a session space for a given date (today to day+2)\n"
            "- **cancel** - Cancel an observing session (use inside session space)\n"
            "- **uncancel** - Uncancel a previously cancelled session (use inside session space)\n"
            "- **enable ms** - Enable midnight shift pinging (winter months)\n"
            "- **disable ms** - Disable midnight shift pinging (summer months)\n"
            "- **schedule [day] [shift] [operator]** - Update the schedule\n"
        )
        self.client.send_message(room_id, help_md, markdown=help_md, parent_id=parent_id)

    def _cmd_graph(self, room_id: str, parent_id: str = None):
        """Handle graph command - send weather graph as an embedded image."""
        from time import time
        url = f"https://forecast.weather.gov/meteograms/Plotter.php?lat=39.2906&lon=-76.6093&wfo=LWX&zcode=MDZ011&gset=18&gdiff=3&unit=0&tinfo=EY5&ahour=0&pcmd=00000100100000000000000000000000000000000000000000000000000&lg=en&indu=1!1!1!&dd=&bw=&hrspan=48&pqpfhr=6&psnwhr=6={int(time())}"
        self.client.send_message(room_id, "48-Hour Weather Forecast", files=[url], parent_id=parent_id)

    def _cmd_details(self, room_id: str, extended: bool = False, parent_id: str = None):
        """Handle details command."""
        wc = WeatherCompiler()
        for day in [1, 2, 3]:
            details = wc.ccForecast(day, extended)
            self.client.send_message(room_id, details, details, parent_id=parent_id)

    def _cmd_details_today(self, room_id: str, parent_id: str = None):
        """Handle details today command."""
        wc = WeatherCompiler()
        details = wc.ccForecast(1, False)
        self.client.send_message(room_id, details, details, parent_id=parent_id)

    def _cmd_popscope(self, room_id: str, parent_id: str = None):
        """Handle popscope command."""
        wc = WeatherCompiler()
        for day in [1, 2, 3]:
            details = wc.popScopeForecast(day)
            self.client.send_message(room_id, details, details, parent_id=parent_id)

    def _cmd_sessions(self, room_id: str, parent_id: str = None):
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

        self.client.send_message(room_id, "\n".join(lines), parent_id=parent_id)

    def _cmd_create_session(self, room_id: str, cmd: str, parent_id: str = None):
        """Handle create session YYYY-MM-DD command."""
        parts = cmd.split()
        if len(parts) != 3:
            self.client.send_message(
                room_id,
                "Usage: create session YYYY-MM-DD (e.g. create session 2026-04-30)",
                parent_id=parent_id
            )
            return

        try:
            target_date = datetime.date.fromisoformat(parts[2])
        except ValueError:
            self.client.send_message(
                room_id,
                "Invalid date format. Use YYYY-MM-DD (e.g. create session 2026-04-30)",
                parent_id=parent_id
            )
            return

        today = datetime.date.today()
        day = (target_date - today).days + 1

        if day < 1 or day > 3:
            self.client.send_message(
                room_id,
                f"Date must be today, tomorrow, or the day after ({today} to {today + datetime.timedelta(days=2)}).",
                parent_id=parent_id
            )
            return

        session = self.state.get_session_for_day(day)
        if session['parent_id']:
            self.client.send_message(
                room_id,
                f"A session space already exists for {target_date}.",
                parent_id=parent_id
            )
            return

        wc = WeatherCompiler()
        space_id = self._create_session_thread(day, wc)
        self.state.set_session_for_day(day, parent_id=space_id, is_clear=True)
        self.state.write_sessions()
        self.client.send_message(room_id, f"Session space created for {target_date}.", parent_id=parent_id)

    def _cmd_cancel(self, room_id: str, parent_id: str = None):
        """Handle cancel command."""
        day = self.state.find_day_by_parent_id(room_id)

        if day is None:
            self.client.send_message(
                room_id,
                "Please use this command inside a session space."
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
        day = self.state.find_day_by_parent_id(room_id)

        if day is None:
            self.client.send_message(
                room_id,
                "Please use this command inside a session space."
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
        self.session_manager.post_uncancelled(session['parent_id'])
        self.client.send_message(room_id, "Session has been uncancelled.")

    def _cmd_enable_ms(self, room_id: str, parent_id: str = None):
        """Enable midnight shifts."""
        self.include_midnight_shifts = True
        self._write_config()
        self.client.send_message(
            room_id,
            "Midnight shifts enabled - MS operators will be pinged in new observing session threads",
            parent_id=parent_id
        )

    def _cmd_disable_ms(self, room_id: str, parent_id: str = None):
        """Disable midnight shifts."""
        self.include_midnight_shifts = False
        self._write_config()
        self.client.send_message(
            room_id,
            "Midnight shifts disabled - MS operators will NOT be pinged in new observing session threads",
            parent_id=parent_id
        )

    def _cmd_schedule(self, room_id: str, cmd: str, parent_id: str = None):
        """Handle schedule command."""
        original_dir = os.getcwd()
        os.chdir(os.path.join(WEBEX_DIR, 'data'))
        result = self.sr.changeSchedule("skybot " + cmd)
        os.chdir(original_dir)
        self.client.send_message(room_id, result, parent_id=parent_id)

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
        """Create a new session space for a day."""
        obs_date = datetime.date.today() + datetime.timedelta(days=day - 1)
        schedule = self.sr.getSchedule(obs_date.weekday())
        operator_message, operator_emails = self._build_operator_message(schedule)

        space_id = self.session_manager.create_session_space(
            date=obs_date,
            operator_message=operator_message,
            operator_emails=operator_emails,
            team_id=self.team_id
        )

        # Post initial weather
        details = wc.ccForecast(day, False)
        self.session_manager.post_weather_update(space_id, details)

        return space_id

    def _build_operator_message(self, schedule) -> tuple:
        """Build operator assignment message with mentions. Returns (message, emails)."""
        lines = []
        emails = []
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
                if email not in emails:
                    emails.append(email)

        return "\n".join(lines), emails

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

    # Register webhook with WebEx
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        print("Registering webhook with WebEx...")
        bot.client.delete_all_webhooks()
        webhook_id = bot.client.create_webhook(
            name='SkyBot Message Handler',
            target_url=webhook_url,
            resource='messages',
            event='created'
        )
        print(f"Webhook registered: {webhook_url} (ID: {webhook_id})")
    else:
        print("WARNING: WEBHOOK_URL not set - bot won't receive messages!")

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

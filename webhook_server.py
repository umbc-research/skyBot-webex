"""
WebEx Webhook Server for SkyBot

Receives incoming messages from WebEx and routes them to the bot.
"""

from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Bot instance (set by main.py on startup)
_bot = None


def set_bot(bot_instance):
    """Set the bot instance for handling commands."""
    global _bot
    _bot = bot_instance


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'bot_connected': _bot is not None
    })


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """
    Handle incoming WebEx webhook events.

    WebEx sends a POST with event data when messages are created.
    We need to fetch the full message content separately (WebEx doesn't include it).
    """
    if _bot is None:
        return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 503

    try:
        data = request.json

        # Extract event info
        resource = data.get('resource')
        event = data.get('event')
        event_data = data.get('data', {})

        # Only handle message:created events
        if resource != 'messages' or event != 'created':
            return jsonify({'status': 'ignored', 'reason': 'Not a message event'})

        # Ignore messages from the bot itself
        person_id = event_data.get('personId')
        if _bot.client.is_from_bot(person_id):
            return jsonify({'status': 'ignored', 'reason': 'Message from bot'})

        # Get the full message content (webhook only contains IDs)
        message_id = event_data.get('id')
        room_id = event_data.get('roomId')
        person_email = event_data.get('personEmail')

        # Fetch full message
        message = _bot.client.get_message(message_id)
        message_text = message.text or ''

        # Route to command handler
        _bot.handle_message(
            room_id=room_id,
            message_text=message_text,
            person_email=person_email,
            message_id=message_id,
            parent_id=getattr(message, 'parentId', None)
        )

        return jsonify({'status': 'ok'})

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/setup-webhook', methods=['POST'])
def setup_webhook():
    """
    Manually trigger webhook setup (for initial configuration).

    POST to this endpoint to register the webhook with WebEx.
    """
    if _bot is None:
        return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 503

    try:
        webhook_url = os.getenv('WEBHOOK_URL')
        if not webhook_url:
            return jsonify({'status': 'error', 'message': 'WEBHOOK_URL not configured'}), 400

        # Delete existing webhooks first
        _bot.client.delete_all_webhooks()

        # Create new webhook
        webhook_id = _bot.client.create_webhook(
            name='SkyBot Message Handler',
            target_url=f"{webhook_url}/webhook",
            resource='messages',
            event='created'
        )

        return jsonify({
            'status': 'ok',
            'webhook_id': webhook_id,
            'target_url': f"{webhook_url}/webhook"
        })

    except Exception as e:
        print(f"Webhook setup error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def run_server(port: int = 8080, debug: bool = False):
    """Run the Flask server."""
    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    # For testing - run standalone
    port = int(os.getenv('FLASK_PORT', 8080))
    run_server(port=port, debug=True)

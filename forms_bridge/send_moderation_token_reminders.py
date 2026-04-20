import json

from forms_bridge.app import create_app
from forms_bridge.performer_workflow import send_expired_moderation_token_reminders


def main():
    app = create_app()
    with app.app_context():
        result = send_expired_moderation_token_reminders(app)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

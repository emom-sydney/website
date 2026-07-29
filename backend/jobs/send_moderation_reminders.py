import json

from backend.app import create_app
from backend.performer_workflow import send_due_moderation_reminders


def main():
    app = create_app()
    with app.app_context():
        result = send_due_moderation_reminders(app)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

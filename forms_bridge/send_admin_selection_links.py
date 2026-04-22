import argparse
import json

from forms_bridge.app import create_app
from forms_bridge.performer_workflow import send_due_admin_selection_emails


def main():
    parser = argparse.ArgumentParser(
        description="Send admin link for performer lineup selection."
    )
    parser.add_argument(
        "--run-date",
        help="Override the base run date in YYYY-MM-DD format before lead-day calculation.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = send_due_admin_selection_emails(app, run_date=args.run_date)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

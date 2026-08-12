import json

from backend.profile_qr import purge_expired_qr_events


def main():
    print(json.dumps(purge_expired_qr_events(), indent=2))


if __name__ == "__main__":
    main()

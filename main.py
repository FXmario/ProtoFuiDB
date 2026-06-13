import getpass
from pathlib import Path
from zoneinfo import available_timezones

import questionary


def main(base_dir: Path | None = None) -> None:
    base_dir = base_dir or Path(__file__).resolve().parent

    secret_key = getpass.getpass("Your SECRET KEY: ")
    secret_key = secret_key.strip()

    if len(secret_key) < 1:
        print("\nYou have to put the SECRET_KEY. Setup aborted")
        return None

    time_zones = sorted(available_timezones())
    time_zone = questionary.autocomplete(
        "Select your timezone:",
        choices=time_zones,
        default="UTC",
    ).ask()

    if not time_zone:
        print("\nYou have to select a timezone. Setup aborted")
        return None

    env_path = base_dir / ".env"
    if env_path.exists():
        replace = questionary.confirm(
            ".env already exists. Do you want to replace it?",
            default=False,
        ).ask()
        if not replace:
            print("\nSetup aborted")
            return None

    with open(env_path, "w") as env_file:
        env_file.write(f"SECRET_KEY={secret_key}\n")
        env_file.write(f"TZ={time_zone}\n")

    print("Your .env configuration has been completed")


if __name__ == "__main__":
    main()

import getpass
import json
import os
import re
import config
from notifier import Notifier

SETTINGS_FILE = "email_settings.json"

KNOWN_SERVERS = {
    "gmail.com": ("smtp.gmail.com", 465),
    "googlemail.com": ("smtp.gmail.com", 465),
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
    "yahoo.in": ("smtp.mail.yahoo.com", 465),
    "zoho.com": ("smtp.zoho.com", 465),
}


def is_valid_email(text):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text) is not None


def ask_email(prompt):
    while True:
        value = input(prompt).strip()
        if is_valid_email(value):
            return value
        print("That doesn't look like an email address. Try again.")


def ask_yes_no(prompt):
    while True:
        answer = input(prompt + " (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please type y or n.")


def ask_password():
    print("Gmail users: use a 16-character APP PASSWORD, not your normal password.")
    print("(Typing is hidden. If nothing appears as you type, that's normal.)")
    return getpass.getpass("App password: ").replace(" ", "")


def save_settings():
    data = {
        "sender": config.EMAIL_SENDER,
        "receiver": config.EMAIL_RECEIVER,
        "server": config.SMTP_SERVER,
        "port": config.SMTP_PORT,
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return False
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        config.EMAIL_SENDER = data["sender"]
        config.EMAIL_RECEIVER = data["receiver"]
        config.SMTP_SERVER = data["server"]
        config.SMTP_PORT = int(data["port"])
        return True
    except (ValueError, KeyError, OSError):
        return False


def disable_email():
    config.SEND_EMAIL = "no"
    config.EMAIL_PASSWORD = ""
    print("Email alerts are OFF (desktop notifications still work).")


def pick_server(sender):
    domain = sender.split("@")[1].lower()
    if domain in KNOWN_SERVERS:
        return KNOWN_SERVERS[domain]
    print("I don't know the SMTP server for " + domain + ".")
    server = input("SMTP server (e.g. smtp.yourprovider.com): ").strip()
    port_text = input("SMTP SSL port [465]: ").strip()
    port = int(port_text) if port_text.isdigit() else 465
    return server, port


def setup_email():
    print("\n--- Email setup ---")
    if not ask_yes_no("Do you want email alerts?"):
        disable_email()
        return False

    while True:
        sender = ask_email("Your email address (the account that sends alerts): ")
        server, port = pick_server(sender)
        if ask_yes_no("Send alerts to the same address?"):
            receiver = sender
        else:
            receiver = ask_email("Email address to receive alerts: ")
        password = ask_password()

        config.EMAIL_SENDER = sender
        config.EMAIL_RECEIVER = receiver
        config.SMTP_SERVER = server
        config.SMTP_PORT = port
        config.EMAIL_PASSWORD = password

        print("Testing login...")
        errors = Notifier().test_login()
        if len(errors) == 0:
            config.SEND_EMAIL = "yes"
            save_settings()
            print("Success! Alerts will be sent from " + sender + " to " + receiver + ".")
            return True
        for error in errors:
            print("Error: " + error)
        if not ask_yes_no("Try again?"):
            disable_email()
            return False


def startup_email():
    if load_settings():
        print("\nSaved email settings found: " + config.EMAIL_SENDER
              + " -> " + config.EMAIL_RECEIVER)
        if ask_yes_no("Use these?"):
            config.EMAIL_PASSWORD = ask_password()
            print("Testing login...")
            errors = Notifier().test_login()
            if len(errors) == 0:
                config.SEND_EMAIL = "yes"
                print("Email alerts are ON.")
                return
            for error in errors:
                print("Error: " + error)
            print("Let's set it up again.")
    setup_email()
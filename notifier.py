import smtplib
from email.message import EmailMessage
import config


class Notifier:
    def test_login(self):
        errors = []
        try:
            server = smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=15)
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.quit()
        except smtplib.SMTPAuthenticationError:
            errors.append("Login failed. Check the email and app password "
                          "(a normal password will not work for Gmail).")
        except Exception as e:
            errors.append("Could not connect: " + str(e))
        return errors

    def send_email(self, subject, body):
        errors = []
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = config.EMAIL_SENDER
        message["To"] = config.EMAIL_RECEIVER
        message.set_content(body)
        try:
            server = smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=15)
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.send_message(message)
            server.quit()
        except Exception as e:
            errors.append("Email failed: " + str(e))
        return errors

    def send_desktop(self, title, text):
        errors = []
        try:
            from plyer import notification
            notification.notify(title=title, message=text[:250], timeout=10)
        except Exception as e:
            errors.append("Desktop notification failed: " + str(e))
        return errors

    def notify(self, subject, body):
        errors = []
        if config.SEND_EMAIL == "yes":
            errors = errors + self.send_email(subject, body)
        if config.SEND_DESKTOP == "yes":
            errors = errors + self.send_desktop(subject, body)

        print("ALERT: " + subject)
        for error in errors:
            print("  " + error)
        return errors
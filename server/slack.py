import requests

from course import current_course
from models import Failure


def post_slack_message(message: str):
    url = current_course().slack_webhook_url
    if not url:
        raise Failure("Slack notifications are not set up for this course.")
    requests.post(url, json={"text": message}, timeout=10).raise_for_status()

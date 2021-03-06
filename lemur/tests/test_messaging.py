from datetime import timedelta

import arrow
import boto3
import pytest
from freezegun import freeze_time
from moto import mock_ses


@mock_ses
def verify_sender_email():
    ses_client = boto3.client("ses", region_name="us-east-1")
    ses_client.verify_email_identity(EmailAddress="lemur@example.com")


def test_needs_notification(app, certificate, notification):
    from lemur.notifications.messaging import needs_notification

    assert not needs_notification(certificate)

    with pytest.raises(Exception):
        notification.options = [
            {"name": "interval", "value": 10},
            {"name": "unit", "value": "min"},
        ]
        certificate.notifications.append(notification)
        needs_notification(certificate)

    certificate.notifications[0].options = [
        {"name": "interval", "value": 10},
        {"name": "unit", "value": "days"},
    ]
    assert not needs_notification(certificate)

    delta = certificate.not_after - timedelta(days=10)
    with freeze_time(delta.datetime):
        assert needs_notification(certificate)


def test_get_certificates(app, certificate, notification):
    from lemur.notifications.messaging import get_certificates

    certificate.not_after = arrow.utcnow() + timedelta(days=30)
    delta = certificate.not_after - timedelta(days=2)

    notification.options = [
        {"name": "interval", "value": 2},
        {"name": "unit", "value": "days"},
    ]

    with freeze_time(delta.datetime):
        # no notification
        certs = len(get_certificates())

        # with notification
        certificate.notifications.append(notification)
        assert len(get_certificates()) > certs

        certificate.notify = False
        assert len(get_certificates()) == certs

    # expired
    delta = certificate.not_after + timedelta(days=2)
    with freeze_time(delta.datetime):
        certificate.notifications.append(notification)
        assert len(get_certificates()) == 0


def test_get_eligible_certificates(app, certificate, notification):
    from lemur.notifications.messaging import get_eligible_certificates

    certificate.notifications.append(notification)
    certificate.notifications[0].options = [
        {"name": "interval", "value": 10},
        {"name": "unit", "value": "days"},
    ]

    delta = certificate.not_after - timedelta(days=10)
    with freeze_time(delta.datetime):
        assert get_eligible_certificates() == {
            certificate.owner: {notification.label: [(notification, certificate)]}
        }


@mock_ses
def test_send_expiration_notification(certificate, notification, notification_plugin):
    from lemur.notifications.messaging import send_expiration_notifications
    verify_sender_email()

    certificate.notifications.append(notification)
    certificate.notifications[0].options = [
        {"name": "interval", "value": 10},
        {"name": "unit", "value": "days"},
    ]

    delta = certificate.not_after - timedelta(days=10)
    with freeze_time(delta.datetime):
        # this will only send owner and security emails (no additional recipients),
        # but it executes 3 successful send attempts
        assert send_expiration_notifications([]) == (3, 0)


@mock_ses
def test_send_expiration_notification_with_no_notifications(
    certificate, notification, notification_plugin
):
    from lemur.notifications.messaging import send_expiration_notifications

    delta = certificate.not_after - timedelta(days=10)
    with freeze_time(delta.datetime):
        assert send_expiration_notifications([]) == (0, 0)


@mock_ses
def test_send_rotation_notification(notification_plugin, certificate):
    from lemur.notifications.messaging import send_rotation_notification
    verify_sender_email()

    assert send_rotation_notification(certificate)


@mock_ses
def test_send_pending_failure_notification(notification_plugin, async_issuer_plugin, pending_certificate):
    from lemur.notifications.messaging import send_pending_failure_notification
    verify_sender_email()

    assert send_pending_failure_notification(pending_certificate)

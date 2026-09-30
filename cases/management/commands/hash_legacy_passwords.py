from django.contrib.auth.hashers import (
    UNUSABLE_PASSWORD_PREFIX,
    check_password,
    identify_hasher,
    make_password,
)
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cases.models import User


def password_is_already_hashed(value):
    """Return True for Django password hashes and unusable-password markers."""
    if value.startswith(UNUSABLE_PASSWORD_PREFIX):
        return True

    try:
        identify_hasher(value)
    except ValueError:
        return False
    return True


class Command(BaseCommand):
    help = (
        "Replace legacy plain-text values in users.password_hash with "
        "Django password hashes. Defaults to a read-only dry run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Save the password hashes. Without this flag, only report a count.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        if apply_changes:
            with transaction.atomic():
                legacy_count, hashed_count = self.hash_legacy_values(save=True)
        else:
            legacy_count, hashed_count = self.hash_legacy_values(save=False)

        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Hashed {hashed_count} legacy password value(s); "
                    f"{legacy_count} legacy value(s) were found."
                )
            )
        else:
            self.stdout.write(
                f"Dry run: found {legacy_count} legacy password value(s). "
                "No database values were changed. Run with --apply to hash them."
            )

    def hash_legacy_values(self, *, save):
        legacy_count = 0
        hashed_count = 0

        if save:
            users = User.objects.select_for_update().only("id", "password_hash").order_by("id")
            for user in users.iterator():
                if password_is_already_hashed(user.password_hash):
                    continue

                legacy_count += 1
                # An empty legacy value should not become a valid blank password.
                old_value = user.password_hash
                new_hash = make_password(old_value or None)
                if old_value and not check_password(old_value, new_hash):
                    raise CommandError(
                        f"Could not verify the new password hash for user id {user.pk}."
                    )
                user.password_hash = new_hash
                user.save(update_fields=["password_hash"])
                hashed_count += 1
        else:
            values = User.objects.values_list("password_hash", flat=True).iterator()
            for value in values:
                if not password_is_already_hashed(value):
                    legacy_count += 1

        return legacy_count, hashed_count

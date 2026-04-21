import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tns_api.models import UserProfile, UserRole


class Command(BaseCommand):
    help = "Create or update a Django superuser and align the app role to SUPERUSER"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            dest="username",
            help="Superuser username. Falls back to DJANGO_SUPERUSER_USERNAME.",
        )
        parser.add_argument(
            "--email",
            dest="email",
            help="Superuser email. Falls back to DJANGO_SUPERUSER_EMAIL.",
        )
        parser.add_argument(
            "--password",
            dest="password",
            help="Superuser password. Falls back to DJANGO_SUPERUSER_PASSWORD.",
        )
        parser.add_argument(
            "--first-name",
            dest="first_name",
            help="Optional first name. Falls back to DJANGO_SUPERUSER_FIRST_NAME.",
        )
        parser.add_argument(
            "--last-name",
            dest="last_name",
            help="Optional last name. Falls back to DJANGO_SUPERUSER_LAST_NAME.",
        )

    def handle(self, *args, **options):
        username = self._resolve_option(options, "username", "DJANGO_SUPERUSER_USERNAME")
        email = self._resolve_option(options, "email", "DJANGO_SUPERUSER_EMAIL")
        password = self._resolve_option(options, "password", "DJANGO_SUPERUSER_PASSWORD")
        first_name = self._resolve_option(options, "first_name", "DJANGO_SUPERUSER_FIRST_NAME")
        last_name = self._resolve_option(options, "last_name", "DJANGO_SUPERUSER_LAST_NAME")
        username_was_explicit = username is not None

        if not username and email:
            username = email

        if not username:
            raise CommandError(
                "A username is required. Pass --username or set DJANGO_SUPERUSER_USERNAME."
            )

        with transaction.atomic():
            user = User.objects.filter(username=username).first()
            if not user and email and not username_was_explicit:
                email_match = User.objects.filter(email=email).first()
                if email_match:
                    user = email_match
                    username = user.username

            created = user is None

            if user and email:
                email_owner = User.objects.filter(email=email).exclude(pk=user.pk).first()
                if email_owner:
                    raise CommandError(
                        f"Email '{email}' is already used by username '{email_owner.username}'."
                    )
            elif created and email:
                email_owner = User.objects.filter(email=email).first()
                if email_owner:
                    raise CommandError(
                        f"Email '{email}' is already used by username '{email_owner.username}'."
                    )

            if created and not password:
                raise CommandError(
                    "A password is required when creating a new superuser. "
                    "Pass --password or set DJANGO_SUPERUSER_PASSWORD."
                )

            if not user:
                user = User(username=username)

            updated_fields = []
            password_updated = False

            if email is not None and user.email != email:
                user.email = email
                updated_fields.append("email")

            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name
                updated_fields.append("first_name")

            if last_name is not None and user.last_name != last_name:
                user.last_name = last_name
                updated_fields.append("last_name")

            for field in ("is_staff", "is_superuser", "is_active"):
                if not getattr(user, field):
                    setattr(user, field, True)
                    updated_fields.append(field)

            if created:
                user.set_password(password)
                password_updated = True
                user.save()
            else:
                if password:
                    user.set_password(password)
                    updated_fields.append("password")
                    password_updated = True
                if updated_fields:
                    user.save(update_fields=list(dict.fromkeys(updated_fields)))

            profile, _ = UserProfile.objects.get_or_create(user=user)
            role_updated = False
            if profile.role != UserRole.SUPERUSER:
                profile.role = UserRole.SUPERUSER
                profile.save(update_fields=["role"])
                role_updated = True

        message = "Created" if created else "Updated"
        password_message = "yes" if password_updated else "no"
        role_message = "yes" if role_updated else "no"

        self.stdout.write(
            self.style.SUCCESS(
                f"{message} superuser '{user.username}'. password_updated={password_message}, "
                f"role_aligned={role_message}"
            )
        )

    @staticmethod
    def _resolve_option(options, option_name, env_name):
        value = options.get(option_name)
        if value is None:
            value = os.getenv(env_name)
        if value is None:
            return None

        value = value.strip()
        return value or None

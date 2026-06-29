from django.apps import AppConfig


class StaffConfig(AppConfig):
    name = 'apps.staff'

    def ready(self):
        import apps.staff.signals  # noqa: F401

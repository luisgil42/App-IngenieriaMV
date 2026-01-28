#!/usr/bin/env python
import os
import sys


def main():
    # ✅ Si no viene DJANGO_SETTINGS_MODULE desde el entorno, usa dev.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "mv_ingenieria.settings.dev"))

    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
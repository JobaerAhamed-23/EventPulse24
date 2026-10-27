"""AD-3 wall tests and their test-only probe apps (never shipped; installed by settings_test).

Probe migrations are generated with the test settings, then formatted:

    cd backend && DJANGO_SETTINGS_MODULE=config.settings_test \\
        uv run python manage.py makemigrations catalog_probe personal_probe
    make fmt-backend
"""

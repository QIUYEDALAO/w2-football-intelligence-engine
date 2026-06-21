from __future__ import annotations


def test_application_import_smoke() -> None:
    import apps.api.main
    import apps.scheduler.main
    import apps.worker.celery_app


    assert apps.api.main.app.title == "W2 Football Intelligence Engine"


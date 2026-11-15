"""Local-only slow answer fixture for browser queue tests; never shipped in image."""
import time
import uvicorn
import web.app as module
from web.queue import QueueManager


def fixture_answer(question, latest, state, cancelled):
    duration = 30 if latest.startswith("Первый") else 2
    until = time.monotonic() + duration
    while time.monotonic() < until:
        if cancelled():
            return dict(status="cancelled", text="Ответ остановлен.", sources=[])
        time.sleep(.05)
    fragment = state.retriever.fragments[0]
    doc = state.retriever.documents[fragment.document]
    return dict(status="answer", text="Тестовый ответ: " + latest + " [1]", sources=[dict(
        n=1, document_id=doc.sha256, title=doc.name, status="", heading=fragment.heading,
        quote=fragment.text, start=fragment.start, end=fragment.end)])


class FixtureManager(QueueManager):
    def __init__(self, history, state, workers=2):
        super().__init__(history, state, workers, runner=fixture_answer)


module.QueueManager = FixtureManager
uvicorn.run(module.app, host="0.0.0.0", port=8000, access_log=False)

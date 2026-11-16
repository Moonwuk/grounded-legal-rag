"""Isolated web generation: terminating the child closes its provider connection."""
import multiprocessing
import os
from threading import BoundedSemaphore, Lock, Thread
import time
from types import SimpleNamespace


def generate(connection, control, question, latest, documents, fragments, vectors, core):
    def watch_parent():
        try:
            control.recv_bytes()
        except EOFError:
            pass
        # Exit this worker only, including a blocking HTTP call. No signal permission
        # or container capabilities are needed; a lost parent also closes this pipe.
        os._exit(0)
    Thread(target=watch_parent, daemon=True).start()
    try:
        if core == "experiment":
            from web.experiment import run
            from web.app import FORGED_ROLE, model_client
            if model_client(time.monotonic() + 150) is None:
                connection.send(dict(status="technical_error", error_code="model_not_configured",
                    text="Заполните LLM_BASE_URL, LLM_API_KEY и LLM_MODEL в файле .env и перезапустите веб-сервис.", sources=[]))
                return
            result = run(question, documents)
            if result["status"] in {"out_of_scope", "disallowed"} and FORGED_ROLE.search(latest):
                result["ui_state"] = "role_protection"
            connection.send(result)
            return
        from web.app import answer, EmbeddingClient, Retriever
        retriever = Retriever(documents, fragments)
        if vectors is not None:
            retriever._query_vectors, retriever._dense_lock, retriever._dense_failed = {}, Lock(), False
            retriever.dense = EmbeddingClient(time.monotonic() + 150)
            retriever.vectors = vectors
        state = SimpleNamespace(retriever=retriever, slots=BoundedSemaphore(1))
        connection.send(answer(question, state, latest))
    except Exception:
        connection.send(dict(status="technical_error", text="Не удалось завершить ответ. Повторите вопрос.", sources=[]))
    finally:
        connection.close()


def run_generation(question, latest, state, cancelled):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    control_reader, control_writer = context.Pipe(duplex=False)
    retriever = state.retriever
    vectors = None if getattr(retriever, "_dense_failed", False) else retriever.vectors
    process = context.Process(target=generate, args=(sender, control_reader, question, latest,
                              list(retriever.documents.values()), retriever.fragments, vectors,
                              getattr(state, "core", "prototype")), daemon=True)
    try:
        process.start()
        sender.close()
        control_reader.close()
        deadline = time.monotonic() + 180
        while True:
            if cancelled():
                return dict(status="cancelled", text="Ответ остановлен пользователем.", sources=[])
            if receiver.poll(.15):
                return receiver.recv()
            if not process.is_alive() or time.monotonic() >= deadline:
                return dict(status="technical_error", text="Не удалось завершить ответ. Повторите вопрос.", sources=[])
    finally:
        if process.pid is not None:
            if process.is_alive():
                try:
                    control_writer.send_bytes(b"stop")
                except (BrokenPipeError, OSError):
                    pass
            process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            process.close()
        sender.close()
        receiver.close()
        control_reader.close()
        control_writer.close()

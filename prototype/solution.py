"""Organizer contract: DATA_DIR/questions.csv + knowledge-base.zip -> submission.csv."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import deque
from pathlib import Path
import csv
import os
import sys
import time
import threading
import zipfile
from psb_corpus import load_corpus
from psb_retrieval import Retriever
from psb_llm import EmbeddingClient, ProxyClient, ProviderError, RerankClient, env, integer
from psb_policy import answer_steps, TECHNICAL


def input_directory() -> Path:
    configured = env("DATA_DIR")
    if configured:
        return Path(configured)
    # The organizer sample may run the script from a separate working directory.
    # Select a single directory for both input files, even if its corpus is missing.
    working = Path.cwd()
    default = working / "data"
    for directory in (default, Path(__file__).resolve().parent / "data", working):
        if (directory / "questions.csv").is_file():
            return directory
    return default


def read_questions(path: Path) -> list[tuple[str, str]]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("questions_size_limit")
    csv.field_size_limit(4 * 1024 * 1024)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames or []
        if fields.count("id") != 1 or fields.count("question") != 1:
            raise ValueError("questions_header")
        result = []
        for row in reader:
            if None in row or None in row.values():
                raise ValueError("questions_row")
            result.append((row["id"], row["question"].strip()))
            if len(result) > 50000 or len(row["id"]) > 512:
                raise ValueError("questions_count_or_id_limit")
    if not result or any(not qid.strip() or not question for qid, question in result):
        raise ValueError("empty_question_or_id")
    if len({qid for qid, _ in result}) != len(result):
        raise ValueError("duplicate_question_id")
    return result


def write_output(path: Path, questions: list[tuple[str, str]], answers: list[str]):
    if len(questions) != len(answers):
        raise ValueError("output_row_count")
    temp = path.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["id", "answer"])
        for (qid, _), answer in zip(questions, answers):
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 10000:
                raise ValueError("invalid_output_answer")
            writer.writerow([qid, answer])
    os.replace(temp, path)


def enable_optional_rerank(retriever, deadline):
    """Reranker only on request (PSB_RERANK=1 and RERANKER_MODEL).

    The platform sets RERANKER_MODEL, but its latency is unknown and the
    measured gain was one LegalBench case of 139 (docs/hybrid_retrieval.md),
    so a set model alone does not add a call to every search."""
    if not env("RERANKER_MODEL"):
        return None
    if os.environ.get("PSB_RERANK", "").strip() != "1":
        return "rerank_off"
    try:
        return retriever.enable_rerank(RerankClient(deadline))
    except ProviderError as error:
        return "rerank_disabled:" + str(error)


def run_questions(questions, retriever, deadline, workers, top_k):
    """Yield complete row checkpoints, with a barrier before each retry round.

    Each worker advances one generation/verification step. A verified full answer
    with checked text ends the batch task. Unverified/partial tasks resume only
    after all rows had their first step; a verified answer published as bare
    quotations gets its one text retry last, so it never takes other rows' time.
    """
    queue = deque((index, None, None, None) for index in range(len(questions)))

    def advance(task):
        index, client, steps, checkpoint = task
        try:
            if client is None:
                # A started call is bounded by the run deadline only. A per-row
                # time share shorter than one generation and verification turned
                # every row into a technical error under a slow API (40 rows, 5 s
                # calls, 120 s: 0 answers instead of 21). Fairness comes from the
                # order: one step per row before any retry.
                client = ProxyClient(deadline, position=index)
                steps = answer_steps(questions[index][1], retriever, client, top_k)
            try:
                result = next(steps)
            except StopIteration as finished:
                return index, finished.value, None
            if result["status"] == "answer" and not result.get("quote_only"):
                steps.close()
                return index, result, None
            return index, result, (index, client, steps, result)
        except Exception as error:
            # Safe diagnostics only; preserve any already verified partial answer.
            print("question_error: " + type(error).__name__, file=sys.stderr)
            if steps is not None:
                steps.close()
            return index, checkpoint or {"text": TECHNICAL, "status": "technical_error"}, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and time.monotonic() < deadline:
            pending, deferred = {}, []
            while queue or pending:
                while queue and len(pending) < workers and time.monotonic() < deadline:
                    task = queue.popleft()
                    pending[pool.submit(advance, task)] = task
                if not pending:
                    break
                done, _ = wait(pending, timeout=.5, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    index, result, resume = future.result()
                    if resume is not None:
                        deferred.append(resume)
                    yield index, result["text"], result["status"]
            # Unresolved rows first, then verified partials, then verified answers
            # whose text was dropped (bare quotations).
            queue = deque(sorted(deferred, key=lambda task: ({"partial": 1, "answer": 2}.get(task[3]["status"], 0), task[0])))
        for _, _, steps, _ in queue:
            if steps is not None:
                steps.close()


def main() -> int:
    start = time.monotonic()
    deadline = start + integer("PSB_RUN_SECONDS", 1100, 1, 1150)
    data = input_directory()
    questions = read_questions(data / "questions.csv")
    answers = [TECHNICAL] * len(questions)
    output = Path.cwd() / "submission.csv"
    write_output(output, questions, answers)
    # A socket timeout is an inactivity timeout. A peer trickling headers/body
    # can otherwise keep a worker alive beyond the overall run deadline.
    # Every output replacement is atomic; the last complete CSV always survives.
    def stop_run():
        os.write(2, b"run_deadline: preserved_complete_csv\n")
        os._exit(0)
    watchdog = threading.Timer(max(0., deadline - time.monotonic()), stop_run)
    watchdog.daemon = True
    watchdog.start()
    corpus_path = next((data / name for name in ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")
                        if (data / name).is_file()), None)
    if corpus_path is None:
        watchdog.cancel()
        print("configuration_error: corpus_missing", file=sys.stderr)
        return 2
    try:
        # A single unreadable document is left out, not the whole base: every
        # answer would otherwise be a technical error. Only reason codes are logged.
        skipped = []
        documents, fragments = load_corpus(corpus_path, deadline, skipped=skipped)
        if skipped:
            codes = sorted({code for _, code in skipped})
            print(f"documents_skipped={len(skipped)} reasons=" + ",".join(codes), file=sys.stderr)
        retriever = Retriever(documents, fragments, deadline)
        ProxyClient(deadline)  # Validate once, without disclosing configuration.
    except (ProviderError, ValueError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        watchdog.cancel()
        print("configuration_error: " + type(error).__name__, file=sys.stderr)
        return 2
    # Optional dense candidates: only when the platform names an embedding model.
    # Indexing may take at most a fifth of the run; any failure keeps BM25 only.
    if env("EMB_MODEL"):
        try:
            started_dense = time.monotonic()
            seconds = integer("PSB_DENSE_SECONDS", int(min(240., max(0., (deadline - started_dense) / 5))), 0, 600)
            budget = min(deadline - 60, started_dense + seconds)
            print(retriever.enable_dense(EmbeddingClient(deadline), budget), file=sys.stderr)
        except ProviderError as error:
            print("dense_disabled:" + str(error), file=sys.stderr)
    code = enable_optional_rerank(retriever, deadline)
    if code:
        print(code, file=sys.stderr)
    top_k = integer("TOP_K", 6, 1, 40)
    workers = integer("MAX_WORKERS", 2, 1, 8)

    next_checkpoint = 0.
    for index, text, status in run_questions(questions, retriever, deadline, workers, top_k):
        answers[index] = text
        print(f"completed_position={index} status={status}", file=sys.stderr)
        # Coalesce completed rows instead of rewriting an N-row file N times.
        if time.monotonic() >= next_checkpoint:
            write_output(output, questions, answers)
            next_checkpoint = time.monotonic() + .25
    write_output(output, questions, answers)
    print(f"rows={len(answers)} elapsed_seconds={time.monotonic() - start:.3f}", file=sys.stderr)
    watchdog.cancel()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (ValueError, OSError, csv.Error) as error:
        print("input_error: " + type(error).__name__, file=sys.stderr)
        code = 2
    raise SystemExit(code)

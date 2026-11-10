"""Organizer contract: DATA_DIR/questions.csv + knowledge-base.zip -> submission.csv."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import csv
import os
import sys
import time
from psb_corpus import load_corpus
from psb_retrieval import Retriever
from psb_llm import ProxyClient, ProviderError, env, integer
from psb_policy import answer_question, TECHNICAL


def read_questions(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["id", "question"]:
            raise ValueError("questions_header")
        result = []
        for row in reader:
            if None in row or not isinstance(row.get("question"), str) or not isinstance(row.get("id"), str):
                raise ValueError("questions_row")
            result.append((row["id"].strip(), row["question"].strip()))
    if not result or any(not qid or not question for qid, question in result):
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


def main() -> int:
    start = time.monotonic()
    deadline = start + integer("PSB_RUN_SECONDS", 1100, 1, 1150)
    data = Path(env("DATA_DIR", default="data"))
    questions = read_questions(data / "questions.csv")
    answers = [TECHNICAL] * len(questions)
    output = Path.cwd() / "submission.csv"
    write_output(output, questions, answers)
    corpus_path = next((data / name for name in ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")
                        if (data / name).is_file()), None)
    if corpus_path is None:
        print("configuration_error: corpus_missing", file=sys.stderr)
        return 2
    try:
        documents, fragments = load_corpus(corpus_path)
        retriever = Retriever(documents, fragments)
        ProxyClient(deadline)  # Validate once, without disclosing configuration.
    except (ProviderError, ValueError, OSError) as error:
        print("configuration_error: " + type(error).__name__, file=sys.stderr)
        return 2
    top_k = integer("TOP_K", 6, 1, 40)
    workers = integer("MAX_WORKERS", 2, 1, 8)

    def work(index):
        try:
            text, status = answer_question(questions[index][1], retriever, ProxyClient(deadline), top_k)
            return index, text, status
        except Exception as error:
            # Never log prompts, source bodies, API response bodies or secrets.
            print("question_error: " + type(error).__name__, file=sys.stderr)
            return index, TECHNICAL, "technical_error"

    next_index = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        while next_index < len(questions) and len(pending) < workers:
            future = pool.submit(work, next_index)
            pending[future] = next_index
            next_index += 1
        while pending:
            done, _ = wait(pending, timeout=.5, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                index, text, status = future.result()
                answers[index] = text
                write_output(output, questions, answers)
                print(f"completed_position={index} status={status}", file=sys.stderr)
            while next_index < len(questions) and len(pending) < workers and time.monotonic() < deadline:
                future = pool.submit(work, next_index)
                pending[future] = next_index
                next_index += 1
    print(f"rows={len(answers)} elapsed_seconds={time.monotonic() - start:.3f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

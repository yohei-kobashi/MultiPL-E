#!/usr/bin/env python3
"""
Send every Delphi snippet from the CodeScope dataset to the deployed Lambda evaluator
using the new source/input/output request shape.

The script mirrors the request flow implemented in
`completion_eval_analysis/send_query_to_multipl_eval_server.py`: it loads the
per-language Function URL from `lang2url.json`, checks the `/healthz` endpoint,
and then POSTs evaluation payloads to `/evaluate`. Unlike the original version,
each payload now contains the original Delphi `source_code`, plus a single
testcase's `input` and expected `output`, allowing you to validate the
execution-based grading path.

Example
-------

    python evaluation_aws_lambda/scripts/test_delphi_dataset.py \\
        --dataset datasets/codescope/code_translation_data.jsonl \\
        --lang2url evaluation_aws_lambda/lang2url.json \\
        --output-dir tmp/delphi_lambda_eval \\
        --workers 8
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetEntry:
    raw: Dict[str, Any]

    @property
    def identifier(self) -> str:
        if "id" in self.raw:
            return str(self.raw["id"])
        if "src_uid" in self.raw:
            return str(self.raw["src_uid"])
        return "<unknown>"

    @property
    def source_code(self) -> str:
        return self.raw["source_code"]

    @property
    def testcases(self) -> List[Dict[str, Any]]:
        raw_cases = self.raw.get("testcases", [])
        if isinstance(raw_cases, str):
            try:
                raw_cases = ast.literal_eval(raw_cases)
            except (ValueError, SyntaxError):
                logger.warning("Failed to parse testcases for id=%s; treating as empty", self.identifier)
                return []
        if not isinstance(raw_cases, list):
            logger.warning("Unexpected testcase format for id=%s; treating as empty", self.identifier)
            return []
        normalized_cases: List[Dict[str, Any]] = []
        for case in raw_cases:
            if not isinstance(case, dict):
                continue
            normalized_cases.append(case)
        return normalized_cases


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Delphi dataset programs via the deployed Lambda endpoint."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help="Path to the CodeScope translation dataset (JSONL).",
    )
    parser.add_argument(
        "--lang2url",
        type=Path,
        help="Path to lang2url.json containing the Lambda Function URLs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory where JSONL results will be written.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of concurrent requests to issue.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on the number of Delphi snippets to evaluate.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        help="Timeout in seconds for each evaluate request (mirrors server default).",
    )
    parser.add_argument(
        "--health-retries",
        type=int,
        help="Maximum number of health-check attempts before giving up.",
    )
    parser.add_argument(
        "--health-interval",
        type=float,
        help="Delay in seconds between health-check attempts.",
    )
    parser.set_defaults(
        dataset=Path("datasets/codescope/code_translation_data.jsonl"),
        lang2url=Path("evaluation_aws_lambda/lang2url.json"),
        output_dir=Path("tmp/delphi_lambda_eval"),
        workers=4,
        limit=None,
        request_timeout=610.0,
        health_retries=5,
        health_interval=10.0,
    )
    return parser.parse_args(argv)


def load_delphi_entries(dataset_path: Path, limit: int | None) -> List[DatasetEntry]:
    entries: List[DatasetEntry] = []
    with dataset_path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse JSON on line %d: %s", line_num, exc)
                continue
            if obj.get("source_lang_cluster") != "Delphi":
                continue
            if "source_code" not in obj:
                logger.warning("Skipping line %d (missing source_code field)", line_num)
                continue
            entries.append(DatasetEntry(obj))
            if limit is not None and len(entries) >= limit:
                break
    return entries


def load_lang2url(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = data.get("urls", {})
    if not urls:
        raise ValueError(f"lang2url file {path} does not contain a 'urls' mapping")
    return urls


def check_health(base_url: str, retries: int, interval: float) -> bool:
    health_url = base_url.rstrip("/") + "/healthz"
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(health_url, timeout=5)
        except requests.RequestException as exc:
            logger.warning(
                "Health check attempt %d/%d failed: %s", attempt, retries, exc
            )
        else:
            if res.status_code == requests.codes.ok:
                logger.info("Lambda health check succeeded: %s", health_url)
                return True
            logger.warning(
                "Health check attempt %d/%d returned status %s",
                attempt,
                retries,
                res.status_code,
            )
        if attempt < retries:
            time.sleep(interval)
    return False


def _canonicalize_text(value: str) -> str:
    text = value
    text = text.replace("\\r\\n", "\n")
    text = text.replace("\\r", "")
    text = text.replace("\\n", "\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "")
    return text


def _normalize_case_io(case: Dict[str, Any]) -> tuple[str, List[str]]:
    raw_input = case.get("input", "")
    raw_output = case.get("output", [])

    if isinstance(raw_input, list):
        input_data = raw_input[0] if raw_input else ""
    else:
        input_data = raw_input

    if isinstance(raw_output, list):
        output_data = [str(item) for item in raw_output]
    elif raw_output is None:
        output_data = []
    else:
        output_data = [str(raw_output)]

    input_text = _canonicalize_text(str(input_data))
    output_texts = [_canonicalize_text(str(item)) for item in output_data]

    return input_text, output_texts


def evaluate_entry(
    entry: DatasetEntry,
    evaluate_url: str,
    timeout: float,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, case in enumerate(entry.testcases):
        input_data, expected_output = _normalize_case_io(case)
        if index % 2 == 0:
            # Intentionally corrupt half of the expected outputs to verify error handling.
            if expected_output:
                expected_output = [expected_output[0] + "__forced_mismatch__"] + expected_output[1:]
            else:
                expected_output = ["__forced_mismatch__"]
        payload = {
            "language": "delphi",
            "source_code": entry.source_code,
            "input": input_data,
            "output": expected_output,
            "name": f"codescope_{entry.identifier}_tc{index}",
        }
        start = time.time()
        try:
            response = requests.post(
                evaluate_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=timeout,
            )
            duration = time.time() - start
            result_body: Any
            try:
                result_body = response.json()
            except ValueError:
                result_body = {"raw": response.text}
            results.append(
                {
                    "id": entry.identifier,
                    "testcase_index": index,
                    "http_status": response.status_code,
                    "duration_sec": duration,
                    "payload_name": payload["name"],
                    "response": result_body,
                    "result_status": (
                        (result_body.get("results") or [{}])[0].get("status")
                        if isinstance(result_body, dict)
                        else None
                    ),
                    "matched": (
                        (result_body.get("results") or [{}])[0].get("matched")
                        if isinstance(result_body, dict)
                        else None
                    ),
                    "expected_output": (
                        (result_body.get("results") or [{}])[0].get("expected_output")
                        if isinstance(result_body, dict)
                        else None
                    ),
                }
            )
        except requests.RequestException as exc:
            duration = time.time() - start
            results.append(
                {
                    "id": entry.identifier,
                    "testcase_index": index,
                    "http_status": None,
                    "duration_sec": duration,
                    "payload_name": payload["name"],
                    "error": str(exc),
                    "result_status": None,
                    "matched": None,
                    "expected_output": expected_output,
                }
            )
    return results


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    entries = load_delphi_entries(args.dataset, args.limit)
    if not entries:
        logger.error("No Delphi entries found in %s", args.dataset)
        return 1
    entries = [entry for entry in entries if entry.testcases]
    if not entries:
        logger.error("No Delphi entries with IO testcases found in %s", args.dataset)
        return 1
    total_cases = sum(len(entry.testcases) for entry in entries)
    logger.info(
        "Loaded %d Delphi snippets (%d IO testcases) from %s",
        len(entries),
        total_cases,
        args.dataset,
    )

    lang2url = load_lang2url(args.lang2url)
    base_url = lang2url.get("delphi")
    if not base_url:
        logger.error("No Lambda URL configured for 'delphi' in %s", args.lang2url)
        return 1
    evaluate_url = base_url.rstrip("/") + "/evaluate"

    if not check_health(base_url, args.health_retries, args.health_interval):
        logger.error("Lambda health check failed for %s", base_url)
        return 1

    results_path = args.output_dir / "delphi_lambda_results.jsonl"
    failures = 0
    processed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor, results_path.open(
        "w", encoding="utf-8"
    ) as out_f:
        futures = {
            executor.submit(
                evaluate_entry,
                entry,
                evaluate_url,
                args.request_timeout,
            ): entry
            for entry in entries
        }
        for future in as_completed(futures):
            entry_obj = futures[future]
            entry_id = entry_obj.identifier
            try:
                case_results = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Unhandled exception while processing id=%s", entry_id)
                failures += len(entry_obj.testcases)
                continue
            for res in case_results:
                out_f.write(json.dumps(res, ensure_ascii=False) + "\n")
                processed += 1
                status = res.get("http_status")
                result_status = res.get("result_status")
                matched = res.get("matched")
                expected_output = res.get("expected_output") or []
                is_failure = False
                if status != requests.codes.ok:
                    is_failure = True
                else:
                    if result_status is None or result_status not in ("OK",):
                        is_failure = True
                    if expected_output and matched is False:
                        is_failure = True
                logger.info(
                    "Progress %d/%d — id=%s testcase=%s status=%s",
                    processed,
                    total_cases,
                    entry_id,
                    res.get("testcase_index"),
                    status,
                )
                if is_failure:
                    failures += 1
                    logger.warning(
                        "Request for id=%s testcase=%s failed (http_status=%s, result_status=%s, matched=%s)",
                        entry_id,
                        res.get("testcase_index"),
                        status,
                        result_status,
                        matched,
                    )

    logger.info(
        "Finished evaluation: total_cases=%d, failures=%d, results=%s",
        total_cases,
        failures,
        results_path,
    )
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

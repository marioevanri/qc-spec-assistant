"""Run a question set through the assistant and save the answers for review.

Every answer is saved right away, so a run that stops halfway can be resumed.

Usage (Anaconda Prompt):
    set GEMINI_API_KEY=your-key
    python eval/run_eval.py --set uji --prompt v2
    python eval/run_eval.py --set holdout --prompt v1
    python eval/run_eval.py --set holdout --prompt v2

Results go to eval/hasil_<set>_<prompt>.csv. Run the same command again to
continue after an error, or add --fresh to start that file over.
"""

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

from google import genai
from google.genai import errors

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))

from qc_assistant import DEFAULT_MODEL, ask, build_system_prompt, load_documents  # noqa: E402

FIELDS = ["id", "tipe", "pertanyaan", "jawaban_benar", "sumber", "kata_kunci",
          "model", "prompt", "jawaban_model", "cek_otomatis", "cek_manual"]


class DailyQuotaExceeded(Exception):
    pass


class ServerBusy(Exception):
    pass


def keyword_check(answer: str, keywords: str) -> bool:
    # ";" separates groups that must all appear, "|" separates alternatives inside a group
    text = answer.lower()
    groups = [g for g in keywords.split(";") if g.strip()]
    return all(any(alt.strip().lower() in text for alt in g.split("|")) for g in groups)


def ask_with_retry(client, system_prompt, question, model, tries=3):
    for attempt in range(1, tries + 1):
        try:
            return ask(client, system_prompt, question, model)
        except errors.ClientError as e:
            if e.code != 429:
                raise
            # the daily free tier quota won't come back by waiting a minute
            if "PerDay" in str(e):
                raise DailyQuotaExceeded from e
            print("  kena batas per menit, tunggu 60 detik...")
            time.sleep(60)
        except errors.ServerError:
            # 503 "high demand" is usually gone after a short wait
            print(f"  server Gemini sibuk, tunggu 30 detik (percobaan {attempt}/{tries})...")
            time.sleep(30)
    raise ServerBusy


def load_saved(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def print_summary(rows):
    per_type = defaultdict(lambda: [0, 0])
    for r in rows:
        per_type[r["tipe"]][1] += 1
        per_type[r["tipe"]][0] += r["cek_otomatis"] == "OK"
    for tipe, (ok, total) in per_type.items():
        print(f"{tipe:<13} {ok}/{total}")
    print(f"{'total':<13} {sum(v[0] for v in per_type.values())}/{len(rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["uji", "holdout"], default="uji")
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--delay", type=float, default=7.0, help="seconds between calls")
    parser.add_argument("--fresh", action="store_true", help="delete saved answers and start over")
    args = parser.parse_args()

    out_file = EVAL_DIR / f"hasil_{args.set}_{args.prompt}.csv"
    if args.fresh and out_file.exists():
        out_file.unlink()

    saved = load_saved(out_file)
    done_ids = {r["id"] for r in saved}
    other_models = {r.get("model") or "tidak diketahui" for r in saved} - {args.model}
    if other_models:
        print(f"{out_file.name} berisi jawaban dari model lain ({', '.join(other_models)}).")
        print("Jalankan ulang dengan --fresh supaya semua jawaban dari model yang sama.")
        return

    with open(EVAL_DIR / f"pertanyaan_{args.set}.csv", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))
    todo = [q for q in questions if q["id"] not in done_ids]

    if not todo:
        print("Semua pertanyaan sudah dijawab.")
    else:
        client = genai.Client()  # reads GEMINI_API_KEY from the environment
        system_prompt = build_system_prompt(*load_documents(), version=args.prompt)
        is_new = not out_file.exists()
        # utf-8-sig so Excel shows the characters correctly
        with open(out_file, "a", newline="", encoding="utf-8-sig" if is_new else "utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if is_new:
                writer.writeheader()
            for row in todo:
                print(f"{row['id']} {row['pertanyaan']}")
                try:
                    answer = ask_with_retry(client, system_prompt, row["pertanyaan"], args.model)
                except DailyQuotaExceeded:
                    print(f"\nKuota harian {args.model} habis. Jawaban sebelumnya sudah tersimpan.")
                    print("Jalankan lagi perintah yang sama setelah kuota reset untuk melanjutkan.")
                    break
                except ServerBusy:
                    print("\nServer Gemini masih sibuk. Jawaban sebelumnya sudah tersimpan.")
                    print("Coba lagi beberapa menit lagi dengan perintah yang sama (tanpa --fresh).")
                    break
                writer.writerow({
                    **row,
                    "model": args.model,
                    "prompt": args.prompt,
                    "jawaban_model": answer.strip(),
                    "cek_otomatis": "OK" if keyword_check(answer, row["kata_kunci"]) else "CEK",
                    "cek_manual": "",
                })
                f.flush()
                time.sleep(args.delay)

    rows = load_saved(out_file)
    print(f"\nPrompt {args.prompt}, model {args.model}, terjawab {len(rows)} dari {len(questions)}")
    print_summary(rows)
    print(f"\nHasil di {out_file}")
    print("Cek otomatis cuma pakai kata kunci. Baca tiap jawaban dan isi kolom cek_manual.")


if __name__ == "__main__":
    main()

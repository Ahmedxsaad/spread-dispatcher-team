"""Measures the note reader against what each note really meant: the truth of the cars that we
won, from the reveals. Also writes desk/words.txt, the words that dealers use often, which the
reader repairs typos against.

  python analysis/notes_score.py            score, and show the notes it reads wrong
  python analysis/notes_score.py --words    write desk/words.txt first
"""
from __future__ import annotations

import glob
import re
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, ".")
from desk import notes  # noqa: E402

OPTIONS = ["same_day", "next_day", "within_3_days"]


def labelled() -> pd.DataFrame:
    """One row for each note of an order that we won, with the request and the truth of its first car."""
    rows = []
    for folder in sorted(glob.glob("results/reveals/*/L[5678]-*")):
        requests = pd.read_csv(f"{folder}/requests.csv")
        legs = pd.read_csv(f"{folder}/legs.csv")
        table = requests.merge(legs[legs.leg == 0], left_on="id", right_on="requestId")
        rows.append(table[table.note.notna() & table["truth.readyAt"].notna()])
    return pd.concat(rows, ignore_index=True)


def all_notes() -> pd.Series:
    return pd.concat([pd.read_csv(f"{folder}/requests.csv").note.dropna() for folder in sorted(glob.glob("results/reveals/*/L[5678]-*"))])


def write_words(minimum: int = 25) -> None:
    counts = Counter(word for text in all_notes().drop_duplicates() for word in re.findall(r"[a-z]+", notes.plain(text)))
    words = sorted((word, count) for word, count in counts.items() if count >= 2 and len(word) >= 3)
    with open("desk/words.txt", "w", encoding="utf-8") as file:
        file.write("".join(f"{word} {count}\n" for word, count in words))
    print(f"desk/words.txt: {len(words)} words that at least 2 distinct notes use, {sum(count >= minimum for _, count in words)} of them in {minimum} or more")


def check(row: pd.Series) -> dict:
    """Compares what the reader says with the truth. Each key is a kind of fact: True when right."""
    facts = notes.read({"text": row.note, "language": row.language}, int(row.arrivedAt))
    stated_ready = int(row["pickup.window.from"])
    truth_ready = int(max(row["truth.readyAt"], row["truth.releasedAt"] if pd.notna(row["truth.releasedAt"]) else 0))
    read_ready = max(stated_ready, facts.ready_at or 0)
    deadline = int(row[f"{row.option}.deadline"])
    truth_deadline = int(min(deadline, row["truth.noteDeadline"])) if pd.notna(row["truth.noteDeadline"]) else deadline
    read_deadline = min(deadline, facts.deliver_by) if facts.deliver_by is not None else deadline
    result = {"ready": read_ready == truth_ready, "ready_unsafe": read_ready < truth_ready, "deadline": read_deadline == truth_deadline, "deadline_unsafe": read_deadline > truth_deadline,
              "manual": facts.manual == bool(row["truth.manualGearbox"]), "plates": facts.plates == bool(row["truth.needsPlates"]), "tyres": facts.summer_tyres == bool(row["truth.summerTyres"])}
    for side, opens, closes in (("pickup", facts.pickup_opens, facts.pickup_closes), ("delivery", facts.delivery_opens, facts.delivery_closes)):
        if pd.isna(row[f"{side}.hours.opens"]):
            result[f"{side}_hours"] = True
            continue
        truth = (int(row[f"truth.{side}Hours.opens"]), int(row[f"truth.{side}Hours.closes"]))
        stated = (int(row[f"{side}.hours.opens"]), int(row[f"{side}.hours.closes"]))
        said = (opens if opens is not None else stated[0], closes if closes is not None else stated[1])
        # Hours wider than the stated ones never matter: the site's stated hours still hold.
        said = (max(said[0], stated[0]), min(said[1], stated[1]))
        result[f"{side}_hours"] = said == truth
        result[f"{side}_hours_unsafe"] = said[0] < truth[0] or said[1] > truth[1]
    result["unsure"] = facts.unsure
    return result


def main() -> None:
    if "--words" in sys.argv:
        write_words()
        import importlib
        importlib.reload(notes)
    table = labelled()
    checks = pd.DataFrame([check(row) for _, row in table.iterrows()]).fillna(False)
    kinds = ["ready", "deadline", "pickup_hours", "delivery_hours", "manual", "plates", "tyres"]
    table["right"] = checks[kinds].all(axis=1).values
    table["unsure"] = checks.unsure.values
    sure = ~table.unsure
    print(f"{len(table)} notes of orders that we won, {table.note.nunique()} distinct")
    print(f"read right: {table.right.mean():.2%} | the reader is sure of {sure.mean():.1%} of the notes, and right on {table.right[sure].mean():.2%} of those")
    print("wrong, by kind of fact (all notes / sure notes):", {kind: (int((~checks[kind]).sum()), int((~checks[kind] & sure.values).sum())) for kind in kinds})
    print("wrong in the costly direction, sure notes:", {kind: int((checks[kind] & sure.values).sum()) for kind in ["ready_unsafe", "deadline_unsafe", "pickup_hours_unsafe", "delivery_hours_unsafe"]})
    show = int(next((arg.split("=")[1] for arg in sys.argv if arg.startswith("--show=")), 12))
    for kind in kinds:
        wrong = table[(~checks[kind]).values & sure.values].drop_duplicates("note")
        if len(wrong):
            print(f"\n--- {kind}: {len(wrong)} distinct notes read wrong")
            for _, row in wrong.head(show).iterrows():
                print("   ", row.note, "  =>", {k: v for k, v in vars(notes.read({"text": row.note, "language": row.language}, int(row.arrivedAt))).items() if v})
    unsure = table[table.unsure].drop_duplicates("note")
    print(f"\n--- unsure: {len(unsure)} distinct notes")
    for text in unsure.note.head(show):
        print("   ", text)


if __name__ == "__main__":
    main()

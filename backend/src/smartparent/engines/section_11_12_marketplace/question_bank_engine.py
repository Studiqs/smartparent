"""
STUDIQS Question Bank Builder (Task 10)
=========================================
Stores every successfully mapped question into a persistent, growing question bank.
Deduplication ensures the same question text is never stored twice.

Storage: data/question_bank/question_bank.json (append-only)

Usage:
    # Programmatic
    from src.studiqs.engines.question_bank_engine import QuestionBankEngine
    bank = QuestionBankEngine()
    bank.add_questions(mapped_results)
    bank.save()

    # CLI
    python -m src.studiqs.engines.question_bank_engine --show-stats
"""
import os
import sys
import json
import hashlib
import re
from typing import List, Dict, Optional

from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]


class QuestionBankEngine:
    """
    Task 10: Persistent Question Bank Builder.
    Every uploaded paper grows the Studiqs Question Bank.
    """

    def __init__(self, bank_path: Optional[str] = None):
        if bank_path:
            self.bank_path = bank_path
            self.bank_dir = Path(os.path.dirname(os.path.abspath(bank_path)))
        else:
            self.bank_dir = _find_workspace_root() / "data" / "question_bank"
            self.bank_path = str(self.bank_dir / "question_bank.json")
        self.bank_dir.mkdir(parents=True, exist_ok=True)
        self.questions: List[Dict] = []
        self._hashes: set = set()
        self._load()

    def _load(self):
        """Load existing question bank from disk."""
        if os.path.exists(self.bank_path):
            try:
                with open(self.bank_path, "r", encoding="utf-8") as f:
                    self.questions = json.load(f)
                # Build hash set for deduplication
                for q in self.questions:
                    h = self._hash(q.get("question", ""))
                    self._hashes.add(h)
                print(f"[QuestionBank] Loaded {len(self.questions)} existing questions.")
            except (json.JSONDecodeError, Exception) as e:
                print(f"[QuestionBank] Warning: Could not load bank: {e}. Starting fresh.")
                self.questions = []
                self._hashes = set()
        else:
            print("[QuestionBank] No existing bank found. Creating new one.")

    def _hash(self, text: str) -> str:
        """Generate a hash for deduplication."""
        clean = text.strip().lower()
        # Remove extra whitespace
        clean = " ".join(clean.split())
        return hashlib.md5(clean.encode("utf-8")).hexdigest()

    def add_questions(self, mapped_results: List[Dict], source: str = "unknown") -> int:
        """
        Add mapped questions to the bank.
        Returns the number of NEW questions added (after dedup).
        """
        added = 0
        for r in mapped_results:
            q_text = r.get("question_text", "").strip()
            if not q_text or len(q_text) < 5:
                continue

            h = self._hash(q_text)
            if h in self._hashes:
                continue  # Duplicate

            # Clean class format (e.g., "10th" -> "10")
            class_str = str(r.get("class", "General"))
            class_num = re.sub(r'\D', '', class_str)
            if not class_num:
                class_num = class_str

            entry = {
                "class": class_num,
                "subject": r.get("subject", "General"),
                "topic": r.get("topic", "Unknown"),
                "question": q_text
            }
            self.questions.append(entry)
            self._hashes.add(h)
            added += 1

        print(f"[QuestionBank] Added {added} new questions (skipped {len(mapped_results) - added} duplicates).")
        return added

    def save(self):
        """Save question bank to disk."""
        with open(self.bank_path, "w", encoding="utf-8") as f:
            json.dump(self.questions, f, indent=2, ensure_ascii=False)
        print(f"[QuestionBank] Saved {len(self.questions)} total questions to {self.bank_path}")

    def get_stats(self) -> Dict:
        """Get statistics about the question bank."""
        if not self.questions:
            return {"total_questions": 0}

        subjects = {}
        classes = {}
        boards = {}
        topics = {}

        for q in self.questions:
            subj = q.get("subject", "Unknown")
            cls = q.get("class", "Unknown")
            board = q.get("board", "Unknown")
            topic = q.get("topic", "Unknown")

            subjects[subj] = subjects.get(subj, 0) + 1
            classes[cls] = classes.get(cls, 0) + 1
            boards[board] = boards.get(board, 0) + 1
            topics[topic] = topics.get(topic, 0) + 1

        return {
            "total_questions": len(self.questions),
            "by_subject": dict(sorted(subjects.items(), key=lambda x: -x[1])),
            "by_class": dict(sorted(classes.items())),
            "by_board": dict(sorted(boards.items(), key=lambda x: -x[1])),
            "unique_topics": len(topics),
            "top_10_topics": dict(sorted(topics.items(), key=lambda x: -x[1])[:10]),
        }

    def search(self, query: str, subject: Optional[str] = None,
               grade: Optional[str] = None) -> List[Dict]:
        """Search the question bank."""
        results = []
        query_lower = query.lower()

        for q in self.questions:
            if query_lower not in q.get("question", "").lower():
                continue
            if subject and q.get("subject", "").lower() != subject.lower():
                continue
            if grade and q.get("class", "").lower() != grade.lower():
                continue
            results.append(q)

        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Studiqs Question Bank")
    parser.add_argument("--show-stats", action="store_true", help="Show bank statistics")
    parser.add_argument("--search", type=str, help="Search questions by keyword")
    args = parser.parse_args()

    bank = QuestionBankEngine()

    if args.show_stats:
        stats = bank.get_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        project_root = _find_workspace_root()
        out_dir = project_root / "outputs" / "Task_10_Question_Bank"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / "question_bank_stats.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"\n[QuestionBank] Saved stats to {out_path}")
    elif args.search:
        results = bank.search(args.search)
        print(f"Found {len(results)} results for '{args.search}':")
        for r in results[:10]:
            print(f"  [{r['class']}] {r['subject']} | {r['question'][:80]}...")
    else:
        stats = bank.get_stats()
        print(f"Question Bank: {stats['total_questions']} questions")
"""
Studiqs Question Bank Engine (Task 10)
"""

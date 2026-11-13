"""
STUDIQS Topic Coverage Analyzer (Task 11)
==========================================
Analyzes the Question Bank to find which topics are asked most frequently.
Useful for: Board Readiness, Question Prediction, Revision Planning.

Usage:
    python -m src.studiqs.engines.topic_coverage_engine
    python -m src.studiqs.engines.topic_coverage_engine --subject Mathematics --grade "Class 10"
"""
import os
import json
import csv
from typing import List, Dict, Optional
from collections import Counter
from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]


class TopicCoverageEngine:
    """
    Task 11: Topic Coverage Analyzer.
    Finds which topics are asked most across all papers in the Question Bank.
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
        self._load()

    def _load(self):
        """Load question bank."""
        if os.path.exists(self.bank_path):
            try:
                with open(self.bank_path, "r", encoding="utf-8") as f:
                    self.questions = json.load(f)
                print(f"[TopicCoverage] Loaded {len(self.questions)} questions from bank.")
            except Exception as e:
                print(f"[TopicCoverage] Warning: {e}")
                self.questions = []
        else:
            print("[TopicCoverage] No question bank found. Run pipeline first to populate it.")

    def analyze(self, subject: Optional[str] = None,
                grade: Optional[str] = None,
                board: Optional[str] = None) -> Dict:
        """
        Analyze topic frequency across the question bank.
        Optionally filter by subject, grade, or board.
        """
        filtered = self.questions

        if subject:
            s_match = [q for q in filtered if q.get("subject", "").lower() == subject.lower()]
            if s_match:
                filtered = s_match
        if grade:
            g_match = [q for q in filtered if str(q.get("class", "")).lower() == str(grade).lower()]
            if g_match:
                filtered = g_match
        if board:
            b_match = [q for q in filtered if str(q.get("board", "")).lower() == str(board).lower()]
            if b_match:
                filtered = b_match

        if not filtered:
            return {
                "total_questions": 0,
                "most_frequent_topic": None,
                "coverage": [],
                "filters_applied": {"subject": subject, "grade": grade, "board": board}
            }

        # Count topics
        topic_counter = Counter()
        chapter_counter = Counter()
        for q in filtered:
            topic = q.get("topic", "Unknown")
            chapter = q.get("chapter", "Unknown")
            if topic and topic.lower() not in ("unknown", "unknown topic", "general concept"):
                topic_counter[topic] += 1
            if chapter and chapter.lower() not in ("unknown", "unknown chapter"):
                chapter_counter[chapter] += 1

        # Sort by frequency
        coverage = [
            {"topic": topic, "count": count}
            for topic, count in topic_counter.most_common()
        ]

        chapter_coverage = [
            {"chapter": chapter, "count": count}
            for chapter, count in chapter_counter.most_common()
        ]

        most_frequent = coverage[0]["topic"] if coverage else None

        return {
            "total_questions": len(filtered),
            "unique_topics": len(topic_counter),
            "unique_chapters": len(chapter_counter),
            "most_frequent_topic": most_frequent,
            "coverage": coverage,
            "chapter_coverage": chapter_coverage[:20],
            "filters_applied": {"subject": subject, "grade": grade, "board": board},
        }

    def save_report(self, analysis: Dict, output_dir: Optional[str] = None):
        """Save the coverage report as JSON and CSV."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        out_dir = output_dir or os.path.join(project_root, "outputs", "Task_11_Topic_Coverage")
        os.makedirs(out_dir, exist_ok=True)

        # JSON
        json_path = os.path.join(out_dir, "topic_coverage_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        print(f"[TopicCoverage] JSON report saved: {json_path}")

        # CSV
        csv_path = os.path.join(out_dir, "topic_coverage_report.csv")
        coverage = analysis.get("coverage", [])
        if coverage:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["topic", "count"])
                writer.writeheader()
                writer.writerows(coverage)
            print(f"[TopicCoverage] CSV report saved: {csv_path}")

    def get_prediction_topics(self, subject: Optional[str] = None,
                              grade: Optional[str] = None, top_n: int = 10) -> List[str]:
        """Return top N most frequently asked topics — useful for question prediction."""
        analysis = self.analyze(subject=subject, grade=grade)
        return [item["topic"] for item in analysis.get("coverage", [])[:top_n]]

    def get_revision_plan(self, subject: Optional[str] = None,
                          grade: Optional[str] = None) -> Dict:
        """Generate a revision priority plan based on topic frequency."""
        analysis = self.analyze(subject=subject, grade=grade)
        coverage = analysis.get("coverage", [])

        if not coverage:
            return {"high_priority": [], "medium_priority": [], "low_priority": []}

        # Top 30% = high, middle 40% = medium, bottom 30% = low
        total = len(coverage)
        high_cut = max(1, int(total * 0.3))
        med_cut = max(high_cut + 1, int(total * 0.7))

        return {
            "high_priority": [c["topic"] for c in coverage[:high_cut]],
            "medium_priority": [c["topic"] for c in coverage[high_cut:med_cut]],
            "low_priority": [c["topic"] for c in coverage[med_cut:]],
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Studiqs Topic Coverage Analyzer")
    parser.add_argument("--subject", type=str, help="Filter by subject")
    parser.add_argument("--grade", type=str, help="Filter by grade (e.g., 'Class 10')")
    parser.add_argument("--board", type=str, help="Filter by board")
    parser.add_argument("--save", action="store_true", help="Save report to files")
    args = parser.parse_args()

    engine = TopicCoverageEngine()
    analysis = engine.analyze(subject=args.subject, grade=args.grade, board=args.board)

    print(f"\n{'='*60}")
    print(f"TOPIC COVERAGE ANALYSIS")
    print(f"{'='*60}")
    print(f"Total Questions: {analysis['total_questions']}")
    print(f"Unique Topics: {analysis.get('unique_topics', 0)}")
    print(f"Most Frequent: {analysis.get('most_frequent_topic', 'N/A')}")

    print(f"\nTop 15 Topics:")
    for item in analysis.get("coverage", [])[:15]:
        bar = "#" * min(item["count"], 50)
        print(f"  {item['topic'][:40]:<40s} {item['count']:>4d}  {bar}")

    if args.save:
        engine.save_report(analysis)

    # Revision plan
    plan = engine.get_revision_plan(subject=args.subject, grade=args.grade)
    if plan.get("high_priority"):
        print(f"\nRevision Plan:")
        print(f"  High Priority: {', '.join(plan['high_priority'][:5])}")
        print(f"  Medium Priority: {', '.join(plan['medium_priority'][:5])}")
"""
Studiqs Topic Coverage Engine (Task 11)
"""

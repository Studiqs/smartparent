import json
from datetime import datetime
import pandas as pd
import os
from pathlib import Path
import random

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]

class TopicIntelligenceEngine:
    """
    Topic Intelligence Engine - Week 3
    Generates exact JSON structure with stakeholder recommendations and dashboard outputs.
    """
    def __init__(self):
        print("[Task 7] Initializing Topic Intelligence Engine (Week 3)...")
        
        self.project_root = _find_workspace_root()
        
        # Load external recommendation libraries
        try:
            self.rec_lib_df = pd.read_excel(self.project_root / "data" / "inputs" / "recommendation_library.xlsx")
        except Exception:
            self.rec_lib_df = pd.DataFrame()

        # Stakeholder specific recommendation library (Maha Sri Library style)
        self.stakeholder_recs = {
            "Strong": {
                "student": ["Challenge yourself with higher-order {topic} problems to extend mastery.", "Help peers with {topic} to reinforce your own understanding."],
                "parent": ["Acknowledge the student's strong grasp in {topic}.", "Encourage them to participate in advanced {topic} challenges."],
                "teacher": ["Assign complex {topic} application problems.", "Use the student to peer-tutor {topic} concepts."],
                "management": ["Note excellent performance in {topic} for this class."]
            },
            "Average": {
                "student": ["Review {topic} once a week to consolidate understanding.", "Attempt mixed {topic} problems to bridge partial knowledge gaps."],
                "parent": ["Ensure the student reviews {topic} notes regularly.", "Ask them to explain basic {topic} concepts to you."],
                "teacher": ["Provide targeted {topic} practice to bridge knowledge gaps.", "Monitor progress in upcoming {topic} assessments."],
                "management": ["Observe average performance in {topic} and suggest standard review."]
            },
            "Weak": {
                "student": ["Practice {topic} worksheets regularly — target at least 3 sessions per week.", "Revise {topic} basics and attempt graded problem sets."],
                "parent": ["Encourage the student to revise {topic} twice this week.", "Monitor {topic} homework completion closely."],
                "teacher": ["Provide worksheet practice on {topic} fundamentals.", "Conduct brief {topic} remedial sessions."],
                "management": ["Monitor class-level weakness in {topic}."]
            },
            "Critical": {
                "student": ["Immediately revisit {topic} fundamentals from scratch with guided instruction.", "Use visual aids and concept maps to rebuild {topic} understanding."],
                "parent": ["Your child needs immediate support in {topic}. Schedule additional study time.", "Ensure weekly {topic} practice is completed."],
                "teacher": ["Conduct urgent remedial practice on basic {topic} concepts.", "Assign dedicated {topic} remedial worksheets with step-by-step problem solving."],
                "management": ["Track class-level critical weakness in {topic}. Consider curriculum intervention."]
            }
        }
        
        # Base insights
        self.insight_templates = {
            "Strong": "{topic} is well-mastered — student demonstrates strong understanding.",
            "Average": "{topic} understanding is partial; targeted review can improve performance.",
            "Weak": "{topic} mastery is below expected level.",
            "Critical": "{topic} is a critical topic that needs immediate support"
        }
        
        self.priority_map = {
            "Strong": "Low",
            "Average": "Low",
            "Weak": "Medium",
            "Critical": "High"
        }

    def _get_recs(self, level, topic, subject="General"):
        """Fetch stakeholder recommendations for a topic based on mastery level"""
        # Base fallback templates (with dynamic interpolation)
        recs = self.stakeholder_recs.get(level, self.stakeholder_recs["Average"])
        student_recs = [recs["student"][hash(topic) % len(recs["student"])].format(topic=topic)]
        parent_recs = [recs["parent"][hash(topic) % len(recs["parent"])].format(topic=topic)]
        teacher_recs = [recs["teacher"][hash(topic) % len(recs["teacher"])].format(topic=topic)]
        management_recs = [recs["management"][hash(topic) % len(recs["management"])].format(topic=topic)]

        # Fetch from Maha Sri Recommendation Library if available
        if not self.rec_lib_df.empty:
            # Look for Category=Topic and Subcategory=topic
            topic_matches = self.rec_lib_df[
                (self.rec_lib_df["Category"].str.lower() == "topic") & 
                (self.rec_lib_df["Subcategory"].str.contains(topic, case=False, na=False))
            ]
            for _, row in topic_matches.iterrows():
                stakeholder = str(row.get("Stakeholder", "")).lower()
                rec_text = str(row.get("Recommendation", ""))
                if "student" in stakeholder: student_recs.insert(0, rec_text)
                elif "parent" in stakeholder: parent_recs.insert(0, rec_text)
                elif "teacher" in stakeholder: teacher_recs.insert(0, rec_text)
                elif "management" in stakeholder: management_recs.insert(0, rec_text)

        return {
            "student": list(dict.fromkeys(student_recs)),
            "parent": list(dict.fromkeys(parent_recs)),
            "teacher": list(dict.fromkeys(teacher_recs)),
            "management": list(dict.fromkeys(management_recs))
        }

    def generate_topic_analysis(self, mastery_df) -> list:
        """Builds the exact topic_analysis array for the final JSON"""
        analysis = []
        if mastery_df is None or mastery_df.empty:
            return analysis
            
        for _, row in mastery_df.iterrows():
            topic = row["topic"]
            level = row["mastery_level"]
            score = float(row["score_percent"])
            
            topic_obj = {
                "question_count": int(row.get("question_count", 0)),
                "total_max_marks": float(row.get("total_max_marks", 0)),
                "total_scored_marks": float(row.get("total_scored_marks", 0)),
                "score_percent": round(score, 2),
                "mastery_level": level,
                "priority": self.priority_map.get(level, "Medium"),
                "insight": self.insight_templates.get(level, "").format(topic=topic),
                "recommendations": self._get_recs(level, topic, row.get("subject", "General"))
            }
            
            for key, value in [
                ("subject", row.get("subject", "Unknown")),
                ("chapter", row.get("chapter", "Unknown")),
                ("topic", topic),
                ("topic_id", row.get("topic_id", "Unknown"))
            ]:
                if value and str(value).lower() not in ["unknown", "none", "", "unknown topic", "general", "unknown subject"]:
                    topic_obj[key] = value
                    
            analysis.append(topic_obj)
        return analysis

    def generate_dashboards(self, topic_analysis: list) -> dict:
        """Generates the stakeholder dashboard outputs from the topic analysis"""
        strong = [t.get("topic", "Unknown Topic") for t in topic_analysis if t.get("mastery_level") == "Strong"]
        critical = [t.get("topic", "Unknown Topic") for t in topic_analysis if t.get("mastery_level") == "Critical"]
        weak = [t.get("topic", "Unknown Topic") for t in topic_analysis if t.get("mastery_level") == "Weak"]
        
        priority_topics = critical + weak
        
        student_actions = []
        parent_actions = []
        teacher_actions = []
        management_actions = []
        
        for t in topic_analysis:
            if t.get("mastery_level") in ["Critical", "Weak"]:
                recs = t.get("recommendations", {})
                student_actions.extend(recs.get("student", []))
                parent_actions.extend(recs.get("parent", []))
                teacher_actions.extend(recs.get("teacher", []))
                management_actions.extend(recs.get("management", []))
                
        # Deduplicate
        student_actions = list(dict.fromkeys(student_actions))
        parent_actions = list(dict.fromkeys(parent_actions))
        teacher_actions = list(dict.fromkeys(teacher_actions))
        management_actions = list(dict.fromkeys(management_actions))

        student_hl = f"You need support in {', '.join(priority_topics)}." if priority_topics else "Great job! Keep it up."
        parent_hl = f"Your child needs immediate support in {', '.join(priority_topics)}." if priority_topics else "Your child is performing well."
        teacher_hl = f"Student requires intervention in {', '.join(priority_topics)}." if priority_topics else "Student is meeting expectations."
        management_hl = f"{len(critical)} critical topic and {len(weak)} weak topic detected."
        
        return {
            "student_dashboard": {
                "headline": student_hl,
                "top_strengths": strong,
                "priority_improvements": priority_topics,
                "actions": student_actions[:3]
            },
            "parent_dashboard": {
                "headline": parent_hl,
                "focus_topics": priority_topics,
                "actions": parent_actions[:3]
            },
            "teacher_dashboard": {
                "headline": teacher_hl,
                "remedial_topics": priority_topics,
                "actions": teacher_actions[:3]
            },
            "management_dashboard": {
                "headline": management_hl,
                "risk_topics": critical,
                "actions": management_actions[:3]
            }
        }
        
    def generate_strict_output(self, student_id: str, gap_result: dict) -> dict:
        """
        Generates the strict MVP output format required in Week 3 documentation.
        """
        strong = gap_result.get("strong_topics", [])
        average = gap_result.get("average_topics", [])
        weak = gap_result.get("weak_topics", [])
        critical = gap_result.get("critical_topics", [])
        
        insights = []
        if strong:
            insights.append(f"{strong[0]} is the strongest topic.")
        if critical:
            insights.append(f"{critical[0]} requires immediate attention.")
        if weak and average:
            insights.append(f"Student weak in {weak[0].lower()} and average in {average[0].lower()}.")
            
        recommendations = []
        if critical:
            recommendations.append(f"Practice {critical[0].lower()} problems weekly.")
        if weak:
            recommendations.append(f"Revise {weak[0].lower()} concepts.")
        if average:
            recommendations.append(f"Pay some attention to {average[0].lower()}")
            
        return {
            "student_id": student_id,
            "strong_topics": strong,
            "average_topics": average,
            "weak_topics": weak,
            "critical_topics": critical,
            "insights": insights,
            "recommendations": recommendations
        }

if __name__ == "__main__":
    print("=" * 60)
    print("STUDIQS TOPIC INTELLIGENCE ENGINE (Task 7 & 8)")
    print("=" * 60)

    import pandas as pd
    import os
    from pathlib import Path
    import json

    engine = TopicIntelligenceEngine()
    
    sample_df = pd.DataFrame([
        {"topic": "Algebra", "score_percent": 40.0, "mastery_level": "Weak", "question_count": 5, "total_max_marks": 20, "total_scored_marks": 8},
        {"topic": "Geometry", "score_percent": 100.0, "mastery_level": "Strong", "question_count": 5, "total_max_marks": 20, "total_scored_marks": 20},
        {"topic": "Trigonometry", "score_percent": 20.0, "mastery_level": "Critical", "question_count": 5, "total_max_marks": 20, "total_scored_marks": 4},
        {"topic": "Statistics", "score_percent": 75.0, "mastery_level": "Average", "question_count": 4, "total_max_marks": 16, "total_scored_marks": 12},
    ])
    
    topic_analysis = engine.generate_topic_analysis(sample_df)
    dashboards = engine.generate_dashboards(topic_analysis)
    
    final_output = {
        "topic_analysis": topic_analysis,
        "dashboards": dashboards
    }
    
    print(json.dumps(final_output, indent=2))
    
    try:
        project_root = _find_workspace_root()
        out_dir = project_root / "outputs" / "standalone"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "topic_intelligence_engine_output.json"
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2)
        print(f"\n[Success] Output saved to {out_path}")
    except Exception as e:
        print(f"\n[Error] Could not save output: {e}")

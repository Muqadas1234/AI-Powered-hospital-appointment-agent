from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import FAQ


def get_faq_answer(db: Session, question: str) -> str:
    normalized = question.strip().lower()

    exact_match = (
        db.query(FAQ)
        .filter(func.lower(FAQ.question) == normalized, FAQ.is_active.is_(True))
        .first()
    )
    if exact_match:
        return exact_match.answer

    closest_match = (
        db.query(FAQ)
        .filter(func.lower(FAQ.question).contains(normalized), FAQ.is_active.is_(True))
        .first()
    )
    if closest_match:
        return closest_match.answer

    return "Sorry, I could not find an exact answer. Please ask a staff member."

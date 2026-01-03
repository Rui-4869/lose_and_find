from datetime import UTC, datetime

from database import db


def _now_utc():
    return datetime.now(UTC)


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match_results.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc, nullable=False)

    match = db.relationship("MatchResult", back_populates="messages")
    sender = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "sender_id": self.sender_id,
            "sender": self.sender.username if self.sender else None,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
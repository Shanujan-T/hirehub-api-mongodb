from app.extensions import db
from app.utils import utc_now


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    deleted_for_everyone = db.Column(db.Boolean, default=False, nullable=False)
    deleted_for_sender = db.Column(db.Boolean, default=False, nullable=False)
    deleted_for_receiver = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    conversation = db.relationship("Conversation", back_populates="messages")
    sender = db.relationship("User", back_populates="sent_messages")

    def is_visible_to(self, viewer_id: int) -> bool:
        if self.deleted_for_everyone:
            return True
        if viewer_id == self.sender_id and self.deleted_for_sender:
            return False
        if viewer_id != self.sender_id and self.deleted_for_receiver:
            return False
        return True

    def to_dict(self, include_sender=False, viewer_id=None):
        data = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deleted_for_everyone": self.deleted_for_everyone,
            "deleted_for_sender": self.deleted_for_sender,
            "deleted_for_receiver": self.deleted_for_receiver,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "is_deleted": False,
            "message_type": "text",
        }

        if self.deleted_for_everyone:
            data["content"] = None
            data["is_deleted"] = True
            data["message_type"] = "deleted"
        else:
            data["content"] = self.content

        if include_sender and self.sender:
            data["sender"] = {
                "id": self.sender.id,
                "full_name": self.sender.full_name,
            }

        if viewer_id is not None and not self.is_visible_to(viewer_id):
            return None

        return data

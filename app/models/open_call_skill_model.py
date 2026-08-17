from app.extensions import db


class OpenCallSkill(db.Model):
    __tablename__ = "open_call_skills"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    open_call_id = db.Column(db.Integer, db.ForeignKey("open_calls.id"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)

    open_call = db.relationship("OpenCall", back_populates="open_call_skills")
    skill = db.relationship("Skill")

    __table_args__ = (
        db.UniqueConstraint("open_call_id", "skill_id", name="uq_open_call_skill"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "open_call_id": self.open_call_id,
            "skill_id": self.skill_id,
            "skill": self.skill.to_dict() if self.skill else None,
        }

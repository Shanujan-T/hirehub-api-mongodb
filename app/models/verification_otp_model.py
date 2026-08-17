from app.extensions import db
from app.utils import utc_now


class VerificationOtp(db.Model):
    __tablename__ = "verification_otps"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(32), nullable=False)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", backref=db.backref("verification_otps", lazy="dynamic"))

from werkzeug.security import check_password_hash, generate_password_hash



from app.extensions import db

from app.utils import utc_now





class User(db.Model):

    __tablename__ = "users"



    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    email = db.Column(db.String(255), unique=True, nullable=False)

    password = db.Column(db.String(255), nullable=False)

    role = db.Column(

        db.Enum("admin", "user", "employer", name="user_role"),

        nullable=False,

        default="user",

    )

    full_name = db.Column(db.String(255), nullable=False)

    bio = db.Column(db.Text, nullable=True)

    location = db.Column(db.String(255), nullable=True)

    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    address_city = db.Column(db.String(128), nullable=True)
    address_region = db.Column(db.String(128), nullable=True)
    address_postal_code = db.Column(db.String(32), nullable=True)

    avatar_url = db.Column(db.String(512), nullable=True)

    phone_number = db.Column(db.String(32), nullable=True)
    phone_verified_at = db.Column(db.DateTime, nullable=True)
    email_verified_at = db.Column(db.DateTime, nullable=True)

    nic_number = db.Column(db.String(512), nullable=True)

    nic_document_url = db.Column(db.String(512), nullable=True)

    identity_status = db.Column(

        db.Enum(

            "unverified",

            "pending",

            "verified",

            "rejected",

            name="identity_status",

        ),

        nullable=False,

        default="unverified",

    )

    identity_rejection_reason = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)



    user_skills = db.relationship("UserSkill", back_populates="user", lazy="dynamic")

    community_memberships = db.relationship(

        "CommunityMember", back_populates="user", lazy="dynamic"

    )

    jobs = db.relationship("Job", back_populates="poster", lazy="dynamic")

    contract_applications = db.relationship(

        "ContractApplication", back_populates="member", lazy="dynamic"

    )

    assigned_contracts = db.relationship(

        "Contract",

        back_populates="assigned_member",

        foreign_keys="Contract.assigned_member_id",

        lazy="dynamic",

    )

    reviews_given = db.relationship(

        "Review",

        back_populates="reviewer",

        foreign_keys="Review.reviewer_id",

        lazy="dynamic",

    )

    sent_messages = db.relationship(

        "Message", back_populates="sender", lazy="dynamic"

    )



    def set_password(self, password):

        self.password = generate_password_hash(password)



    def check_password(self, password):

        return check_password_hash(self.password, password)

    def sync_identity_verification_status(self):
        """Set identity_status when phone or email OTP is confirmed (§31)."""
        if self.identity_phone_verified() or self.identity_email_verified():
            self.identity_status = "verified"
            self.identity_rejection_reason = None

    def identity_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def identity_phone_verified(self) -> bool:
        return self.phone_verified_at is not None



    def to_dict(

        self,

        include_stats=False,

        include_skills=False,

        viewer_role=None,

        viewer_id=None,

    ):

        data = {

            "id": self.id,

            "email": self.email,

            "role": self.role,

            "full_name": self.full_name,

            "bio": self.bio,

            "location": self.location,

            "avatar_url": self.avatar_url,

            "identity_status": self.identity_status,

            "is_active": self.is_active,

            "created_at": self.created_at.isoformat() if self.created_at else None,

        }



        is_self = viewer_id is not None and viewer_id == self.id

        is_platform_admin = viewer_role == "admin"



        if is_self and self.identity_status == "rejected" and self.identity_rejection_reason:

            data["identity_rejection_reason"] = self.identity_rejection_reason

        if is_self:
            data["phone_number"] = self.phone_number
            data["email_verified_for_identity"] = self.identity_email_verified()
            data["phone_verified_for_identity"] = self.identity_phone_verified()
            if self.phone_verified_at:
                data["phone_verified_at"] = self.phone_verified_at.isoformat()
            if self.email_verified_at:
                data["email_verified_at"] = self.email_verified_at.isoformat()
            data["address_line1"] = self.address_line1
            data["address_line2"] = self.address_line2
            data["address_city"] = self.address_city
            data["address_region"] = self.address_region
            data["address_postal_code"] = self.address_postal_code
            data["community_memberships"] = [
                m.to_dict() for m in self.community_memberships
            ]

        if is_platform_admin and not is_self:
            data["address_line1"] = self.address_line1
            data["address_line2"] = self.address_line2
            data["address_city"] = self.address_city
            data["address_region"] = self.address_region
            data["address_postal_code"] = self.address_postal_code



        if include_skills:

            data["user_skills"] = [us.to_dict() for us in self.user_skills.all()]

        if include_stats:

            from app.models.contract_model import Contract



            completed = Contract.query.filter_by(

                assigned_member_id=self.id, status="completed"

            ).count()

            data["completed_project_count"] = completed

            from sqlalchemy import func

            from app.models.review_model import Review



            avg_rating = (

                db.session.query(func.avg(Review.rating))

                .filter(Review.member_id == self.id)

                .scalar()

            )

            data["rating"] = round(float(avg_rating), 2) if avg_rating else 0.0

        return data

from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask.ctx import RequestContext

# Compatibility patch for Flask 3.1+ RequestContext.session setter removal (Flask-SocketIO compatibility)
if getattr(RequestContext.session, "fset", None) is None:
    original_prop = RequestContext.session
    RequestContext.session = original_prop.setter(
        lambda self, value: setattr(self, "_session", value)
    )

db = SQLAlchemy()
jwt = JWTManager()
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")

'use strict';
const jwt = require('jsonwebtoken');
const { jwtSecret } = require('../config');
const { User, Community, CommunityMember } = require('../models');

async function authenticate(req, res, next) {
  const header = req.get('authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ msg: 'Missing Authorization Header' });
  try {
    const payload = jwt.verify(token, jwtSecret);
    const id = Number(payload.sub);
    const user = await User.findOne({ id });
    if (!user) return res.status(401).json({ error: 'Unauthorized.' });
    req.user = user; req.userId = id;
    next();
  } catch (_) { return res.status(401).json({ msg: 'Token has expired or is invalid' }); }
}

function optionalAuth(req, _res, next) {
  const header = req.get('authorization') || '';
  if (!header.startsWith('Bearer ')) return next();
  try { req.jwt = jwt.verify(header.slice(7), jwtSecret); } catch (_) { /* optional */ }
  return next();
}

const rolesRequired = (...roles) => [authenticate, (req, res, next) => roles.includes(req.user.role) ? next() : res.status(403).json({ error: 'Forbidden.' })];

function communityAdminRequired(param = 'community_id') {
  return async (req, res, next) => {
    const communityId = Number(req.params[param]);
    const community = await Community.findOne({ id: communityId });
    const member = await CommunityMember.findOne({ community_id: communityId, user_id: req.userId, role: 'admin', status: 'approved' });
    if (!community || (community.admin_id !== req.userId && !member)) return res.status(403).json({ error: 'Community admin access required.' });
    next();
  };
}

module.exports = { authenticate, optionalAuth, rolesRequired, communityAdminRequired };

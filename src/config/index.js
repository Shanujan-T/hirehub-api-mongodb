'use strict';
const path = require('node:path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env') });

module.exports = {
  mongodbUri: process.env.MONGODB_URI,
  jwtSecret: process.env.JWT_SECRET_KEY || 'dev-secret-key',
  jwtExpiresMinutes: Number(process.env.JWT_ACCESS_TOKEN_EXPIRES_MINUTES || 1440),
  port: Number(process.env.PORT || 5000),
  clientUrl: process.env.CLIENT_URL || '*',
};

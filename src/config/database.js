'use strict';
const dns = require('node:dns');
const mongoose = require('mongoose');
const { mongodbUri } = require('./index');

async function connectDatabase() {
  if (!mongodbUri) throw new Error('MONGODB_URI is required.');
  if (mongodbUri.startsWith('mongodb+srv://') && dns.getServers().every(server => ['127.0.0.1', '::1'].includes(server))) {
    dns.setServers((process.env.MONGODB_DNS_SERVERS || '1.1.1.1,8.8.8.8').split(',').map(value => value.trim()).filter(Boolean));
  }
  mongoose.set('strictQuery', true);
  await mongoose.connect(mongodbUri);
  return mongoose.connection;
}

module.exports = { connectDatabase };

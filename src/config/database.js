'use strict';
const dns = require('node:dns');
const mongoose = require('mongoose');
const { mongodbUri, mongodbConnectTimeoutMs } = require('./index');

async function connectDatabase() {
  if (!mongodbUri) throw new Error('MONGODB_URI is required.');
  if (mongodbUri.startsWith('mongodb+srv://') && dns.getServers().every(server => ['127.0.0.1', '::1'].includes(server))) {
    dns.setServers((process.env.MONGODB_DNS_SERVERS || '1.1.1.1,8.8.8.8').split(',').map(value => value.trim()).filter(Boolean));
  }
  mongoose.set('strictQuery', true);
  await mongoose.connect(mongodbUri, {
    serverSelectionTimeoutMS: mongodbConnectTimeoutMs,
    connectTimeoutMS: mongodbConnectTimeoutMs,
  });
  return mongoose.connection;
}

function databaseState() {
  return {
    ready: mongoose.connection.readyState === 1,
    state: ['disconnected', 'connected', 'connecting', 'disconnecting'][mongoose.connection.readyState] || 'unknown',
  };
}

module.exports = { connectDatabase, databaseState };

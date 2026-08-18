'use strict';
const dns = require('node:dns');
const mongoose = require('mongoose');
const { mongodbUri, mongodbConnectTimeoutMs } = require('./index');

let connectionPromise = null;

async function connectDatabase() {
  if (!mongodbUri) throw new Error('MONGODB_URI is required.');
  if (mongoose.connection.readyState === 1) return mongoose.connection;
  if (mongoose.connection.readyState === 2 && connectionPromise) return connectionPromise;
  connectionPromise = null;
  if (mongodbUri.startsWith('mongodb+srv://') && dns.getServers().every(server => ['127.0.0.1', '::1'].includes(server))) {
    dns.setServers((process.env.MONGODB_DNS_SERVERS || '1.1.1.1,8.8.8.8').split(',').map(value => value.trim()).filter(Boolean));
  }
  mongoose.set('strictQuery', true);
  connectionPromise = mongoose.connect(mongodbUri, {
    serverSelectionTimeoutMS: mongodbConnectTimeoutMs,
    connectTimeoutMS: mongodbConnectTimeoutMs,
  }).then(() => mongoose.connection).catch(error => {
    connectionPromise = null;
    throw error;
  });
  return connectionPromise;
}

function databaseState() {
  return {
    ready: mongoose.connection.readyState === 1,
    state: ['disconnected', 'connected', 'connecting', 'disconnecting'][mongoose.connection.readyState] || 'unknown',
  };
}

module.exports = { connectDatabase, databaseState };

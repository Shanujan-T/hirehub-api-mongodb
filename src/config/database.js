'use strict';
const mongoose = require('mongoose');
const { mongodbUri } = require('./index');

async function connectDatabase() {
  if (!mongodbUri) throw new Error('MONGODB_URI is required.');
  mongoose.set('strictQuery', true);
  await mongoose.connect(mongodbUri);
  return mongoose.connection;
}

module.exports = { connectDatabase };

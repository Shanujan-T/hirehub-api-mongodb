'use strict';
const http = require('node:http');
const { Server } = require('socket.io');
const app = require('./app');
const { connectDatabase } = require('./src/config/database');
const { port, mongodbRetryDelayMs } = require('./src/config');
const { registerSocket } = require('./src/socket');
const { startSchedulers } = require('./src/scheduler');

const server = http.createServer(app);
const io = new Server(server, { cors: app.get('corsOptions') });
app.set('io', io);
registerSocket(io);

server.on('error', error => {
  console.error(`HTTP server error (${error.code || 'unknown'}): ${error.message}`);
});
server.listen(port, '0.0.0.0', () => {
  console.log(`HireHub API listening on 0.0.0.0:${port}`);
});

let retryTimer = null;
let schedulerStarted = false;
const connectWithRetry = async () => {
  try {
    await connectDatabase();
    console.log('MongoDB connected.');
    if (!schedulerStarted) {
      startSchedulers();
      schedulerStarted = true;
    }
  } catch (error) {
    console.error(`MongoDB connection failed: ${error.message}`);
    console.error(`Retrying MongoDB connection in ${mongodbRetryDelayMs}ms.`);
    retryTimer = setTimeout(connectWithRetry, mongodbRetryDelayMs);
    retryTimer.unref();
  }
};
void connectWithRetry();

const shutdown = signal => {
  console.log(`${signal} received; shutting down.`);
  if (retryTimer) clearTimeout(retryTimer);
  server.close(() => process.exit(0));
};
process.once('SIGTERM', () => shutdown('SIGTERM'));
process.once('SIGINT', () => shutdown('SIGINT'));

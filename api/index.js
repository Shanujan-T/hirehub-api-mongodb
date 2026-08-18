'use strict';

const app = require('../src/application');

module.exports = function handler(req, res) {
  return app(req, res);
};

'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const crypto=require('node:crypto');const passwords=require('../src/utils/password');
test('new bcrypt hashes verify',async()=>{const hash=await passwords.hash('secret123');assert.equal(await passwords.verify('secret123',hash),true);assert.equal(await passwords.verify('wrong',hash),false);});
test('legacy Werkzeug pbkdf2 hashes verify',async()=>{const password='secret123',salt='legacy-salt',iterations=1000,hash=crypto.pbkdf2Sync(password,salt,iterations,32,'sha256').toString('hex');const encoded=`pbkdf2:sha256:${iterations}$${salt}$${hash}`;assert.equal(await passwords.verify(password,encoded),true);assert.equal(await passwords.verify('wrong',encoded),false);});

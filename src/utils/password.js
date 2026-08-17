'use strict';
const crypto=require('node:crypto');const bcrypt=require('bcryptjs');
async function verify(password,encoded){
 if(!encoded)return false;if(encoded.startsWith('$2'))return bcrypt.compare(String(password),encoded);
 const parts=encoded.split('$');if(parts.length!==3)return false;const [method,salt,expected]=parts;
 try{
  if(method.startsWith('scrypt:')){const [N,r,p]=method.slice(7).split(':').map(Number);const actual=await new Promise((resolve,reject)=>crypto.scrypt(String(password),salt,64,{N,r,p,maxmem:256*N*r},(e,key)=>e?reject(e):resolve(key.toString('hex'))));return crypto.timingSafeEqual(Buffer.from(actual),Buffer.from(expected));}
  if(method.startsWith('pbkdf2:')){const [,digest='sha256',iterations='260000']=method.split(':');const actual=crypto.pbkdf2Sync(String(password),salt,Number(iterations),Math.ceil(expected.length/2),digest).toString('hex');return crypto.timingSafeEqual(Buffer.from(actual),Buffer.from(expected));}
 }catch{return false;}return false;
}
const hash=password=>bcrypt.hash(String(password),12);
module.exports={verify,hash};

'use strict';
const cloudinary=require('cloudinary').v2;
const ALLOWED=new Set(['image/jpeg','image/png','image/webp','image/gif']);
function validate(file){if(!file)return 'image is required.';if(!ALLOWED.has(file.mimetype))return 'Only JPEG, PNG, WEBP, and GIF images are allowed.';if(file.size>10*1024*1024)return 'Image must be 10 MB or smaller.';return null;}
async function upload(file,folder){
  const error=validate(file);if(error){const e=new Error(error);e.code='INVALID_UPLOAD';throw e;}
  if(process.env.CLOUDINARY_CLOUD_NAME&&process.env.CLOUDINARY_API_KEY&&process.env.CLOUDINARY_API_SECRET){cloudinary.config({cloud_name:process.env.CLOUDINARY_CLOUD_NAME,api_key:process.env.CLOUDINARY_API_KEY,api_secret:process.env.CLOUDINARY_API_SECRET});return new Promise((resolve,reject)=>{const stream=cloudinary.uploader.upload_stream({folder,resource_type:'image'},(e,r)=>e?reject(e):resolve(r.secure_url));stream.end(file.data);});}
  throw new Error('Image storage is not configured.');
}
module.exports={validate,upload};

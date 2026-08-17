'use strict';
async function askAi(system, prompt, maxTokens=500) {
  const key=String(process.env.OPENROUTER_API_KEY||'').trim();
  if(!key)return null;
  const response=await fetch('https://openrouter.ai/api/v1/chat/completions',{method:'POST',headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify({model:process.env.OPENROUTER_MODEL||'openai/gpt-4o-mini',messages:[{role:'system',content:system},{role:'user',content:prompt}],max_tokens:maxTokens}),signal:AbortSignal.timeout(30000)});
  if(!response.ok)return null;const data=await response.json();return data.choices?.[0]?.message?.content?.trim()||null;
}
function parseObject(text){if(!text)return null;try{return JSON.parse(text.replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,''));}catch{return null;}}
module.exports={askAi,parseObject};

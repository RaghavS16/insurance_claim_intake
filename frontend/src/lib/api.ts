export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export class ApiError extends Error { status:number; payload:any; constructor(message:string,status=500,payload:any=null){super(message);this.status=status;this.payload=payload;} }
export async function api<T=any>(path:string,init:RequestInit & {skipAuth?:boolean}={}):Promise<T>{
 const {skipAuth,...requestInit}=init;
 const headers=new Headers(requestInit.headers||{});
 if(!skipAuth && typeof window!=="undefined"){const token=localStorage.getItem("access_token");if(token)headers.set("Authorization","Bearer "+token)}
 if(requestInit.body && !(requestInit.body instanceof FormData))headers.set("Content-Type","application/json");
 const res=await fetch(API_BASE+path,{...requestInit,headers,credentials:requestInit.credentials||"include"});
 const text=await res.text();let payload:any=null;try{payload=text?JSON.parse(text):null}catch{payload=text}
 if(!res.ok)throw new ApiError(payload?.detail||payload?.message||"Request failed ("+res.status+")",res.status,payload);
 return payload as T;
}

"use client";
import { useEffect, useRef, useState } from "react";
import { Menu, MessageCircle, Mic, Plus, Send, Upload, X } from "lucide-react";
import { API_BASE, api } from "@/lib/api";

type Source={citation_label?:string;source_name?:string;document_type?:string;page_number?:number;section_number?:string;clause_number?:string;chunk_id?:string;document_version?:string;text?:string};
type ChatMessage={id?:string;role:"user"|"assistant";text:string;citations?:Source[];grounded?:boolean;attachment?:any};
type Conversation={ticket_id:string;status:string;insurance_type?:string;updated_at?:string;last_message?:string;turn_count?:number};

function sourceLabel(s:Source){ return s.citation_label || s.source_name || s.chunk_id || "Source"; }

export function ClaimantChat(){
  const [conversations,setConversations]=useState<Conversation[]>([]);
  const [ticket,setTicket]=useState("");
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [draft,setDraft]=useState("");
  const [loading,setLoading]=useState(true);
  const [sending,setSending]=useState(false);
  const [uploading,setUploading]=useState(false);
  const [voiceState,setVoiceState]=useState<"idle"|"starting"|"listening"|"thinking"|"speaking"|"error">("idle");
  const [error,setError]=useState("");
  const [showSources,setShowSources]=useState<Record<string,boolean>>({});
  const [mobileHistory,setMobileHistory]=useState(false);
  const pcRef=useRef<RTCPeerConnection|null>(null);
  const mediaRef=useRef<MediaStream|null>(null);
  const audioRef=useRef<HTMLAudioElement|null>(null);
  const socketRef=useRef<WebSocket|null>(null);
  const heartbeatRef=useRef<ReturnType<typeof setInterval>|null>(null);
  const callRef=useRef("");
  const creatingRef=useRef<Promise<string>|null>(null);

  function cleanupVoice(){
    if(heartbeatRef.current)clearInterval(heartbeatRef.current);
    heartbeatRef.current=null;
    socketRef.current?.close();
    socketRef.current=null;
    mediaRef.current?.getTracks().forEach(t=>t.stop());
    mediaRef.current=null;
    pcRef.current?.close();
    pcRef.current=null;
    callRef.current="";
    setVoiceState("idle");
  }

  useEffect(()=>()=>cleanupVoice(),[]);

  async function loadConversations(preferred?:string){
    const data=await api<any>("/api/v1/claims?limit=100");
    const items=(data.items||[]) as Conversation[];
    setConversations(items);
    const next=preferred || ticket || items[0]?.ticket_id || "";
    if(next) {
      await openConversation(next);
      return;
    }
    setMessages([]);
    if(!items.length) await createChat();
  }

  async function openConversation(id:string){
    if(!id)return;
    cleanupVoice();
    setTicket(id); setMobileHistory(false);
    try{
      const rows=await api<any[]>("/api/v1/claims/"+encodeURIComponent(id)+"/conversation");
      setMessages((rows||[]).map((m:any):ChatMessage=>({role:m.speaker==="user"?"user":"assistant",text:m.text||"",attachment:m.attachment})).filter(x=>x.text));
      setError("");
    }catch(e:any){setError(e.message||"Unable to open conversation.");}
  }

  async function createChat():Promise<string>{
    if(creatingRef.current) return creatingRef.current;
    const task=(async()=>{
      cleanupVoice();setMobileHistory(false);
      setError("");
      const data=await api<any>("/api/v1/claims/new-session",{method:"POST",body:JSON.stringify({})});
      const welcome:ChatMessage={role:"assistant",text:data.initial_message||"Tell me what happened, in your own words. I'll collect the details as we go."};
      setTicket(data.ticket_id);
      setMessages([welcome]);
      setConversations(v=>[{ticket_id:data.ticket_id,status:data.status||"draft",insurance_type:data.insurance_type,updated_at:new Date().toISOString(),last_message:welcome.text,turn_count:1},...v.filter(x=>x.ticket_id!==data.ticket_id)]);
      return String(data.ticket_id);
    })();
    creatingRef.current=task;
    try { return await task; } finally { creatingRef.current=null; }
  }

  useEffect(()=>{
    let alive=true;
    setLoading(true);
    loadConversations().catch((e:any)=>alive&&setError(e.message||"Unable to load conversations.")).finally(()=>alive&&setLoading(false));
    return()=>{alive=false;};
  },[]);

  async function sendText(){
    const text=draft.trim();
    if(!text||sending)return;
    let activeTicket=ticket;
    if(!activeTicket) activeTicket=await createChat();
    if(!activeTicket) return;
    setDraft("");
    setMessages(v=>[...v,{id:"local-"+Date.now(),role:"user",text}]);
    setSending(true);setError("");
    try{
      const r=await api<any>("/api/v1/claims/"+encodeURIComponent(activeTicket)+"/text-turn",{method:"POST",body:JSON.stringify({text})});
      setMessages(v=>[...v,{role:"assistant",text:r.agent_message||"Received.",citations:r.citations||r.sources||[],grounded:r.grounded}]);
      setConversations(v=>v.map(x=>x.ticket_id===activeTicket?{...x,last_message:r.agent_message||"Received.",updated_at:new Date().toISOString(),status:r.status||x.status,turn_count:(x.turn_count||0)+2}:x));
    }catch(e:any){setError(e.message||"Your message could not be processed.");}
    finally{setSending(false);}
  }

  async function upload(file:File){
    if(!ticket)return;
    setUploading(true);setError("");
    try{
      const fd=new FormData();fd.append("file",file);
      const r=await api<any>("/api/v1/claims/"+encodeURIComponent(ticket)+"/evidence",{method:"POST",body:fd});
      setMessages(v=>[...v,{role:"user",text:"Uploaded evidence: "+file.name,attachment:{name:file.name}},{role:"assistant",text:r.message||"Evidence received and added to this claim."}]);
    }catch(e:any){setError(e.message||"Evidence upload failed.");}
    finally{setUploading(false);}
  }

  async function startVoice(){
    let activeTicket=ticket || "";
    if(!activeTicket){
      activeTicket=await createChat();
    }
    if(!activeTicket)return;
    cleanupVoice();setVoiceState("starting");setError("");
    try{
      const token=localStorage.getItem("access_token");
      if(!token)throw new Error("Your session has expired. Please sign in again.");
      const session=await api<any>("/api/v1/voice/realtime/session/"+encodeURIComponent(activeTicket),{method:"POST"});
      if(window.isSecureContext===false) throw new Error("Voice requires HTTPS or localhost. Open the secure application URL and try again.");
      if(!navigator.mediaDevices?.getUserMedia) throw new Error("This browser does not provide microphone access.");
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      const peer=new RTCPeerConnection({iceServers:(session.ice_servers||[]).map((x:any)=>({urls:x.urls}))});
      pcRef.current=peer;mediaRef.current=stream;
      stream.getTracks().forEach(t=>peer.addTrack(t,stream));
      peer.ontrack=(ev)=>{const remote=ev.streams?.[0];if(remote&&audioRef.current){audioRef.current.srcObject=remote;audioRef.current.play().catch(()=>{});}};
      peer.onconnectionstatechange=()=>{if(["failed","disconnected","closed"].includes(peer.connectionState)){setVoiceState("error");setError("Voice connection dropped. Your same conversation remains available by text.");}};
      const wsBase=API_BASE.replace(/^http/,"ws");
      const ws=new WebSocket(wsBase+"/api/v1/voice/events/"+encodeURIComponent(activeTicket));
      socketRef.current=ws;
      ws.onopen=()=>ws.send(JSON.stringify({type:"auth",token}));
      ws.onmessage=(ev)=>{
        try{
          const event=JSON.parse(ev.data);
          if(event.event_type==="voice.state"){
            if(event.state==="listening"||event.state==="thinking"||event.state==="speaking")setVoiceState(event.state);
          }
          if(event.event_type==="voice.user.final"&&event.text)setMessages(v=>[...v,{role:"user",text:event.text}]);
          if(event.event_type==="voice.agent.final"&&event.text)setMessages(v=>[...v,{role:"assistant",text:event.text,citations:event.citations||event.sources||[],grounded:event.grounded}]);
          if(event.event_type==="voice.error"){setVoiceState("error");setError("Voice processing failed; continue this exact conversation by typing.");}
        }catch{/* ignore malformed event */}
      };
      ws.onerror=()=>setError("Voice event stream is unavailable; audio may still connect. Text remains available.");
      const offer=await peer.createOffer();
      await peer.setLocalDescription(offer);
      await new Promise<void>((resolve,reject)=>{
        if(peer.iceGatheringState==="complete"){resolve();return;}
        const timer=window.setTimeout(()=>{peer.removeEventListener("icegatheringstatechange",onState);resolve();},5000);
        const onState=()=>{if(peer.iceGatheringState==="complete"){window.clearTimeout(timer);peer.removeEventListener("icegatheringstatechange",onState);resolve();}};
        peer.addEventListener("icegatheringstatechange",onState);
      });
      const local=peer.localDescription;
      if(!local?.sdp) throw new Error("WebRTC could not prepare local media candidates.");
      const answer=await api<any>("/api/v1/voice/realtime/offer/"+encodeURIComponent(session.call_id),{method:"POST",body:JSON.stringify({ticket_id:activeTicket,sdp:local.sdp,type:local.type})});
      await peer.setRemoteDescription(answer);
      callRef.current=session.call_id;
      setVoiceState("listening");
      heartbeatRef.current=setInterval(()=>{api("/api/v1/voice/heartbeat/"+encodeURIComponent(activeTicket)+"/"+encodeURIComponent(session.call_id),{method:"POST"}).catch(()=>{})},30000);
    }catch(e:any){cleanupVoice();setVoiceState("error");setError(e.message||"Voice is unavailable. Continue this conversation with text.");}
  }

  async function stopVoice(){
    try{if(ticket)await api("/api/v1/voice/close/"+encodeURIComponent(ticket),{method:"POST"});}catch{/* local cleanup always runs */}
    cleanupVoice();
  }

  const selected=conversations.find(x=>x.ticket_id===ticket);
  return <div className="claimant-chat-shell">
    <aside className={"chat-history"+(mobileHistory?" mobile-open":"")} aria-label="Claim conversations">
      <div className="chat-history-head"><div><div className="chat-brand">Claims</div><div className="chat-history-sub">Your conversations</div></div><button className="icon-btn" onClick={createChat} aria-label="New chat"><Plus size={17}/></button></div>
      <button className="new-chat-btn" onClick={createChat}><Plus size={15}/>New chat</button>
      <div className="chat-history-list">
        {conversations.map(c=><button key={c.ticket_id} className={"chat-history-item"+(c.ticket_id===ticket?" active":"")} onClick={()=>openConversation(c.ticket_id)}>
          <div className="chat-history-title">{c.insurance_type?c.insurance_type.replaceAll("_"," "):"Claim conversation"}</div>
          <div className="chat-history-meta">{c.ticket_id}</div>
          <div className="chat-history-preview">{c.last_message||"No messages yet."}</div>
        </button>)}
        {!conversations.length&&!loading&&<div className="chat-history-empty">No conversations yet.</div>}
      </div>
    </aside>
    <main className="claim-chat-main">
      <header className="claim-chat-topbar"><button className="chat-history-toggle" onClick={()=>setMobileHistory(v=>!v)} aria-label="Toggle chat history"><Menu size={17}/></button><div><div className="claim-chat-title">{selected?.insurance_type?selected.insurance_type.replaceAll("_"," "):"Insurance claim assistant"}</div><div className="claim-chat-status">{ticket||"Start a new claim conversation"}</div></div>{ticket&&<span className="chat-status-pill">{voiceState==="listening"?"Voice active":selected?.status||"draft"}</span>}</header>
      <div className="claim-chat-scroll">
        {loading?<div className="chat-skeleton" aria-label="Loading conversations"><div/><div/><div/></div>:messages.map((m,i)=><div key={m.id||i} className={"claim-chat-message "+(m.role==="user"?"mine":"theirs")}>
          <div className="claim-chat-avatar">{m.role==="user"?"You":"AI"}</div>
          <div className="claim-chat-content">
            <div className="claim-chat-bubble">{m.text}</div>
            {m.citations?.length?<div className="citation-wrap"><button className="citation-toggle" onClick={()=>setShowSources(x=>({...x,[String(i)]:!x[String(i)]}))}>Sources ({m.citations.length})</button>{showSources[String(i)]&&<div className="citation-list">{m.citations.slice(0,6).map((s,j)=><div className="citation-item" key={j}><b>{sourceLabel(s)}</b><span>{s.page_number?"p. "+s.page_number+" · ":""}{s.clause_number?"Clause "+s.clause_number:""}{s.document_version?" · v"+s.document_version:""}</span></div>)}</div>}</div>:null}
          </div>
        </div>)}
        {!messages.length&&!loading?<div className="chat-empty"><MessageCircle size={34}/><h2>Start your claim conversation</h2><p>Speak first, type when you prefer, and attach evidence without leaving this thread.</p><button className="btn primary" onClick={createChat}><Plus size={14}/>New chat</button></div>:null}
        {sending&&<div className="typing-indicator"><span/><span/><span/>AI is thinking</div>}
      </div>
      <audio ref={audioRef} autoPlay playsInline className="sr-only"/>
      {error&&<div className="chat-error" role="alert"><span>{error}</span><button onClick={()=>setError("")} aria-label="Dismiss"><X size={15}/></button></div>}
      <div className="claim-chat-composer">
        <label className="composer-attach" aria-label="Attach evidence"><Upload size={18}/><input type="file" hidden disabled={!ticket||uploading} onChange={e=>{const f=e.target.files?.[0];if(f)upload(f);e.currentTarget.value=""}}/></label>
        <button className={"voice-primary "+(voiceState!=="idle"&&voiceState!=="error"?"active":"")} onClick={voiceState==="listening"||voiceState==="thinking"||voiceState==="speaking"?stopVoice:startVoice} disabled={voiceState==="starting"} aria-label={voiceState==="listening"?"Stop voice":"Start voice"}><Mic size={21}/></button>
        <textarea value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendText()}}} placeholder="Ask a question or describe what happened…" aria-label="Message claim assistant"/>
        <button className="composer-send" onClick={sendText} disabled={!draft.trim()||sending||!ticket} aria-label="Send message"><Send size={18}/></button>
      </div>
      <div className="composer-hint">Voice is the primary input. Text is always available as a fallback. Policy and regulatory answers show their sources.</div>
    </main>
  </div>;
}

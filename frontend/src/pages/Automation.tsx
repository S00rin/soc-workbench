import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, useToast } from "../lib";

const NEW_FEED = { name:"", url:"", source_type:"rss", category:"Threat Intelligence",
  trust_score:0.7, interval_minutes:60, enabled:true, auto_save_kb:true,
  auto_extract_iocs:true, summarize:false };
const NEW_IOC = { name:"", url:"", adapter:"threatfox", trust_score:0.7,
  interval_minutes:60, enabled:true, configuration:{} };

export default function Automation() {
  const [intel,setIntel]=useState<any[]|null>(null);
  const [iocs,setIocs]=useState<any[]|null>(null);
  const [tasks,setTasks]=useState<any[]|null>(null);
  const [feed,setFeed]=useState<any>(NEW_FEED);
  const [feedId,setFeedId]=useState<number|null>(null);
  const [ioc,setIoc]=useState<any>(NEW_IOC);
  const [iocId,setIocId]=useState<number|null>(null);
  const [task,setTask]=useState({title:"",workspace:"",prompt:"",mode:"read-only"});
  const [busy,setBusy]=useState("");
  const toast=useToast();

  async function load() {
    try {
      const [a,b,c]=await Promise.all([
        api.get("/api/automation/intel-sources"),
        api.get("/api/automation/ioc-sources"),
        api.get("/api/automation/claude-tasks"),
      ]);
      setIntel(a); setIocs(b); setTasks(c);
    } catch(e:any){toast(e.message,"error");}
  }
  useEffect(()=>{load(); const id=setInterval(load,5000); return()=>clearInterval(id);},[]);

  async function run(path:string,label:string) {
    setBusy(label);
    try { const out=await api.post(path); toast(JSON.stringify(out),"ok"); await load(); }
    catch(e:any){toast(e.message,"error");} finally{setBusy("");}
  }
  async function saveFeed() {
    if(!feed.name||!feed.url)return toast("Name and URL are required","error");
    try {
      if(feedId) await api.put(`/api/automation/intel-sources/${feedId}`,feed);
      else await api.post("/api/automation/intel-sources",feed);
      setFeed({...NEW_FEED}); setFeedId(null); await load(); toast("News source saved","ok");
    } catch(e:any){toast(e.message,"error");}
  }
  async function saveIoc() {
    if(!ioc.name||!ioc.url)return toast("Name and URL are required","error");
    try {
      if(iocId) await api.put(`/api/automation/ioc-sources/${iocId}`,ioc);
      else await api.post("/api/automation/ioc-sources",ioc);
      setIoc({...NEW_IOC}); setIocId(null); await load(); toast("IoC source saved","ok");
    } catch(e:any){toast(e.message,"error");}
  }
  async function remove(kind:"intel"|"ioc",id:number) {
    if(!confirm("Delete this source?"))return;
    try { await api.del(`/api/automation/${kind}-sources/${id}`); await load(); }
    catch(e:any){toast(e.message,"error");}
  }
  async function submitTask() {
    if(!task.prompt||!task.workspace)return toast("Workspace and prompt are required","error");
    try {
      await api.post("/api/automation/claude-tasks",{...task,title:task.title||"Claude Code task",timeout_seconds:600,max_turns:10});
      setTask(x=>({...x,title:"",prompt:""})); await load(); toast("Claude Code task queued","ok");
    } catch(e:any){toast(e.message,"error");}
  }
  if(!intel||!iocs||!tasks)return <Loading/>;

  return <>
    <div className="card mb">
      <div className="card-head"><h3>Automatic IoC pipeline</h3><div className="row">
        <button className="btn-sm" disabled={!!busy}
          onClick={()=>run("/api/automation/knowledge-to-iocs","kb")}>
          {busy==="kb"?"Scanning…":"Scan all Knowledge Base now"}
        </button>
        <button className="btn-primary btn-sm" disabled={!!busy}
          onClick={()=>run("/api/automation/run-all","all")}>
          {busy==="all"?"Running…":"Run all feeds now"}
        </button>
      </div></div>
      <p className="dim">Every hour the scheduler refreshes enabled news and IoC feeds, then scans every Knowledge Base item. Only valid IP, domain, URL, email, and hash indicators are transferred to the IoC repository. Both operations can also be started on demand.</p>
    </div>

    <div className="card mb"><div className="card-head"><h3>News and research feeds</h3></div>
      <div className="field-row"><div><label>Name</label><input value={feed.name} onChange={e=>setFeed({...feed,name:e.target.value})}/></div>
        <div><label>RSS/Atom URL</label><input className="mono" value={feed.url} onChange={e=>setFeed({...feed,url:e.target.value})}/></div>
        <div><label>Trust (0–1)</label><input type="number" min="0" max="1" step=".05" value={feed.trust_score} onChange={e=>setFeed({...feed,trust_score:+e.target.value})}/></div>
        <div><label>Interval minutes</label><input type="number" min="15" value={feed.interval_minutes} onChange={e=>setFeed({...feed,interval_minutes:+e.target.value})}/></div>
      </div>
      <div className="row mb"><label className="row"><input type="checkbox" style={{width:"auto"}} checked={feed.enabled} onChange={e=>setFeed({...feed,enabled:e.target.checked})}/> Enabled</label>
        <label className="row"><input type="checkbox" style={{width:"auto"}} checked={feed.auto_save_kb} onChange={e=>setFeed({...feed,auto_save_kb:e.target.checked})}/> Save to KB</label>
        <label className="row"><input type="checkbox" style={{width:"auto"}} checked={feed.auto_extract_iocs} onChange={e=>setFeed({...feed,auto_extract_iocs:e.target.checked})}/> Extract IoCs</label>
        <label className="row"><input type="checkbox" style={{width:"auto"}} checked={feed.summarize} onChange={e=>setFeed({...feed,summarize:e.target.checked})}/> Claude summary</label>
        <button className="btn-primary btn-sm" onClick={saveFeed}>{feedId?"Update":"Add"} source</button>
        {feedId&&<button className="btn-sm" onClick={()=>{setFeedId(null);setFeed({...NEW_FEED});}}>Cancel</button>}
      </div>
      <table className="data"><thead><tr><th>Source</th><th>Trust</th><th>Enabled</th><th>Last success/error</th><th/></tr></thead>
      <tbody>{intel.map(x=><tr key={x.id}><td>{x.name}<div className="dim mono">{x.url}</div></td><td>{x.trust_score}</td><td>{x.enabled?"Yes":"No"}</td>
        <td className="dim">{x.last_error||x.last_success_at||"Never"}</td><td><div className="row">
          <button className="btn-sm" onClick={()=>run(`/api/automation/intel-sources/${x.id}/run`,"n"+x.id)}>Run</button>
          <button className="btn-sm" onClick={()=>{setFeedId(x.id);setFeed({name:x.name,url:x.url,source_type:x.source_type,category:x.category,trust_score:x.trust_score,interval_minutes:x.interval_minutes,enabled:x.enabled,auto_save_kb:x.auto_save_kb,auto_extract_iocs:x.auto_extract_iocs,summarize:x.summarize});}}>Edit</button>
          <button className="btn-sm btn-danger" onClick={()=>remove("intel",x.id)}>Delete</button></div></td></tr>)}</tbody></table>
    </div>

    <div className="card mb"><div className="card-head"><h3>IoC feeds</h3></div>
      <div className="field-row"><div><label>Name</label><input value={ioc.name} onChange={e=>setIoc({...ioc,name:e.target.value})}/></div>
        <div><label>Feed/API URL</label><input className="mono" value={ioc.url} onChange={e=>setIoc({...ioc,url:e.target.value})}/></div>
        <div><label>Adapter</label><select value={ioc.adapter} onChange={e=>setIoc({...ioc,adapter:e.target.value})}><option>threatfox</option><option>urlhaus_text</option><option>cisa_kev</option></select></div>
        <div><label>Trust</label><input type="number" min="0" max="1" step=".05" value={ioc.trust_score} onChange={e=>setIoc({...ioc,trust_score:+e.target.value})}/></div></div>
      <div className="row mb"><label className="row"><input type="checkbox" style={{width:"auto"}} checked={ioc.enabled} onChange={e=>setIoc({...ioc,enabled:e.target.checked})}/> Enabled</label>
        <button className="btn-primary btn-sm" onClick={saveIoc}>{iocId?"Update":"Add"} IoC source</button>
        {iocId&&<button className="btn-sm" onClick={()=>{setIocId(null);setIoc({...NEW_IOC});}}>Cancel</button>}</div>
      <table className="data"><thead><tr><th>Source</th><th>Adapter</th><th>Trust</th><th>Last success/error</th><th/></tr></thead>
      <tbody>{iocs.map(x=><tr key={x.id}><td>{x.name}<div className="dim mono">{x.url}</div></td><td>{x.adapter}</td><td>{x.trust_score}</td>
        <td className="dim">{x.last_error||x.last_success_at||"Never"}</td><td><div className="row">
          <button className="btn-sm" onClick={()=>run(`/api/automation/ioc-sources/${x.id}/run`,"i"+x.id)}>Run</button>
          <button className="btn-sm" onClick={()=>{setIocId(x.id);setIoc({name:x.name,url:x.url,adapter:x.adapter,trust_score:x.trust_score,interval_minutes:x.interval_minutes,enabled:x.enabled,configuration:x.configuration||{}});}}>Edit</button>
          <button className="btn-sm btn-danger" onClick={()=>remove("ioc",x.id)}>Delete</button></div></td></tr>)}</tbody></table>
    </div>

    <div className="card"><div className="card-head"><h3>Claude Code tasks</h3></div>
      <div className="field-row"><div><label>Title</label><input value={task.title} onChange={e=>setTask({...task,title:e.target.value})}/></div>
        <div><label>Workspace</label><input className="mono" value={task.workspace} onChange={e=>setTask({...task,workspace:e.target.value})}/></div>
        <div><label>Mode</label><select value={task.mode} onChange={e=>setTask({...task,mode:e.target.value})}><option value="plan">Plan</option><option value="read-only">Read only</option><option value="edit">Edit files</option></select></div></div>
      <label>Prompt</label><textarea style={{minHeight:130}} value={task.prompt} onChange={e=>setTask({...task,prompt:e.target.value})}/>
      <button className="btn-primary btn-sm mb" onClick={submitTask}>Run with Claude Code</button>
      <table className="data"><thead><tr><th>Task</th><th>Mode</th><th>Status</th><th>Changed files</th><th>Result</th></tr></thead>
      <tbody>{tasks.map(x=><tr key={x.id}><td>{x.title}</td><td>{x.mode}</td><td><span className="badge">{x.status}</span></td><td className="mono">{(x.changed_files||[]).join(", ")||"—"}</td><td style={{maxWidth:420,whiteSpace:"pre-wrap"}}>{x.error||x.output||"—"}</td></tr>)}</tbody></table>
    </div>
  </>;
}

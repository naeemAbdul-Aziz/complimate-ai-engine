const API_BASE = window.API_BASE || "http://localhost:8000";

const qs = (s)=>document.querySelector(s);
const j = (o)=>JSON.stringify(o,null,2);

// Health
qs('#btn-health').addEventListener('click', async ()=>{
  try{
    const r = await fetch(`${API_BASE}/health`);
    const data = await r.json();
    qs('#health-out').textContent = j(data);
  }catch(err){
    qs('#health-out').textContent = `Error: ${err}`;
  }
});

let lastFileId = null;

// Upload
qs('#btn-upload').addEventListener('click', async ()=>{
  const file = qs('#file-input').files[0];
  if(!file){
    alert('Select a file first');
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  try{
    const r = await fetch(`${API_BASE}/upload`, { method:'POST', body: fd });
    if(!r.ok){
      const t = await r.text();
      throw new Error(t);
    }
    const data = await r.json();
    lastFileId = data.file_id;
    qs('#file-id').textContent = data.file_id;
    qs('#file-path').textContent = data.file_path;
    qs('#btn-analyze').disabled = !lastFileId;
  }catch(err){
    alert(`Upload failed: ${err}`);
  }
});

// Analyze
let pollTimer = null;
qs('#btn-analyze').addEventListener('click', async ()=>{
  if(!lastFileId){
    alert('Upload a file first');
    return;
  }
  try{
    const r = await fetch(`${API_BASE}/analysis/start`, {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ file_id: lastFileId, priority: 'normal', include_universal_clauses: true })
    });
    if(!r.ok){
      const t = await r.text();
      throw new Error(t);
    }
    const data = await r.json();
    qs('#analysis-id').textContent = data.analysis_id;
    qs('#status').textContent = data.status;
    qs('#progress').textContent = 'Starting...';
    // start polling
    if(pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async ()=>{
      try{
        const s = await fetch(`${API_BASE}/analysis/${data.analysis_id}/status`);
        const st = await s.json();
        qs('#status').textContent = st.status;
        qs('#progress').textContent = st.progress;
        if(st.report_paths){
          const { json_file, txt, pdf } = st.report_paths;
          qs('#reports').innerHTML = `
            <a href="${json_file}" target="_blank">JSON</a> · 
            <a href="${txt}" target="_blank">TXT</a> · 
            <a href="${pdf}" target="_blank">PDF</a>`;
        }
        const statusUpper = String(st.status).toUpperCase();
        if(statusUpper === 'COMPLETED' || statusUpper === 'FAILED' || statusUpper === 'ERROR'){
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }catch(e){
        console.warn('Status polling error', e);
      }
    }, 1500);
  }catch(err){
    alert(`Start analysis failed: ${err}`);
  }
});

// WebSocket
qs('#btn-ws-connect').addEventListener('click', ()=>{
  const aid = qs('#ws-analysis-id').value.trim();
  if(!aid){ alert('Enter analysis_id'); return; }
  const wsUrl = API_BASE.replace('http', 'ws') + `/ws/analysis/${aid}`;
  const ws = new WebSocket(wsUrl);
  ws.onopen = ()=>{ qs('#ws-out').textContent += `\n[open] ${wsUrl}`; };
  ws.onmessage = (e)=>{ try{ qs('#ws-out').textContent += `\n` + JSON.stringify(JSON.parse(e.data)); }catch{ qs('#ws-out').textContent += `\n` + e.data; } };
  ws.onerror = (e)=>{ qs('#ws-out').textContent += `\n[error] ${e.message||e}`; };
  ws.onclose = ()=>{ qs('#ws-out').textContent += `\n[close]`; };
});

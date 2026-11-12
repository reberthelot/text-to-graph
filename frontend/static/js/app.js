'use strict';
const $ = id => document.getElementById(id);
const DATA_KEY = 'dtu-text-to-graph-cases-v1';
const SETTINGS_KEY = 'dtu-text-to-graph-settings-v1';
let cases = [], selected = 0, results = [], running = false, stopRequested = false, batchSettings = null;
const emptyGraph = () => ({'@context': {'@base':'https://example.org/keyboards/extraction/reference/','kb':'https://keyboards.wikibase.cloud/entity/','kbt':'https://keyboards.wikibase.cloud/prop/direct/','rdfs':'http://www.w3.org/2000/01/rdf-schema#'}, '@graph':[]});
const pretty = value => JSON.stringify(value, null, 2);
const pct = value => (100 * value).toFixed(1) + '%';

function status(message, error = false) { $('status').textContent = message; $('status').className = error ? 'error' : ''; }

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail || result));
  return result;
}

function persist() {
  try { localStorage.setItem(DATA_KEY, JSON.stringify(cases)); }
  catch (_) { status('Browser storage is unavailable. Export the dataset to keep edits.', true); }
}

function settings() {
  const timeout = Number($('timeout').value), parallel = Number($('parallel').value);
  if (!Number.isInteger(parallel) || parallel < 1 || parallel > 8) throw new Error('Parallel calls must be an integer from 1 to 8.');
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 300) throw new Error('Timeout must be from 1 to 300 seconds.');
  const endpoint = $('endpoint').value.trim();
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify({endpoint,timeout,parallel})); } catch (_) {}
  return {endpoint, timeout, parallel};
}

function updateOptions() {
  $('cases').replaceChildren();
  cases.forEach((item, index) => { const option = document.createElement('option'); option.value = index; option.textContent = (index + 1) + '. ' + item.name; $('cases').append(option); });
  $('cases').value = selected;
}

function clearResults() { results = []; $('batch').hidden = true; }

function commit() {
  const reference = JSON.parse($('reference').value);
  if (!reference || !Array.isArray(reference['@graph']) || !reference['@context']) throw new Error('Reference needs @context and an @graph array.');
  if (!$('text').value.trim()) throw new Error('Input text is empty.');
  const next = {name:$('name').value.trim() || 'Untitled case', text:$('text').value, reference};
  if (JSON.stringify(next) !== JSON.stringify(cases[selected])) clearResults();
  cases[selected] = next;
  persist(); updateOptions();
}

function showCase(index, result) {
  selected = index; $('cases').value = index;
  const item = cases[index];
  $('name').value = item.name; $('text').value = item.text; $('reference').value = pretty(item.reference);
  $('prediction').value = result && result.prediction !== undefined ? pretty(result.prediction) : '';
  $('score').hidden = true;
  if (result && result.score) showScore(result.score, result.elapsed_seconds);
  if (result && (result.error || result.validation_error)) status(result.error || result.validation_error, true);
}

function table(headers, rows, className = '') {
  const node = document.createElement('table'); node.className = className;
  const head = node.createTHead().insertRow(); headers.forEach(h => { const th = document.createElement('th'); th.textContent = h; head.append(th); });
  const body = node.createTBody();
  rows.forEach(values => { const row = body.insertRow(); values.forEach(value => { const td = row.insertCell(); td.textContent = value === null ? 'Unmatched' : value; }); });
  return node;
}

function showScore(score, seconds) {
  $('score').hidden = false; $('metrics').replaceChildren();
  [['Precision',pct(score.precision)],['Recall',pct(score.recall)],['F1',pct(score.f1)],['TP / FP / FN',`${score.tp} / ${score.fp} / ${score.fn}`]].forEach(([label,value]) => {
    const div = document.createElement('div'); div.className = 'metric';
    const strong = document.createElement('strong'); strong.textContent = value;
    const span = document.createElement('span'); span.textContent = label; div.append(strong,span); $('metrics').append(div);
  });
  $('score-note').textContent = `${score.predicted_triples} predicted · ${score.reference_triples} reference triples` + (seconds === undefined ? '' : ` · ${seconds.toFixed(2)} s HTTP time`) + (score.exact ? ' · optimal local-node alignment' : ' · alignment budget reached: scores are lower bounds');
  $('score-note').className = score.exact ? 'subtle' : 'notice';
  $('diff').replaceChildren();
  [['missing','Missing reference triples'],['extra','Extra predicted triples'],['matched','Matched triples']].forEach(([key,title]) => {
    const details = document.createElement('details'); details.open = key !== 'matched' && score[key].length > 0;
    const summary = document.createElement('summary'); summary.textContent = `${title} (${score[key].length})`;
    const wrap = document.createElement('div'); wrap.className = 'scroll';
    wrap.append(table(['Subject','Predicate','Object'],score[key],'triples')); details.append(summary,wrap); $('diff').append(details);
  });
  $('alignment').replaceChildren(table(['Prediction node','Reference node'],score.alignment.map(row => [row.prediction,row.reference])));
}

function busy(value) {
  running = value;
  ['run-all','extract','compare','save','add','remove','import','export','reset','cases','name','text','reference','prediction','endpoint','timeout','parallel'].forEach(id => { $(id).disabled = value; });
  $('stop').disabled = !value;
  $('report').disabled = value;
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function loadServer() {
  const data = await api('api/dataset'); cases = data.cases; selected = 0; clearResults(); persist(); updateOptions(); showCase(0);
  $('source').textContent = data.sample ? 'Bundled sample: three specification examples.' : 'Loaded from ' + data.source;
  status(data.sample ? 'Ready. Import keyboards.txt to use your full dataset.' : `Ready. ${cases.length} cases loaded.`);
}
$('cases').addEventListener('change', () => {
  const next = Number($('cases').value);
  try { commit(); showCase(next, results[next]); } catch (error) { $('cases').value = selected; status('Save valid reference JSON before changing case: ' + error.message, true); }
});
$('save').onclick = () => { try { commit(); status('Case saved in this browser.'); } catch (error) { status(error.message,true); } };

$('add').onclick = () => {
    try {
  commit();
  cases.push({name:'New case',text:'Describe a keyboard here.',reference:emptyGraph()});
  clearResults(); selected=cases.length-1; persist(); updateOptions(); showCase(selected); }
    catch (error) { status(error.message, true); } };

$('remove').onclick = () => {
  if (cases.length < 2) return status('Keep at least one case, or import a replacement dataset.',true);
  if (!confirm('Delete this case from the browser dataset?')) return;
  cases.splice(selected,1); selected = Math.min(selected,cases.length-1); clearResults(); persist(); updateOptions(); showCase(selected); status('Case deleted.');
};
$('reset').onclick = async () => { if (!confirm('Replace browser edits with the server dataset? Export first to keep edits.')) return; try { await loadServer(); } catch (error) { status(error.message,true); } };
$('import').onchange = async event => {
  try {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 5_000_000) throw new Error('Dataset file exceeds 5 MB.');
    const data = await api('api/dataset/parse',{content:await file.text()});
    cases=data.cases; selected=0; clearResults(); persist(); updateOptions(); showCase(0);
    $('source').textContent = 'Imported ' + file.name; status(`Imported ${cases.length} cases.`);
  } catch (error) { status(error.message,true); } finally { event.target.value=''; }
};
$('export').onclick = () => { try { commit(); download('keyboards.txt',cases.map(item => item.text.trim()+'\n\n'+pretty(item.reference)).join('\n\n')+'\n','text/plain;charset=utf-8'); status('Dataset exported.'); } catch (error) { status(error.message,true); } };
$('compare').onclick = async () => {
  try { commit(); const prediction = JSON.parse($('prediction').value); busy(true); status('Comparing RDF graphs…'); const score = await api('api/compare',{prediction,reference:cases[selected].reference}); showScore(score); status(score.exact ? 'Comparison complete.' : 'Comparison complete with lower-bound scores.'); }
  catch (error) { $('score').hidden=true; status(error.message,true); } finally { busy(false); }
};
$('extract').onclick = async () => {
  try {
    commit(); const config=settings(); busy(true); $('score').hidden=true; $('prediction').value=''; status('Calling student service…');
    const result = await api('api/extract',{...config,text:cases[selected].text,reference:cases[selected].reference});
    $('prediction').value=pretty(result.prediction);
    if (result.validation_error) throw new Error(result.validation_error);
    showScore(result.score,result.elapsed_seconds); status('Extraction and comparison complete.');
  } catch (error) { status(error.message,true); } finally { busy(false); }
};
function renderBatch() {
  const scored=results.filter(item=>item && item.score), attempted=results.filter(Boolean).length;
  const errors=results.filter(item=>item && !item.score).length;
  const tp=scored.reduce((sum,item)=>sum+item.score.tp,0), fp=scored.reduce((sum,item)=>sum+item.score.fp,0), fn=scored.reduce((sum,item)=>sum+item.score.fn,0);
  const micro=2*tp+fp+fn ? 2*tp/(2*tp+fp+fn) : 1;
  const precision=tp+fp ? tp/(tp+fp) : (fn ? 0 : 1), recall=tp+fn ? tp/(tp+fn) : 1;
  const macro=scored.length ? scored.reduce((sum,item)=>sum+item.score.f1,0)/scored.length : 0;
  const bounded=scored.some(item=>!item.score.exact);
  $('batch-summary').textContent=`${attempted}/${cases.length} attempted · ${scored.length} scored · ${errors} failed · ${cases.length-attempted} not run.` + (scored.length ? ` Scored cases only: micro P ${pct(precision)}, R ${pct(recall)}, F1 ${pct(micro)}; macro F1 ${pct(macro)}. TP/FP/FN ${tp}/${fp}/${fn}.` : '') + (bounded ? ' Alignment limits reached: aggregate scores are lower bounds.' : '');
  $('batch-rows').replaceChildren();
  cases.forEach((item,index) => {
    const result=results[index], score=result && result.score, row=document.createElement('tr');
    const cell=document.createElement('td'), button=document.createElement('button'); button.className='compact'; button.textContent=(index+1)+'. '+item.name; button.disabled=running;
    button.onclick=()=>{ try { commit(); showCase(index,results[index]); $('text').scrollIntoView({behavior:'smooth',block:'center'}); } catch (error) { status(error.message,true); } }; cell.append(button); row.append(cell);
    const values=score ? [pct(score.precision),pct(score.recall),pct(score.f1),`${score.tp} / ${score.fp} / ${score.fn}`,result.elapsed_seconds.toFixed(2)+' s',score.exact?'Scored':'Lower bound'] : ['—','—','—','—','—',result ? (result.error || result.validation_error || 'Failed') : 'Not run'];
    values.forEach(value=>{ const td=document.createElement('td'); td.textContent=value; row.append(td); }); $('batch-rows').append(row);
  });
}
$('run-all').onclick = async () => {
  try {
    commit(); const config=settings(); batchSettings={...config}; busy(true); stopRequested=false; results=new Array(cases.length); $('batch').hidden=false;
    let next=0; renderBatch();
    async function worker() {
      while (!stopRequested && next<cases.length) {
        const index=next++, item=cases[index]; status(`Running case ${index+1}/${cases.length}: ${item.name}`);
        try { results[index]=await api('api/extract',{...config,text:item.text,reference:item.reference}); }
        catch (error) { results[index]={error:error.message}; }
        renderBatch();
      }
    }
    await Promise.all(Array.from({length:Math.min(config.parallel,cases.length)},worker));
    status(stopRequested?'Batch stopped. Active calls have finished.':'Batch complete.');
  } catch (error) { status(error.message,true); }
  finally { busy(false); renderBatch(); }
};
$('stop').onclick = () => { stopRequested=true; $('stop').disabled=true; status('Stopping: waiting for active calls; no more cases will start.'); };
$('report').onclick = () => download('text-to-graph-report.json',pretty({created_at:new Date().toISOString(),settings:batchSettings,cases:cases.map((item,index)=>({...item,result:results[index] || null}))}),'application/json');
async function init() {
  // Default endpoint from the environment (STUDENT_URL), e.g. Compose DNS in Docker.
  try { $('endpoint').value = (await (await fetch('api/config')).json()).student_url; } catch (_) {}
  try {
    const config=JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null');
    if (config) for (const id of ['endpoint','timeout','parallel']) $(id).value=config[id];
    const saved=JSON.parse(localStorage.getItem(DATA_KEY) || 'null');
    if (Array.isArray(saved) && saved.length && saved.every(item=>typeof item.text==='string' && typeof item.name==='string' && item.reference && Array.isArray(item.reference['@graph']))) {
      cases=saved; updateOptions(); showCase(0); $('source').textContent='Restored browser dataset.'; status(`Ready. ${cases.length} cases restored from this browser.`); return;
    }
  } catch (_) { /* A blocked or corrupt browser store does not prevent startup. */ }
  try { await loadServer(); } catch (error) { status(error.message,true); }
}
init();

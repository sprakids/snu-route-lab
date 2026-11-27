// Preserve every published versioned dataset; restore only the default v7 UI/model.
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib'),crypto=require('node:crypto'),util=require('node:util');
const root=path.resolve(__dirname,'..'),work=__dirname;
const base=path.join(root,'deployment/weekday_operations_release_261110002926');
const old=path.join(root,'deployment/rollback_v7_261110005327_staging');
const target=path.join(root,'deployment/rollback_v7_261110005327_with_history');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const all=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?all(path.join(d,e.name)):[path.join(d,e.name)]);
const comp=util.promisify(z.brotliCompress);
(async()=>{
 const decision=JSON.parse(fs.readFileSync(path.join(work,'pilot-decision.json')));
 if(decision.status!=='REJECTED_REVERT_TO_V7')throw Error('Rollback condition not satisfied');
 if(fs.existsSync(target))throw Error('Preserve existing staging; do not overwrite');
 fs.cpSync(base,target,{recursive:true});
 // The v7 snapshot preserves original current-time1x behavior, defaults and docs.
 for(const f of all(path.join(old,'public'))){
  const rel=path.relative(path.join(old,'public'),f);
  if(rel.startsWith('data'+path.sep))continue;
  const dest=path.join(target,'public',rel);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.copyFileSync(f,dest);
 }
 const names={'admin_snu_1653':'16:53 행정관 셔틀','culture_1655':'16:55 문화관입구','snu_gate_1703':'17:03 서울대학교21128'};
 const r=decision,table=r.v7.map((v,i)=>`| ${names[v.id]} | ${v.people_interval.join('~')} | ${v.uniform_minute_mean.toFixed(2)} | ${r.v8[i].uniform_minute_mean.toFixed(2)} | ${r.candidate[i].uniform_minute_mean.toFixed(2)} |`).join('\n');
 const md=`# 정문 대기열 오차 분석과 v7 복원

도착 시각을 보정한 후보가 사전에 정한 기준을 통과하지 못해 운영 계산을 이전 v7으로 복원했습니다. v8과 교정 후보의 원문·실험 로그는 보존했습니다. 수요·정원을 임의로 바꾸지 않았습니다.

## 원인에서 확인한 것

v8은 관측된 배차간격 분포를 적용했지만, 실제 차량의 절대 도착시각을 그대로 재생한 모형은 아니었습니다. 17:03의 두 모형 대기열 차이는 그 분이 시작되기 전에 이미 발생했고, 해당 분의 유입 곡선은 같았습니다.

v8에서는5515번이17:01:21에 약33.68명 상당을 태워 줄을 줄였습니다. 월요일 위치자료에서 관측된5515번의 정문 근방 정차 위치 시각은17:04:56이었습니다. 이는 같은 노선의 모형·관측 도착 기록 비교이며 가상 차량과 실차의 ID 매칭은 아닙니다. GPS의 정차 근방 탐지는 실제 승차 시작을 직접 측정한 것도 아닙니다.

교외에서 이미 타고 들어오는 승객의 수와 교내 수요, 실제 승하차시간도 완전히 확인되지 않았습니다. 따라서 도착 시각의 어긋남만으로 모든 오차를 설명할 수 있다고 단정하지 않았습니다.

## 한 번 시험한 개선 후보

수요·정원·속도 프로필·셔틀 시각은 고정했습니다. 정문 근방 시각이 충분히 기록된5513·5515·5528·6515의91개 통과 참조시각을 적용했습니다. 도킹 관측 비율85%를 충족하지 못한5511은 v8 시각을 유지했습니다. 이 기준은 통계적 신뢰수준이 아니라 사전에 정한 자료 사용 조건입니다.

후보 선택에 사용할 도킹 위치 규칙은 정차 관측의 최저 정류장 거리40m 이하·그 최저거리에서10m 안으로 들어온 첫 정차 시각이었습니다. 이 규칙이나 수요를 대기열33~39명에 맞추어 조정하지 않았습니다. 후보는 월요일 피크 한 번만 계산했습니다.

| 관측 | 보고 인원 구간 | 이전v7 분 평균 | v8 분 평균 | 시각 교정 후보 분 평균 |
|---|---:|---:|---:|---:|
${table}

모형 수치는 가중 대기량 상당이며 실제 인원을 직접 센 값이 아닙니다. 측정 초가 알려져 있지 않아 해당 분 전체를 시간 가중했으며, 정문33~39를36명으로 대체하거나 잘 맞는 초를 골라내지 않았습니다.

정문17:03의 분내 범위는 v7이28.41~37.20, v8이17.66~26.45, 교정 후보가58.09~66.62였습니다. 분 안의 측정시각을 균등하게 가정한 관측구간까지의 기대 절대거리는 각각1.597·11.856·22.383명 상당입니다. 후보는 기존 v7 수준 이하로 회복한다는 기준을 통과하지 못했습니다. 다른 두 관측과 질량·정원·승차 순서·차량 시각 검산은 통과했지만 이 사실로 정문 오차를 정당화하지 않았습니다.

## 복원 범위와 한계

지도·30분 그래프·경로 추천의 계산내용을 v7로 복원했습니다. 앱이 더 과거인 모델 번호를 거부하므로, 계산내용은 원래 v7과 완전히 같게 두고 발행 번호만261110005327로 새로 붙였습니다. 계산내용 해시는 기존261109173153과 같습니다. 앱의 자료 실제요일 검증 수정은 유지했습니다.

이 세 관측은 이미 v7 보정에 사용한 자료입니다. 복원이 새로운 날짜에서 정확도가 입증됐다는 뜻은 아닙니다. 앞으로는 실제 정류장 도착·승차 시작시각, 승하차와 재차량, 같은 시각의 줄을 함께 확인해야 도착시각과 공급·수요의 원인을 더 분리할 수 있습니다.

근거는2026-11-09 보관 위치자료, 보존된 v7/v8 원문, 단일 교정 실험과 독립 정합성 검산입니다. 원시 차량 식별자와 입자별 감사 로그는 공개하지 않았습니다.

[현재 지도](./) · [경로 추천](https://snu-route-lab.vercel.app/) · [v7 가정·자료](gate-access-methodology.html) · [비교 집계](rollback-status.json)
`;
 const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const inline=s=>esc(s).replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2">$1</a>');
 const chunks=[];let tbl=[];const flush=()=>{if(!tbl.length)return;const [head,...rows]=tbl;chunks.push('<div class="table-wrap"><table><thead><tr>'+head.map(v=>'<th>'+inline(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+inline(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>');tbl=[]};
 for(const line of md.split('\n')){if(line.startsWith('|')){if(!/^[| :\-]+$/.test(line))tbl.push(line.slice(1,-1).split('|').map(s=>s.trim()));continue}flush();if(line.startsWith('# '))chunks.push('<h1>'+inline(line.slice(2))+'</h1>');else if(line.startsWith('## '))chunks.push('<h2>'+inline(line.slice(3))+'</h2>');else if(line.trim())chunks.push('<p>'+inline(line)+'</p>')};flush();
 const html='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>정문 오차 분석·v7 복원</title><link rel="stylesheet" href="methodology.css"><link rel="stylesheet" href="campus-theme.css"><script defer src="campus-theme.js"></script><body><header class="doc-header"><a href="./" class="doc-brand">하교길 실험실</a><nav><a href="./">현재 지도</a><a href="rollback-report.md">MD 원문</a></nav></header><main class="doc-layout" style="display:block;max-width:1000px"><article>'+chunks.join('')+'</article></main></body></html>';
 const pub=path.join(target,'public');fs.writeFileSync(path.join(pub,'rollback-report.md'),md);fs.writeFileSync(path.join(pub,'rollback-report.html'),html);
 const stat={status:'restored_v7',model_id:'261110005327',source_model_id:'261109173153',dataset:'capacity_v7',candidate_status:decision.status,comparison:{v7:r.v7,v8:r.v8,candidate:r.candidate},independent_accuracy_validated:false};
 fs.writeFileSync(path.join(pub,'rollback-status.json'),JSON.stringify(stat));
 fs.writeFileSync(path.join(work,'원인_분석_및_v7_복원.md'),md);
 for(const suffix of ['html','md']){
  const file=path.join(pub,'gate-access-methodology.'+suffix);let text=fs.readFileSync(file,'utf8');
  const note='11/10 실험 후 계산내용을 v7으로 복원했습니다. 현재 발행번호261110005327은 이전 v7과 계산내용이 같습니다.';
  text=suffix==='html'?text.replace('</h1>','</h1><p><strong>'+note+'</strong> <a href="rollback-report.html">원인과 시험 결과</a></p>'):text.replace('\n','\n\n'+note+' [원인과 시험 결과](rollback-report.html)\n');fs.writeFileSync(file,text);
 }
 // Preserve old v8 guide URLs as an explicitly withdrawn historical record.
 for(const suffix of ['html','md']){
  const file=path.join(pub,'weekday-operations-methodology.'+suffix);let t=fs.readFileSync(file,'utf8');
  const note='이 문서는 철회된 v8 실험의 기록입니다. 현재 운영 계산은 v7로 복원했습니다.';
  t=suffix==='html'?t.replace('</h1>','</h1><p><strong>'+note+'</strong> <a href="rollback-report.html">복원 이유와 시험 결과</a></p>'):t.replace('\n','\n\n'+note+' [복원 이유와 시험 결과](rollback-report.html)\n');
  t=t.replace('기본 지도와 30분 그래프는 capacity_v8을 사용합니다.','아래 표와 비교는 당시 capacity_v8의 기록입니다. 현재 기본 지도와 그래프는 v7입니다.');fs.writeFileSync(file,t);
 }
 // All routing payloads remain raw JSON, readable by the standard-library client.
 // Gain source-size headroom only by lossless recompression of archived v8 replays.
 const candidates=all(path.join(pub,'data/capacity_v8')).filter(p=>/\/(regular|peak)-(mon|tue|wed|thu)\.json\.br$/.test(p.split(path.sep).join('/'))).sort((a,b)=>fs.statSync(b).size-fs.statSync(a).size).slice(0,6);
 const repacked=[];
 async function worker(){for(;;){const file=candidates.shift();if(!file)return;const encoded=fs.readFileSync(file),raw=z.brotliDecompressSync(encoded),better=await comp(raw,{params:{[z.constants.BROTLI_PARAM_QUALITY]:11,[z.constants.BROTLI_PARAM_MODE]:z.constants.BROTLI_MODE_TEXT}});
   if(!z.brotliDecompressSync(better).equals(raw))throw Error('Lossless recompression failed');
   if(better.length<encoded.length)fs.writeFileSync(file,better);
   repacked.push({file:path.relative(pub,file),before:encoded.length,after:Math.min(better.length,encoded.length),decoded_sha256:sha(raw)});console.log('RECOMPRESSED',path.basename(file),encoded.length,better.length);
 }}
 await Promise.all([worker(),worker()]);
 const manifest=all(pub).map(f=>({path:path.relative(pub,f).split(path.sep).join('/'),bytes:fs.statSync(f).size,sha256:sha(fs.readFileSync(f))}));
 const bytes=manifest.reduce((s,v)=>s+v.bytes,0);if(bytes>=100000000)throw Error('Preserve stage, still too large: '+bytes);
 const receipt={status:'PASS',stage:target,bytes,model_id:'261110005327',source_dataset:'capacity_v7',every_versioned_dataset_retained:true,retained_v8_payload:true,lossless_repacked:repacked,manifest};
 fs.writeFileSync(path.join(work,'rollback-stage-verification.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify({...receipt,manifest:undefined,lossless_repacked:undefined}));
})().catch(e=>{console.error(e);process.exit(1)});

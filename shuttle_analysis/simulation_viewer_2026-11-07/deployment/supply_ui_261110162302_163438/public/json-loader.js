// Share in-flight downloads and parsed data. Bound completed entries so a long
// session comparing every weekday does not retain every large replay in RAM.
export function createJsonLoader(maxEntries,fetchData=url=>fetch(url)){
  const entries=new Map();
  function trim(){
    for(const [key,entry] of entries){
      if(entries.size<=maxEntries)break;
      if(entry.done)entries.delete(key);
    }
  }
  return function json(url){
    if(entries.has(url)){
      const entry=entries.get(url);entries.delete(url);entries.set(url,entry);
      return entry.promise;
    }
    const entry={done:false,promise:null};
    entry.promise=Promise.resolve().then(()=>fetchData(url)).then(response=>{
      if(!response.ok)throw new Error(`Replay data ${response.status}`);
      return response.json();
    }).then(data=>{entry.done=true;trim();return data;},error=>{
      if(entries.get(url)===entry)entries.delete(url);
      throw error;
    });
    entries.set(url,entry);trim();return entry.promise;
  };
}

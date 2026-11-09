const make = (tag, text, cls) => { const el = document.createElement(tag); if(text) el.textContent=text; if(cls) el.className=cls; return el; };
const date = value => value ? new Date(value).toLocaleString('zh-CN') : '未知';
function link(record, text, cls) {
  const a = make('a', text, cls), url = new URL(record.url);
  if(url.protocol !== 'https:' || !['download.codebuddy.cn','www.workbuddy.cn'].includes(url.hostname) || url.username || url.password) throw Error('下载域名未通过检查');
  a.href=url.href; a.rel='noopener noreferrer'; return a;
}
async function render(){
  const status=document.querySelector('#status');
  try {
    const response=await fetch('./data/releases.json', {cache:'no-store'});
    if(!response.ok) throw Error('版本数据暂时无法读取');
    const data=await response.json();
    status.textContent=`版本记录更新：${date(data.lastChanged)} · 检查状态请查看 Actions`;
    for(const fmt of ['deb','rpm']) {
      const r=data.current[fmt], card=make('article',null,'card');
      if(!r){card.append(make('h3',`${fmt.toUpperCase()} 暂无可用记录`));document.querySelector('#current').append(card);continue;}
      card.append(make('span',fmt.toUpperCase()+' / x86_64','format'),make('h3',r.version,'version'),make('p',fmt==='deb'?'Ubuntu / Debian 包格式':'Fedora / RPM 包格式'));
      card.append(link(r,`下载官方 ${fmt.toUpperCase()} ↗`,'download'),make('span',new URL(r.url).hostname,'domain'));
      const source=make('a','核对 workbuddy.cn 更新接口 ↗');source.href='https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-'+fmt;
      card.append(make('small',`首次发现：${date(r.firstSeen)}`),source);
      const details=make('details');details.append(make('summary','接口 SHA-256（未验证）'),make('code',r.reportedSha256 || '接口未提供'));card.append(details);
      document.querySelector('#current').append(card);
    }
    document.querySelector('#count').textContent=`${data.history.length} 条观测记录`;
    for(const r of data.history){const tr=make('tr');tr.append(make('td',r.version),make('td',r.format.toUpperCase()),make('td',date(r.firstSeen)));const td=make('td');td.append(link(r,new URL(r.url).hostname+' ↗'));tr.append(td);document.querySelector('#history').append(tr);}
  } catch(error) { status.textContent='加载失败：'+error.message+'。请稍后刷新，或直接访问上方官方接口。'; status.className='error'; }
}
render();

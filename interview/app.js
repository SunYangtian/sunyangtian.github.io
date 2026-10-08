'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const printMode = params.has('print-pdf');
  const readMode = !printMode && (params.get('view') === 'scroll' || (params.get('view') !== 'slides' && matchMedia('(max-width: 760px)').matches));
  let data, chapters, deck, current = 0;
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const append = (parent, ...children) => { children.filter(Boolean).forEach(c => parent.append(c)); return parent; };
  function url(value, label, localOnly = false) {
    if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} 需要填写路径或链接。`);
    const parsed = new URL(value, location.href);
    if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol) || (localOnly && (parsed.origin !== location.origin || /^(https?:)?\/\//i.test(value)))) throw new Error(`${label} 必须使用${localOnly ? '本地相对路径' : ' http(s) 或 mailto 链接'}。`);
    return value;
  }
  const requireText = (v, label) => { if (typeof v !== 'string' || !v.trim()) throw new Error(`${label} 必须是非空文字。`); };
  function validate(d) {
    if (!d || typeof d !== 'object' || Array.isArray(d)) throw new Error('content.json 顶层应为对象。');
    ['title','name','email','homepage'].forEach(k => requireText(d[k], k)); url(d.homepage, 'homepage');
    const count = (v, label) => { if (!Number.isSafeInteger(v) || v < 0) throw new Error(`${label} 应为非负整数。`); };
    if (d.scholar || d.repositories) {
      if (d.scholar) { url(d.scholar.url, 'scholar.url'); count(d.scholar.citations, 'scholar.citations'); }
      Object.entries(d.repositories || {}).forEach(([key, r]) => { requireText(r.name, `repositories.${key}.name`); url(r.url, `repositories.${key}.url`); count(r.stars, `repositories.${key}.stars`); });
    }
    const repository = key => { if (key !== undefined && !d.repositories?.[key]) throw new Error(`找不到仓库：${key}`); };
    if (!Array.isArray(d.chapters) || !d.chapters.length) throw new Error('chapters 至少需要一个章节。');
    const ids = new Set(), layouts = ['cover','timeline','project','comparison','publications','expertise','outlook'];
    d.chapters.forEach((c, i) => {
      const at = `第 ${i+1} 章`;
      if (!c || typeof c !== 'object') throw new Error(`${at} 应为对象。`);
      ['id','layout','title'].forEach(k => requireText(c[k], `${at}.${k}`));
      if (!/^[a-z][a-z0-9-]*$/.test(c.id) || ids.has(c.id)) throw new Error(`${at}.id 须唯一，且只含小写英文字母、数字和连字符，以字母开头。`);
      ids.add(c.id);
      if (!layouts.includes(c.layout)) throw new Error(`${at}.layout 不支持 ${c.layout}。可用：${layouts.join(', ')}`);
      if (c.visible !== undefined && typeof c.visible !== 'boolean') throw new Error(`${at}.visible 应为 true 或 false。`);
      const arr = (key, fields) => { if (!Array.isArray(c[key]) || !c[key].length) throw new Error(`${at}.${key} 不能为空。`); c[key].forEach((v,j) => fields.forEach(k => requireText(v?.[k], `${at}.${key}[${j}].${k}`))); };
      if (['timeline','comparison','expertise','outlook'].includes(c.layout)) arr('items', ['title','description']);
      if (c.layout === 'timeline') c.items.forEach((v,j) => ['date','role'].forEach(k => requireText(v[k],`${at}.items[${j}].${k}`)));
      if (c.layout === 'project') { arr('blocks', ['label','text']); requireText(c.subtitle,`${at}.subtitle`); }
      if (c.layout === 'cover') url(c.portrait, `${at}.portrait`, true);
      if (c.educationId && !d.chapters.some(v => v.id === c.educationId && v.layout === 'timeline')) throw new Error(`${at}.educationId 应指向教育经历 timeline 章节。`);
      if (c.experienceId && !d.chapters.some(v => v.id === c.experienceId && v.layout === 'timeline')) throw new Error(`${at}.experienceId 应指向产业经历 timeline 章节。`);
      repository(c.repository);
      c.items?.forEach(v => repository(v.repository));
      if (c.repositories) { if (!Array.isArray(c.repositories) || c.repositories.length !== c.rows?.length) throw new Error(`${at}.repositories 必须与论文行数相同。`); c.repositories.forEach(repository); }
      if (c.extraProjects) { if (!Array.isArray(c.extraProjects)) throw new Error(`${at}.extraProjects 应为数组。`); c.extraProjects.forEach(v => { requireText(v.title, 'extraProjects.title'); requireText(v.meta, 'extraProjects.meta'); repository(v.repository); }); }
      const media = (m, label) => { if (!m || !['image','video'].includes(m.type)) throw new Error(`${label}.type 应为 image 或 video。`); url(m.src,`${label}.src`,true); requireText(m.alt,`${label}.alt`); if (m.poster) url(m.poster,`${label}.poster`,true); };
      if (c.layout === 'project') media(c.media,`${at}.media`);
      if (c.layout === 'comparison') c.items.forEach((v,j) => { media(v.media,`${at}.items[${j}].media`); if (v.url) url(v.url,`${at}.items[${j}].url`); });
      if (c.layout === 'publications') { if (!Array.isArray(c.columns) || !c.columns.length || !Array.isArray(c.rows)) throw new Error(`${at} 需要 columns 和 rows 数组。`); c.rows.forEach((r,j) => { if (!Array.isArray(r) || r.length !== c.columns.length || r.some(v => typeof v !== 'string')) throw new Error(`${at}.rows[${j}] 必须与 columns 列数相同，且每格为文字。`); }); }
      for (const key of ['links','sources']) if (c[key] !== undefined && !Array.isArray(c[key])) throw new Error(`${at}.${key} 必须是数组。`);
      c.links?.forEach((v,j) => { requireText(v?.label,`${at}.links[${j}].label`); url(v.url,`${at}.links[${j}].url`); });
      c.sources?.forEach(v => url(v,`${at}.sources`));
    });
    if (!d.chapters.some(c => c.visible !== false)) throw new Error('至少需要一个 visible 为 true 的章节。');
  }
  function anchor(label, href) { const a = el('a','',label); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; }
  function contacts() { return append(el('div','contact'), anchor(data.email,`mailto:${data.email}`), anchor(data.homepage.replace(/^https?:\/\//,'').replace(/\/$/,''),data.homepage)); }
  function stars(key, compact = false) {
    const r = data.repositories[key];
    const a = anchor(`${compact ? '' : 'GitHub ' }★ ${r.stars.toLocaleString('en-US')}`, r.url);
    a.className = 'github-stars';
    a.title = `${r.name} · GitHub stars`;
    a.setAttribute('aria-label', `${r.name}：${r.stars} GitHub stars`);
    return a;
  }
  function metricDate() { return null; }
  function applyMetrics(metrics) {
    if (metrics?.scholar?.citations >= 0 && data.scholar) data.scholar.citations = metrics.scholar.citations;
    Object.entries(metrics?.repositories || {}).forEach(([key, value]) => { if (data.repositories[key] && value.stars >= 0) data.repositories[key].stars = value.stars; });
  }
  async function refreshMetrics() {
    try {
      const local = await fetch('metrics.json',{cache:'no-store'});
      if (local.ok) applyMetrics(await local.json());
    } catch (error) { console.warn('本地动态指标接口不可用，继续读取公开 API。', error); }
    const request = (endpoint, timeout = 6000) => { const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout); return fetch(endpoint,{cache:'no-store',signal:controller.signal}).then(response => response.ok ? response.json() : null).finally(() => clearTimeout(timer)); };
    await Promise.allSettled(Object.entries(data.repositories || {}).map(async ([key, repo]) => { const value = await request(`https://api.github.com/repos/${repo.name}`); if (Number.isInteger(value?.stargazers_count)) data.repositories[key].stars = value.stargazers_count; }));
    if (data.scholar?.url) {
      try {
        const mirror = await fetch(`https://r.jina.ai/http://${data.scholar.url.replace(/^https?:\/\//,'')}`,{cache:'no-store'});
        const text = mirror.ok ? await mirror.text() : '';
        const match = text.match(/Citations\s+([\d,]+)/i);
        if (match) data.scholar.citations = Number(match[1].replace(/,/g,''));
      } catch (error) { console.warn('Google Scholar 动态读取失败，使用本地值。', error); }
    }
  }
  function media(m) {
    const frame = el('div','media-frame');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let node;
    if (m.type === 'video') { node = el('video','motion-media'); node.src = m.src; node.controls = true; node.muted = true; node.loop = true; node.playsInline = true; node.preload = 'metadata'; if (m.poster) node.poster = m.poster; node.setAttribute('aria-label',m.alt); }
    else { node = el('img','motion-media'); node.src = reduced && m.poster ? m.poster : m.src; node.alt = m.alt; node.decoding = 'async'; }
    node.addEventListener('error', () => { node.hidden = true; if (!frame.querySelector('.media-error')) frame.append(el('p','media-error',`素材加载失败：${m.src}`)); }); frame.append(node);
    if (m.poster) { const poster = el('img','print-poster'); poster.src = m.poster; poster.alt = m.alt; frame.append(poster); }
    return frame;
  }
  function render(c, i) {
    const section = el('section',`layout-${c.layout}`); section.id = c.id; section.dataset.chapter = i; section.setAttribute('aria-label',c.title);
    section.append(el('span','slide-index',`${String(i+1).padStart(2,'0')} / ${String(chapters.length).padStart(2,'0')}`));
    if (c.layout !== 'cover') { const head = append(el('header','slide-head'), el('p','eyebrow',c.eyebrow || ''), el('h1','',c.title)); if (c.subtitle) head.append(el('p','subtitle',c.subtitle)); if (c.venue) head.append(append(el('div','meta'),el('span','',c.venue),el('span','',c.authorship))); section.append(head); }
    if (c.layout === 'cover') {
      if (c.educationId) {
        const education = data.chapters.find(v => v.id === c.educationId);
        const photo = el('img','portrait'); photo.src = c.portrait; photo.alt = data.name;
        const identity = append(el('div','profile-identity'),photo,append(el('div'),el('p','eyebrow',c.eyebrow),el('h1','',data.name),el('p','affiliation',c.affiliation)));
        const copy = append(el('div','profile-copy'),identity,el('h2','profile-focus',c.subtitle),el('p','description',c.description),el('p','intent',c.intent));
        if (data.scholar) {
          const scholar = anchor('',data.scholar.url); scholar.className = 'scholar-stat';
          append(scholar,el('strong','',data.scholar.citations.toLocaleString('en-US')),append(el('span'),el('span','scholar-label','Google Scholar'),el('span','scholar-caption','Citations · 总引用')));
          copy.append(scholar);
        }
        copy.append(contacts());
        const background = append(el('div','profile-education'),el('p','eyebrow','EDUCATION'),el('h2','','教育背景'));
        education.items.forEach(v=>background.append(append(el('article','education-item'),el('p','education-date',v.date),el('h3','',v.title),el('p','education-role',v.role),el('p','education-detail',v.description))));
        if (education.footer) background.append(el('p','education-award',education.footer));
        const experience = c.experienceId ? data.chapters.find(v => v.id === c.experienceId) : null;
        const work = experience ? append(el('div','profile-experience'),el('p','eyebrow','EXPERIENCE'),el('h2','',experience.title)) : null;
        experience?.items.forEach(v => work.append(append(el('article','experience-item'),el('p','experience-date',v.date),el('h3','',v.title),el('p','experience-role',v.role),el('p','experience-detail',v.description))));
        const right = append(el('div','profile-right'),background,work);
        section.append(append(el('div',`profile-cover ${experience ? 'has-experience' : ''}`),copy,right));
      } else {
      const copy = append(el('div','cover-copy'),el('p','eyebrow',c.eyebrow),el('h1','',data.name),el('h2','',c.subtitle),el('p','affiliation',c.affiliation),el('p','description',c.description),el('p','intent',c.intent),contacts());
      const photo = el('img','portrait'); photo.src=c.portrait;photo.alt=data.name;
      section.append(append(el('div','cover'),copy,append(el('div','cover-side'),photo,el('p','portrait-caption',data.date))));
      }
    } else if (c.layout === 'timeline') {
      const list=el('div',`timeline-list ${c.items.length>=4?'four':''}`);
      c.items.forEach(v=>list.append(append(el('article','timeline-row'),el('p','timeline-date',v.date),append(el('div','timeline-body'),append(el('div','timeline-title'),el('h2','',v.title),el('p','timeline-role',v.role)),el('p','timeline-description',v.description)))));section.append(list);
    } else if (c.layout === 'project') {
      const copy=el('div','project-copy');c.blocks.forEach(v=>copy.append(append(el('div','research-block'),el('h2','',v.label),el('p','',v.text))));
      const visual=append(el('div','project-visual'),append(el('figure',''),media(c.media),el('figcaption','',c.media.caption||'')));
      if(c.result) visual.append(append(el('div','result'),el('span','result-value',c.result.value),append(el('div',''),el('p','result-label',c.result.label),el('p','result-detail',c.result.detail))));
      if(c.links || c.repository)visual.append(append(el('div','links'),...(c.links || []).map(v=>anchor(v.label,v.url)),c.repository ? stars(c.repository) : null));
      if(c.repository)visual.append(metricDate());
      section.append(append(el('div',`project-content ${c.result?'':'no-result'}`),copy,visual));
    } else if(c.layout==='comparison') {
      const grid=el('div','comparison-grid');c.items.forEach(v=>{const item=append(el('article','comparison-item'),el('h2','',v.title),el('p','comparison-meta',v.meta),media(v.media),el('p','comparison-description',v.description));if(v.url || v.repository)item.append(append(el('div','links'),v.url ? anchor('项目演示',v.url) : null,v.repository ? stars(v.repository) : null));grid.append(item);});section.append(grid);if(c.items.some(v=>v.repository))section.append(metricDate());
    } else if(c.layout==='publications') {
      const entries = c.rows.map((r,j) => ({row:r, repository:c.repositories?.[j]})).filter(v => !v.repository || data.repositories[v.repository]?.stars >= 100);
      const table=el('table',`publication-table ${c.repositories ? 'with-stars' : ''}`);const tr=el('tr');[...c.columns,...(c.repositories ? ['GitHub stars'] : [])].forEach(t=>{const th=el('th','',t);th.scope='col';tr.append(th);});table.append(append(el('thead'),tr));const body=el('tbody');entries.forEach(v=>{const row=append(el('tr'),...v.row.map(t=>el('td','',t)));if(c.repositories)row.append(append(el('td'),stars(v.repository,true)));body.append(row);});table.append(body);section.append(append(el('div','publication-scroll'),table));
      if(c.extraProjects) { const extras=append(el('div','extra-projects'),el('p','','其他核心贡献'));c.extraProjects.filter(v => !v.repository || data.repositories[v.repository]?.stars >= 100).forEach(v=>extras.append(append(el('span','extra-project'),el('span','',`${v.title}（${v.meta}）`),v.repository ? stars(v.repository,true) : el('span','repository-unconfirmed','官方仓库未确认'))));section.append(extras); }
      if(c.repositories)section.append(metricDate());
    } else if(c.layout==='expertise') {
      c.items.forEach((v,j)=>section.append(append(el('article','expertise-row'),el('span','expertise-number',String(j+1).padStart(2,'0')),append(el('div'),el('h2','',v.title),el('p','',v.description),el('p','evidence',v.evidence)))));
    } else if(c.layout==='outlook') {
      section.append(append(el('div','outlook-items'),...c.items.map(v=>append(el('article'),el('h2','',v.title),el('p','',v.description)))),el('p','closing',c.closing));const contact=contacts();contact.classList.add('outlook-contact');section.append(contact);
    }
    if(c.footer)section.append(el('p',c.layout==='publications'?'publications-footer':'slide-footer',c.footer));
    section.append(el('aside','notes',c.notes||''));return section;
  }
  function update(i) {current=i;$('position').textContent=`${String(i+1).padStart(2,'0')} / ${String(chapters.length).padStart(2,'0')}`;$('previous').disabled=i===0;$('next').disabled=i===chapters.length-1;document.querySelectorAll('#chapter-list button').forEach((b,j)=>b.setAttribute('aria-current',String(i===j)));}
  function go(i) {i=Math.max(0,Math.min(chapters.length-1,i)); if(readMode){document.getElementById(chapters[i].id).scrollIntoView({behavior:'instant'});history.replaceState(null,'',`#/${chapters[i].id}`);update(i);}else deck.slide(i);}
  function showNotes() {const c=chapters[current];$('notes-heading').textContent=c.title;$('notes-copy').textContent=c.notes||'本章暂无备注，可在 content.json 中填写 notes。';$('notes-sources').replaceChildren(...(c.sources||[]).map((u,i)=>anchor(`参考资料 ${i+1}`,u)));$('speaker-view').hidden=readMode;$('notes-dialog').showModal();}
  async function start() {
    try {
      if(location.protocol==='file:')throw new Error('请双击「启动展示.command」后通过本地网址打开，不能直接双击 index.html。');
      const response=await fetch('content.json',{cache:'no-store'});if(!response.ok)throw new Error(`无法读取 content.json（HTTP ${response.status}）。`);
      const raw=await response.text();try{data=JSON.parse(raw);}catch(e){throw new Error(`content.json 的 JSON 格式错误：${e.message}。请检查英文双引号、逗号和括号。`);}
      validate(data);
      await refreshMetrics();
      chapters=data.chapters.filter(c=>c.visible!==false);document.title=data.title;
      document.body.classList.toggle('read-mode',readMode);$('slides').replaceChildren(...chapters.map(render));
      if(!readMode){deck=new Reveal({width:1280,height:720,margin:.025,center:false,hash:true,hashOneBasedIndex:false,controls:false,progress:true,transition:matchMedia('(prefers-reduced-motion: reduce)').matches?'none':'fade',transitionSpeed:'fast',scrollActivationWidth:null,keyboardCondition:()=>!document.querySelector('dialog[open]'),pdfSeparateFragments:false,pdfMaxPagesPerSlide:1,plugins:[RevealNotes]});await deck.initialize();deck.on('slidechanged',e=>{update(e.indexh);document.querySelectorAll('video').forEach(v=>{if(!e.currentSlide.contains(v))v.pause();});});update(deck.getIndices().h);}
      chapters.forEach((c,i)=>{const b=append(el('button'),el('span','chapter-number',String(i+1).padStart(2,'0')),el('span','',c.title));b.addEventListener('click',()=>{$('chapter-menu').close();go(i);});$('chapter-list').append(append(el('li'),b));});
      $('menu-button').onclick=()=>$('chapter-menu').showModal();$('previous').onclick=()=>go(current-1);$('next').onclick=()=>go(current+1);
      $('mode-button').textContent=readMode?'演示模式':'阅读模式';$('mode-button').onclick=()=>{const u=new URL(location.href);u.searchParams.set('view',readMode?'slides':'scroll');u.hash='/'+chapters[current].id;location.assign(u);};
      $('notes-button').onclick=showNotes;$('speaker-view').onclick=()=>{deck.getPlugin('notes').open();$('notes-dialog').close();};
      $('fullscreen-button').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{ $('fullscreen-button').textContent='请使用浏览器全屏'; }};
      document.addEventListener('fullscreenchange',()=>{$('fullscreen-button').textContent=document.fullscreenElement?'退出全屏':'全屏';});
      document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());
      document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
      if(readMode){const id=decodeURIComponent(location.hash.replace(/^#\/?/,''));const initial=chapters.findIndex(c=>c.id===id);if(initial>=0)requestAnimationFrame(()=>go(initial));const syncReadingPosition=()=>{const sections=[...document.querySelectorAll('#slides>section')];const marker=Math.min(innerHeight*.25,180);const active=sections.findIndex(s=>{const r=s.getBoundingClientRect();return r.top<=marker&&r.bottom>marker;});if(active>=0)update(active);};document.addEventListener('scroll',syncReadingPosition,{passive:true});window.addEventListener('resize',syncReadingPosition);document.addEventListener('keydown',e=>{if(e.key.toLowerCase()==='s'&&!e.ctrlKey&&!e.metaKey&&!document.querySelector('dialog[open]')){e.preventDefault();showNotes();}});}
      $('status').hidden=true;document.querySelector('.toolbar').hidden=printMode;update(deck?deck.getIndices().h:current);window.interview={go,get current(){return current;},get chapters(){return chapters;},deck,readMode};
    } catch(error) {$('status').hidden=false;$('status').className='error';$('status').replaceChildren(el('h1','','内容暂时无法显示'),el('p','',error.message),el('p','','修正文件后刷新页面即可。'));console.error(error);}
  }
  start();
})();

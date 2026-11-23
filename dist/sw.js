// DSIG professional space service worker.
// Privacy: API responses (customer data) are never cached. Static files use the network first,
// so a new release is picked up immediately; the cache only serves as an offline fallback.
const CACHE='dsig-shell-v1';
const SHELL=['/offline.html','/admin.css','/accessibility.css','/dsig-mark.svg','/favicon.svg','/icon-192.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('dsig-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==location.origin||url.pathname.startsWith('/api/'))return;
 if(!/^\/[A-Za-z0-9_-]*(\.(html|css|js|svg|png|webp|webmanifest))?$/.test(url.pathname)||url.pathname==='/sw.js')return;
 event.respondWith(fetch(request).then(response=>{
  if(response.ok&&response.type==='basic'){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy))}
  return response;
 }).catch(()=>caches.match(request,{ignoreSearch:true}).then(hit=>hit||(request.mode==='navigate'?caches.match('/offline.html'):Response.error()))));
});

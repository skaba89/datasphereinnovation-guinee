/* Original, local SVG line icons. No font, emoji or external library. */
const iconPaths = {
  database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  chart:'<path d="M3 3v18h18M7 17v-5m5 5V8m5 9V4"/>',
  network:'<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v4M5 16v-4h14v4"/>',
  cloud:'<path d="M6 19h13a4 4 0 0 0 1-8 7 7 0 0 0-13-4 6 6 0 0 0-1 12Z"/>',
  code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-2-15-4 18"/>',
  layers:'<path d="m12 2 10 6-10 6-10-6 10-6ZM2 12l10 6 10-6M2 16l10 6 10-6"/>',
  shield:'<path d="M12 2 3 6v6c0 5 4 8 9 10 5-2 9-5 9-10V6L12 2Z"/><path d="m8 12 3 3 5-6"/>',
  lock:'<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3"/>',
  radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7m-7 7v1"/>',
  backup:'<path d="M4 8a8 8 0 1 1 0 8M4 8V3m0 5h5"/><path d="M12 8v4l3 2"/>',
  brain:'<path d="M12 5a4 4 0 0 0-7-1 5 5 0 0 0-2 8 5 5 0 0 0 2 7 4 4 0 0 0 7 0V5Zm0 0a4 4 0 0 1 7-1 5 5 0 0 1 2 8 5 5 0 0 1-2 7 4 4 0 0 1-7 0M7 8c0 2 2 3 5 3m5-3c0 2-2 3-5 3"/>',
  finance:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 11h2m4 0h2m-8 4h2m4 0h2m-8 4h8"/>',
  audit:'<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V2h6v2M9 10l2 2 4-4m-6 8h6"/>',
  document:'<path d="M6 2h8l6 6v14H6V2Zm8 0v6h6M9 12h8m-8 4h8"/>',
  users:'<circle cx="9" cy="7" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M17 3a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 5v2"/>',
  briefcase:'<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V3h8v4M2 13h20m-12 0v3h4v-3"/>',
  truck:'<path d="M2 5h13v12H2zm13 4h4l3 4v4h-7"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  education:'<path d="m2 9 10-6 10 6-10 6-10-6Zm4 3v6c4 3 8 3 12 0v-6m4-3v8"/>',
  store:'<path d="M3 10 5 3h14l2 7M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M5 13v8h14v-8M10 21v-6h4v6"/>',
  building:'<path d="m2 8 10-6 10 6H2Zm2 13h16M6 10v9m6-9v9m6-9v9M2 23h20"/>',
  health:'<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z"/>',
  radio:'<circle cx="12" cy="12" r="2"/><path d="M7 7a7 7 0 0 0 0 10M17 7a7 7 0 0 1 0 10M4 4a11 11 0 0 0 0 16M20 4a11 11 0 0 1 0 16"/>',
  map:'<path d="m2 5 7-3 6 3 7-3v17l-7 3-6-3-7 3V5Zm7-3v17m6-14v17"/>',
  gear:'<circle cx="12" cy="12" r="4"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4M5 5l3 3m8 8 3 3M5 19l3-3m8-8 3-3"/>',
  arrow:'<path d="M6 18 18 6M7 6h11v11"/>',
  up:'<path d="M12 20V4m-6 6 6-6 6 6"/>',
  back:'<path d="M20 12H4m6-6-6 6 6 6"/>',
  menu:'<path d="M3 6h18M3 12h18M3 18h18"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  mic:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8"/>',
  music:'<path d="M9 18V5l12-3v13M9 5l12-3"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="18" cy="15" rx="3" ry="2"/>'
};
function icon(name){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [k,v] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',focusable:'false',class:'dsig-icon'}))svg.setAttribute(k,v);
  svg.innerHTML=iconPaths[name]||iconPaths.layers;
  return svg;
}
function renderIcons(root=document){
  root.querySelectorAll('[data-icon]').forEach(el=>el.replaceChildren(icon(el.dataset.icon)));
}
function arrowLabel(el,text,name='arrow'){
  el.replaceChildren(document.createTextNode(text+' '),icon(name));
}
renderIcons();

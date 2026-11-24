// Caddyfile of the public website image, from the single source deploy/public/Caddyfile (V175).
// "disabled" (default): unchanged static site, connect-src 'none', no API route.
// "enabled": same file plus POST /api/contact proxied to the dedicated PROD contact service on the
// private edge network, connect-src 'self', and private-range proxies trusted so the visitor IP
// is forwarded (X-Forwarded-For) for rate limiting; read timeouts cut slow clients (slowloris).
// The shared edge proxy is never modified.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const contactUpstream='dsig-contact:8090';

export function publicCaddyfile(source,mode='disabled'){
 if(!['disabled','enabled'].includes(mode))throw Error('Mode must be disabled or enabled');
 source=source.split('\r\n').join('\n');
 if(mode==='disabled')return source;
 const csp="connect-src 'none'",global='    persist_config off\n',privateRoutes='    @private path ';
 for(const marker of [csp,global,privateRoutes])if(source.split(marker).length!==2)throw Error('Unexpected Caddyfile layout: '+marker.trim());
 return source
  .replace(csp,"connect-src 'self'")
  .replace(global,global+'    servers {\n        trusted_proxies static private_ranges\n        timeouts {\n            read_header 5s\n            read_body 10s\n        }\n    }\n')
  // request_buffers: Caddy reads the whole (8 KB max) body before proxying, so a slow visitor never
  // holds one of the contact service's handler slots.
  .replace(privateRoutes,'    @contact {\n        method POST\n        path /api/contact\n    }\n    handle @contact {\n        request_body {\n            max_size 8KB\n        }\n        reverse_proxy '+contactUpstream+' {\n            request_buffers 8KB\n        }\n    }\n'+privateRoutes);
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 if(process.argv.length!==4)throw Error('Usage: node scripts/public-caddyfile.mjs CADDYFILE disabled|enabled');
 process.stdout.write(publicCaddyfile(fs.readFileSync(process.argv[2],'utf8'),process.argv[3]));
}

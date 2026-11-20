document.addEventListener('DOMContentLoaded',async()=>{
 const form=document.getElementById('login-form')||document.getElementById('form');const input=document.getElementById('token');if(!form||!input)return;
 const link=document.createElement('a');link.href='connexion.html';link.textContent='Portail de connexion';form.after(link);
 const button=document.getElementById('logout');if(button)button.addEventListener('click',async()=>{try{const r=await fetch('/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer session','Content-Type':'application/json'},body:'{}'});if(r.ok)location.assign('connexion.html')}catch{} });
 try{const r=await fetch('/api/auth/me',{headers:{Authorization:'Bearer session'}});if(r.ok&&!input.value){input.value='session';form.requestSubmit()}}catch{}
});

let stream;
function startStreaming(){if(stream)return;stream=new EventSource(document.body.dataset.base+'/action/local-record/stream');stream.onmessage=event=>{const value=JSON.parse(event.data),mouth=document.querySelector('.enable-mouth'),talking=document.querySelector('.animation-talking');if(!mouth||!talking)return;mouth.style.opacity=value.status==='playing'?'1':'0';talking.style.animationPlayState=value.status==='playing'?'running':'paused';};}
window.addEventListener('DOMContentLoaded',startStreaming);

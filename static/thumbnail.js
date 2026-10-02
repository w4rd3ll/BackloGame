'use strict';
let cropGame=null,cropRect=null,cropBase=null,cropPointer=null,cropReady=false,cropSaving=false,menuGame=null;
const thumbnailRatio=460/215;
const clampCrop=(value,min,max)=>Math.min(max,Math.max(min,value));
function hideCoverMenu(){ $('coverMenu').hidden=true; }
document.addEventListener('contextmenu',event=>{
  const image=event.target.closest('[data-cover-id]');
  if(!image)return;
  const game=games.find(g=>g.id===Number(image.dataset.coverId));
  if(!game||!cropArtwork(game).src)return;
  event.preventDefault();menuGame=game;
  $('resetThumbnail').hidden=!game.thumbnail_crop;
  const menu=$('coverMenu');menu.hidden=false;
  menu.style.left=Math.max(0,Math.min(event.clientX,window.innerWidth-menu.offsetWidth-8))+'px';
  menu.style.top=Math.max(0,Math.min(event.clientY,window.innerHeight-menu.offsetHeight-8))+'px';
  $('chooseThumbnail').focus();
});
document.addEventListener('click',event=>{if(!event.target.closest('#coverMenu'))hideCoverMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')hideCoverMenu();});
window.addEventListener('resize',hideCoverMenu);
document.addEventListener('scroll',hideCoverMenu,true);
$('chooseThumbnail').onclick=()=>{const game=menuGame;hideCoverMenu();openCrop(game);};
$('resetThumbnail').onclick=async()=>{
  const game=menuGame;hideCoverMenu();
  try{const saved=await api('/api/save',{id:game.id,game:{title:game.title,thumbnail_crop:null}});Object.assign(game,saved);render();toast(t("Миниатюра сброшена"));}catch(err){toast(err.message,true);}
};
function paintCrop(){
  if(!cropReady)return;
  const frame=$('cropFrame');
  Object.assign(frame.style,{left:cropRect.x*100+'%',top:cropRect.y*100+'%',width:cropRect.width*100+'%',height:cropRect.height*100+'%'});
  frame.setAttribute('aria-valuenow',String(Math.round(cropRect.y*100)));
  frame.setAttribute('aria-valuetext',`${t("Область:")} ${Math.round(cropRect.x*100)}${t("% слева,")} ${Math.round(cropRect.y*100)}${t("% сверху")}`);
  $('cropPreview').innerHTML=croppedCover(cropArtwork(cropGame).src,cropRect);
  wireImages($('cropPreview'));
}
function openCrop(game){
  cropGame=game;cropReady=false;cropPointer=null;cropSaving=false;
  $('saveCrop').disabled=true;$('cropZoom').disabled=true;$('cropFrame').hidden=true;
  $('cropPreview').innerHTML='';$('cropMessage').textContent=t("Загружаем обложку…");
  const img=$('cropImage');
  img.onload=()=>{
    const aspect=img.naturalWidth/img.naturalHeight;
    cropBase=aspect>thumbnailRatio?{width:thumbnailRatio/aspect,height:1}:{width:1,height:aspect/thumbnailRatio};
    const previous=game.thumbnail_crop;
    const valid=previous?.image===cropArtwork(game).image&&Math.abs(previous.width*aspect/previous.height-thumbnailRatio)<0.01;
    const zoom=valid?clampCrop(cropBase.width/previous.width,1,4):1;
    cropRect=valid?{...previous}:{width:cropBase.width,height:cropBase.height,x:(1-cropBase.width)/2,y:(1-cropBase.height)/2};
    $('cropZoom').value=String(zoom);$('cropZoom').disabled=false;cropReady=true;
    $('cropFrame').hidden=false;$('saveCrop').disabled=false;
    $('cropMessage').textContent=t("Можно двигать рамку мышью или стрелками на клавиатуре.");paintCrop();
  };
  img.onerror=()=>{$('cropMessage').textContent=t("Не удалось загрузить обложку. Проверь подключение и попробуй снова.");};
  img.removeAttribute('src');img.src=cropArtwork(game).src;$('cropDialog').showModal();
}
$('cropZoom').oninput=()=>{
  if(!cropReady)return;
  const cx=cropRect.x+cropRect.width/2,cy=cropRect.y+cropRect.height/2,zoom=Number($('cropZoom').value);
  cropRect.width=cropBase.width/zoom;cropRect.height=cropBase.height/zoom;
  cropRect.x=clampCrop(cx-cropRect.width/2,0,1-cropRect.width);cropRect.y=clampCrop(cy-cropRect.height/2,0,1-cropRect.height);paintCrop();
};
function cropPoint(event){const box=$('cropStage').getBoundingClientRect();return {x:(event.clientX-box.left)/box.width,y:(event.clientY-box.top)/box.height};}
$('cropStage').onpointerdown=event=>{
  if(!cropReady||cropSaving||event.button!==0)return;
  event.preventDefault();const point=cropPoint(event);
  if(event.target!==$('cropFrame')){cropRect.x=clampCrop(point.x-cropRect.width/2,0,1-cropRect.width);cropRect.y=clampCrop(point.y-cropRect.height/2,0,1-cropRect.height);paintCrop();}
  cropPointer={id:event.pointerId,x:point.x-cropRect.x,y:point.y-cropRect.y};
  $('cropStage').setPointerCapture(event.pointerId);$('cropFrame').focus({preventScroll:true});
};
$('cropStage').onpointermove=event=>{
  if(!cropPointer||cropPointer.id!==event.pointerId)return;
  const point=cropPoint(event);cropRect.x=clampCrop(point.x-cropPointer.x,0,1-cropRect.width);cropRect.y=clampCrop(point.y-cropPointer.y,0,1-cropRect.height);paintCrop();
};
for(const event of ['pointerup','pointercancel','lostpointercapture'])$('cropStage').addEventListener(event,()=>{cropPointer=null;});
$('cropFrame').onkeydown=event=>{
  if(!cropReady||cropSaving)return;
  const steps={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]},step=steps[event.key];
  if(!step)return;event.preventDefault();const amount=event.shiftKey?0.05:0.01;
  cropRect.x=clampCrop(cropRect.x+step[0]*amount,0,1-cropRect.width);cropRect.y=clampCrop(cropRect.y+step[1]*amount,0,1-cropRect.height);paintCrop();
};
function closeCrop(){if(!cropSaving){$('cropDialog').close();cropReady=false;cropPointer=null;}}
$('closeCrop').onclick=closeCrop;$('cancelCrop').onclick=closeCrop;
$('cropDialog').addEventListener('cancel',event=>{if(cropSaving)event.preventDefault();else cropReady=false;});
$('saveCrop').onclick=async()=>{
  if(!cropReady||cropSaving)return;
  cropSaving=true;$('cropZoom').disabled=true;
  await busy($('saveCrop'),async()=>{
    const saved=await api('/api/save',{id:cropGame.id,game:{title:cropGame.title,thumbnail_crop:{x:cropRect.x,y:cropRect.y,width:cropRect.width,height:cropRect.height,image:cropArtwork(cropGame).image}}});
    Object.assign(cropGame,saved);render();$('cropDialog').close();cropReady=false;toast(t("Миниатюра сохранена"));
  });
  cropSaving=false;$('cropZoom').disabled=false;
};

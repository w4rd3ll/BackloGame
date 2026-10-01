'use strict';
// The desktop wrapper injects its marker without changing the browser workflow.
function desktopCloseRequest(){
  if(dirty&&!confirm(t("Изменения в карточке не сохранены. Закрыть приложение?")))return;
  api('/api/desktop-close',{}).catch(err=>toast(err.message,true));
}

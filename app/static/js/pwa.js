/* Registra o app (service worker) e mostra o botão "Instalar app" quando o celular permite. */
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").then(function () {
        // Na tela de entrar do associado, apaga a carteirinha guardada (quem saiu não deixa dados no aparelho)
        if (document.body.dataset.limparCarteirinha && navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage("limpar-carteirinha");
        }
      }).catch(function () {});
    });
  }
  if (document.body.dataset.limparCarteirinha && window.caches) caches.delete("vda-carteirinha");

  var instalado = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  var pedido = null;
  // Android em navegador que não é o Chrome (Samsung Internet, Mi Browser, Opera, Edge, Firefox...):
  // o app que eles criam é bloqueado pelo Play Protect ("App de risco bloqueado").
  // Nesses casos não oferece instalar ali: mostra o aviso com o botão "Abrir no Chrome".
  var ua = navigator.userAgent;
  var android = /android/i.test(ua);
  var chromeDeVerdade = /Chrome\/\d/.test(ua) && !/SamsungBrowser|EdgA|OPR|Opera|YaBrowser|MiuiBrowser|XiaoMi|HeyTapBrowser|UCBrowser|Vivaldi|DuckDuckGo|; wv\)|Version\/\d/.test(ua);
  var foraDoChrome = android && !chromeDeVerdade && !instalado;
  if (foraDoChrome) {
    var endereco = location.host + location.pathname + location.search;
    document.querySelectorAll("[data-dica-chrome]").forEach(function (b) { b.hidden = false; });
    document.querySelectorAll("[data-abrir-chrome]").forEach(function (a) {
      a.href = "intent://" + endereco + "#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=" +
        encodeURIComponent("https://play.google.com/store/apps/details?id=com.android.chrome") + ";end";
    });
  }
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    if (foraDoChrome) return;
    pedido = e;
    document.querySelectorAll("[data-instalar]").forEach(function (b) { b.hidden = false; });
  });
  document.addEventListener("click", function (e) {
    var botao = e.target.closest("[data-instalar]");
    if (!botao || !pedido) return;
    pedido.prompt();
    pedido.userChoice.finally(function () { pedido = null; botao.hidden = true; });
  });
  window.addEventListener("appinstalled", function () {
    document.querySelectorAll("[data-instalar], [data-dica-iphone], [data-dica-chrome]").forEach(function (b) { b.hidden = true; });
  });
  // iPhone não tem botão de instalar: mostra a dica de "Adicionar à Tela de Início"
  var iphone = /iphone|ipad|ipod/i.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  if (iphone && !instalado) {
    document.querySelectorAll("[data-dica-iphone]").forEach(function (b) { b.hidden = false; });
  }
  // Sem internet: avisa que a carteirinha mostrada é a última guardada
  function avisoConexao() {
    document.querySelectorAll("[data-sem-internet]").forEach(function (b) { b.hidden = navigator.onLine; });
  }
  window.addEventListener("online", avisoConexao);
  window.addEventListener("offline", avisoConexao);
  avisoConexao();
})();

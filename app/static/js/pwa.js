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
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
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
    document.querySelectorAll("[data-instalar], [data-dica-iphone]").forEach(function (b) { b.hidden = true; });
  });
  // iPhone não tem botão de instalar: mostra a dica de "Adicionar à Tela de Início"
  var iphone = /iphone|ipad|ipod/i.test(navigator.userAgent);
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

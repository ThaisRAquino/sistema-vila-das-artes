/* Service worker do app Vila das Artes.
   - Arquivos de estilo, ícones e logo: guardados para abrir rápido.
   - Carteirinha do associado (página inicial, QR e foto): a última versão fica guardada no celular
     e aparece mesmo sem internet, para mostrar o QR na entrada da assembleia.
   - Páginas da equipe NÃO são guardadas (têm dados de todos os associados). */
const VERSAO = "vda-v5";
const ESTATICOS = VERSAO + "-estaticos";
const CARTEIRINHA = "vda-carteirinha";
const PRE_CACHE = [
  "/static/css/style.css",
  "/static/img/logo.jpg",
  "/static/js/pwa.js",
  "/static/js/fotos.js",
  "/static/js/mascaras.js",
  "/static/icones/icone-192.png",
  "/static/offline.html",
];
const DA_CARTEIRINHA = ["/associado/", "/associado/qr.png", "/associado/foto.jpg"];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(ESTATICOS).then((c) => c.addAll(PRE_CACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith("vda-v") && !n.startsWith(VERSAO)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (evento) => {
  if (evento.data === "limpar-carteirinha") caches.delete(CARTEIRINHA);
});

self.addEventListener("fetch", (evento) => {
  const req = evento.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    // Mostra o que está guardado (rápido) e busca a versão nova em segundo plano: atualizações chegam sozinhas
    evento.respondWith(
      caches.open(ESTATICOS).then((cache) => cache.match(req).then((guardado) => {
        const daRede = fetch(req).then((resp) => {
          if (resp.ok) cache.put(req, resp.clone());
          return resp;
        }).catch(() => guardado);
        return guardado || daRede;
      }))
    );
    return;
  }

  if (DA_CARTEIRINHA.includes(url.pathname)) {
    evento.respondWith(
      fetch(req).then((resp) => {
        // só guarda quando a página é mesmo a carteirinha (não a tela de entrar ou o termo)
        if (resp.ok && !resp.redirected) { const copia = resp.clone(); caches.open(CARTEIRINHA).then((c) => c.put(url.pathname, copia)); }
        return resp;
      }).catch(() => caches.match(url.pathname, { cacheName: CARTEIRINHA })
        .then((guardado) => guardado || caches.match("/static/offline.html")))
    );
    return;
  }

  if (req.mode === "navigate") {
    evento.respondWith(fetch(req).catch(() => caches.match("/static/offline.html")));
  }
});

/* Reduz fotos no próprio celular antes de enviar (máx. 1600 px, JPG).
   Fotos de celular costumam ter de 3 a 15 MB; reduzidas ficam com cerca de 300 KB e o envio é rápido
   mesmo com internet fraca. Se o navegador não conseguir abrir a foto (ex.: HEIC no Android),
   o arquivo original é enviado e o servidor converte. Vale para <input type="file" data-reduzir>. */
(function () {
  var MAX = 1600;

  function reduzir(arquivo) {
    if (!arquivo || !/^image\//.test(arquivo.type) || !window.createImageBitmap) return Promise.resolve(null);
    return createImageBitmap(arquivo, { imageOrientation: "from-image" }).then(function (bmp) {
      var escala = Math.min(1, MAX / Math.max(bmp.width, bmp.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(bmp.width * escala);
      canvas.height = Math.round(bmp.height * escala);
      canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
      return new Promise(function (ok) { canvas.toBlob(ok, "image/jpeg", 0.85); });
    }).then(function (blob) {
      if (!blob) return null;
      var nome = (arquivo.name || "foto").replace(/\.[^.]+$/, "") + ".jpg";
      return new File([blob], nome, { type: "image/jpeg" });
    }).catch(function () { return null; });
  }

  document.addEventListener("change", function (e) {
    var campo = e.target;
    if (!campo.matches || !campo.matches('input[type="file"][data-reduzir]') || !campo.files.length) return;
    var form = campo.form, botao = form && form.querySelector('[type="submit"]');
    var texto = botao && botao.textContent;
    if (botao) { botao.disabled = true; botao.textContent = "Preparando a foto…"; }
    reduzir(campo.files[0]).then(function (menor) {
      if (menor && menor.size < campo.files[0].size && window.DataTransfer) {
        try {
          var dt = new DataTransfer();
          dt.items.add(menor);
          campo.files = dt.files;
        } catch (erro) { /* navegador antigo: envia a original */ }
      }
    }).finally(function () {
      if (botao) { botao.disabled = false; botao.textContent = texto; }
    });
  });

  // Mostra que está enviando (evita tocar duas vezes com internet lenta)
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.querySelector('input[type="file"][data-reduzir]')) return;
    var botao = form.querySelector('[type="submit"]');
    if (botao) { setTimeout(function () { botao.disabled = true; botao.textContent = "Enviando…"; }, 0); }
  });
})();

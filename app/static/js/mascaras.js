/* Máscaras dos campos de documentos e preenchimento do endereço pelo CEP.
   Uso no HTML: <input data-mascara="cpf|rg|cep|cnpj|celular|telefone|titulo">
   O servidor continua aceitando com ou sem pontos (guarda só os números onde precisa). */
(function () {
  "use strict";

  function digitos(texto, max) { return (texto || "").replace(/\D/g, "").slice(0, max); }

  // Encaixa os dígitos no modelo: cada 0 é um dígito, o resto é separador.
  function aplicar(modelo, numeros) {
    var saida = "", i = 0;
    for (var p = 0; p < modelo.length && i < numeros.length; p++) {
      saida += modelo[p] === "0" ? numeros[i++] : modelo[p];
    }
    return saida;
  }

  var MASCARAS = {
    cpf: function (v) { return aplicar("000.000.000-00", digitos(v, 11)); },
    cep: function (v) { return aplicar("00000-000", digitos(v, 8)); },
    cnpj: function (v) { return aplicar("00.000.000/0000-00", digitos(v, 14)); },
    titulo: function (v) { return aplicar("0000 0000 0000", digitos(v, 12)); },
    celular: function (v) {
      var d = digitos(v, 11);
      return d.length > 10 ? aplicar("(00) 00000-0000", d) : aplicar("(00) 0000-0000", d);
    },
    telefone: function (v) {
      var d = digitos(v, 11);
      return d.length > 10 ? aplicar("(00) 00000-0000", d) : aplicar("(00) 0000-0000", d);
    },
    // RG de SP e da maioria dos estados: 00.000.000-0 (o último pode ser X).
    // RG com outro tamanho fica como foi digitado, para não estragar documentos de outros estados.
    rg: function (v) {
      var limpo = (v || "").toUpperCase().replace(/[^0-9X]/g, "");
      var corpo = limpo.replace(/X/g, "");
      var final = /X$/.test(limpo) ? "X" : "";
      if (final && corpo.length === 8) return aplicar("00.000.000", corpo) + "-X";
      if (!final && corpo.length <= 9) {
        return corpo.length > 8 ? aplicar("00.000.000-0", corpo) : aplicar("00.000.000", corpo);
      }
      return v;
    }
  };

  function formatar(campo) {
    var f = MASCARAS[campo.dataset.mascara];
    if (!f) return;
    var antes = campo.value, novo = f(antes);
    if (novo === antes) return;
    var noFim = campo.selectionStart === antes.length;
    campo.value = novo;
    if (noFim && document.activeElement === campo) campo.setSelectionRange(novo.length, novo.length);
  }

  // ---- Endereço automático pelo CEP (serviço gratuito ViaCEP) ----
  var ultimoCep = "";
  function avisoCep(campo, texto, erro) {
    var aviso = document.getElementById("cep-aviso");
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.style.color = erro ? "var(--risco-texto, #B42318)" : "";
  }
  function buscarCep(campo) {
    var cep = digitos(campo.value, 8);
    if (cep.length !== 8 || cep === ultimoCep) return;
    ultimoCep = cep;
    avisoCep(campo, "Buscando endereço…");
    fetch("https://viacep.com.br/ws/" + cep + "/json/")
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (d) {
        if (d.erro) { avisoCep(campo, "CEP não encontrado. Preencha o endereço à mão.", true); return; }
        var form = campo.form, preenchidos = 0;
        [["rua", d.logradouro], ["bairro", d.bairro], ["cidade", d.localidade], ["uf", d.uf]].forEach(function (par) {
          var alvo = form.elements[par[0]];
          if (alvo && par[1]) { alvo.value = par[1]; preenchidos++; }
        });
        avisoCep(campo, preenchidos ? "Endereço preenchido pelo CEP. Confira e coloque o número." : "CEP sem rua cadastrada: preencha a rua e o bairro.");
        var numero = form.elements["numero"];
        if (numero && !numero.value) numero.focus();
      })
      .catch(function () { avisoCep(campo, "Sem conexão para buscar o CEP. Preencha o endereço à mão.", true); ultimoCep = ""; });
  }

  function iniciar() {
    document.querySelectorAll("input[data-mascara]").forEach(function (campo) {
      formatar(campo);  // valores que já vêm do banco aparecem com pontos
      campo.addEventListener("input", function () {
        formatar(campo);
        if (campo.dataset.mascara === "cep" && campo.dataset.buscarEndereco !== undefined) buscarCep(campo);
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();

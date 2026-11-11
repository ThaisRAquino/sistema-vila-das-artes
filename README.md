# Sistema Vila das Artes – Gestão de Associados

Sistema web feito para a **Associação Vila das Artes** (Embu das Artes/SP), entidade de defesa do direito à moradia, como **Projeto de Extensão Curricularizada** do curso de Análise e Desenvolvimento de Sistemas da **UniFECAF**.

- **Temática 1:** Digitalização e Automação de Processos Sociais
- **ODS:** 1 (Erradicação da pobreza), 10 (Redução das desigualdades), 11 (Cidades e comunidades sustentáveis) e 16 (Instituições eficazes)
- **Autora:** Thais R. Aquino

## O problema

A associação acompanha cerca de **508 famílias** em fichas de papel guardadas em caixas, com dados repetidos em planilhas. Na visita técnica (11/10/2026), localizar a documentação de uma família levou **15 a 20 minutos**, montar a lista pedida pelo CDHU levava **cerca de uma semana**, e já houve **4 famílias com o mesmo número de associado**.

## O que o sistema faz

### 1º bloco – pronto ✅
- Login da equipe (senha criptografada)
- Cadastro de associados com os campos da ficha de inscrição
- **Nº de sócio único**: o sistema sugere o próximo número, a equipe pode alterar, números repetidos são bloqueados e cada alteração fica registrada (quem, quando e motivo)
- CPF validado e sem duplicidade
- Categoria **regular** ou **mutirante (isento)**
- Checklist dos 5 documentos (RG, CPF, título de eleitor, comprovante de endereço e carteira de trabalho), com registro de quem conferiu
- Familiares (cônjuge e dependentes)
- **QR da carteirinha** gerado a partir de um código secreto (não usa CPF nem nº de sócio), com opção de gerar um novo se a carteirinha for perdida
- Autorização de uso dos dados (LGPD) obrigatória no cadastro
- Busca por nome, CPF ou nº de sócio, e filtros por categoria e documentos pendentes

### 2º bloco – pronto ✅
- **Mensalidades (R$ 50)** geradas automaticamente a cada mês
- **Comprovante obrigatório**: a equipe registra o comprovante (foto ou PDF) e a mensalidade fica *em análise*; ela só vira **paga** depois que alguém da equipe **valida**. Se recusar, escolhe o motivo
- **Recibo** numerado (ex.: 2026-00001), pronto para imprimir ou salvar em PDF
- **Mutirantes isentos** até a diretoria **ativar a cobrança** (botão na tela de Mensalidades, quando sair novo projeto do CDHU)
- **Assembleias** no 2º domingo do mês: presença pelo **nº de sócio** ou **lendo o QR** da carteirinha com a câmera do celular; não deixa marcar duas vezes; encerrar e reabrir a lista
- **Alerta de desligamento**: o painel mostra quem tem **3 faltas seguidas** ou **3 mensalidades seguidas em aberto** (e quem está com 2, em atenção). O sistema só alerta; a decisão é da diretoria
- **Avisos pelo WhatsApp**: o sistema prepara a mensagem (faltas, mensalidade, documentos ou lembrete da assembleia), abre o WhatsApp com o texto pronto e guarda o histórico

### 3º bloco – área do associado (pedido do presidente)
- O associado entra pelo celular em **/associado** com **CPF e senha**. No primeiro acesso (ou se esquecer a senha) usa um **código de 6 letras** que a equipe gera na ficha e envia pelo WhatsApp (vale 7 dias e só uma vez)
- Antes de usar, ele lê e aceita o **termo de uso dos dados e da imagem** (LGPD). São dois aceites separados: os dados são obrigatórios; a imagem é opcional. A ficha mostra a versão e a data do aceite
- Com a imagem autorizada, o **próprio associado envia a foto** do perfil. O sistema recorta em quadrado, reduz para 600×600 e salva em JPG (apaga a localização e outros dados ocultos da foto). Se ele retirar a autorização, a foto é apagada
- **Carteirinha digital** com foto e QR para a assembleia, situação (mensalidades, faltas, documentos), próxima assembleia, presenças e **envio do comprovante** da mensalidade, que vai para a análise da equipe
- A equipe vê a foto na ficha e pode removê-la (imprópria ou a pedido). Depois de 5 tentativas erradas, o acesso fica bloqueado por 15 minutos

### 4º bloco – pronto para usar de verdade
- **App instalável** (PWA): no Android aparece o botão **Instalar app**; no iPhone, "Adicionar à Tela de Início". O ícone da associação vai para a tela inicial e abre em tela cheia. A **carteirinha com o QR abre mesmo sem internet** (a última versão fica guardada no celular e é apagada quando o associado sai). As telas da equipe não ficam guardadas no aparelho
- **Equipe**: cada pessoa da equipe tem o seu usuário. O presidente cadastra, desativa e gera senha provisória; no primeiro acesso a pessoa cria a própria senha (tela **Minha senha**)
- **Bloqueio de tentativas** guardado no banco, para a equipe e para os associados: 5 senhas erradas bloqueiam por 15 minutos, mesmo trocando de navegador
- **Importar planilha** (Excel ou CSV) para cadastrar os associados de uma vez: modelo pronto para baixar, prévia linha a linha com os erros (CPF inválido ou repetido, nº em uso, data errada) e nada é gravado antes de confirmar
- **Acessos ao app**: mostra quem já usa a área do associado e gera os **códigos de primeiro acesso em lote**, com o botão de envio pelo WhatsApp em cada linha
- **Banco atualizado automaticamente**: quando o sistema ganha campos novos, o banco é ajustado sozinho, sem apagar dados
- **Modo de produção** (https, cookies seguros, cabeçalhos de segurança), páginas de erro amigáveis e **backup** com um comando
- **Exportar Excel**: a lista que está na tela (com os filtros e a busca) sai em planilha, com dados da ficha, documentos pendentes e situação. Resolve a "lista do CDHU/Prefeitura", que levava cerca de 1 semana. Cada exportação fica registrada (quem, quando, quantos), por causa da LGPD
- **Decisão da diretoria**: o presidente registra o desligamento (motivo, data e observação) depois que a diretoria decide. O associado sai das listas, das mensalidades e da área do associado, mas o histórico fica guardado e é possível reativar. Na reativação, faltas e mensalidades voltam a contar do zero
- **Indicadores de impacto**: o "antes" do diagnóstico (508 fichas, 15–20 min para achar uma família, 1 semana para a lista, 4 números repetidos, 75% de documentação) ao lado do "depois" calculado pelo sistema, pronto para imprimir e usar no relatório final
- **Celular**: na tela pequena, o menu vira uma barra com o botão "Menu", para a equipe marcar presença na porta da assembleia

### 5º bloco – organização da equipe (2ª visita)
- **Três perfis**, conforme a organização da associação:
  - **Presidente / Diretoria**: tudo, inclusive cadastrar a equipe, registrar desligamentos e baixar o backup
  - **Administração (conferência)**: valida ou recusa os pagamentos, mantém o cadastro, importa e exporta listas e gera os códigos de acesso
  - **Voluntário (presença e coleta)**: nas assembleias, marca presença e recebe pagamentos e comprovantes. Vê a ficha com o CPF mascarado e sem a renda
- **Receber mensalidade**: pelo nº de sócio (ou pelo atalho que aparece depois de marcar a presença), o voluntário registra **"Recebi R$ 50 em dinheiro"** ou fotografa o comprovante. A mensalidade fica "em análise" até a administração conferir o valor e validar; só então sai o recibo
- **Fotos de comprovante reduzidas** (até 1600 px, em JPG): cabem muito mais no servidor e perdem a localização da foto
- **Baixar backup agora** (presidente, na tela Equipe): um arquivo com banco, fotos e comprovantes, para guardar no Google Drive da associação

## Tecnologias

Python 3 · Flask · Flask-SQLAlchemy (SQLite) · Flask-Login · qrcode · Pillow · openpyxl · PWA (manifest + service worker) · pytest

## Como rodar no Windows

1. Instale o [Python 3](https://www.python.org/downloads/) (marque "Add Python to PATH").
2. Abra o **Prompt de Comando** dentro da pasta do projeto e rode:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python seed.py --exemplos
python run.py
```

3. Abra **http://127.0.0.1:5000** no navegador e entre com o usuário **admin** e a senha que você definiu no passo do `seed.py`.

> **Esqueceu a senha do admin?** Com o ambiente ativo, rode `python seed.py --nova-senha`. Ele pede a senha nova duas vezes e não apaga nenhum dado.

> `python seed.py --exemplos` cria 6 associados **fictícios** com 3 meses de mensalidades e assembleias, para o painel já mostrar alertas, e mostra um código para testar a área do associado com a Ana (CPF 529.982.247-25) em **http://127.0.0.1:5000/associado/primeiro-acesso**. Para usar com dados reais, rode só `python seed.py`.

> **Atualizou o sistema?** Rode `pip install -r requirements.txt` de novo (pode ter biblioteca nova). O banco se ajusta sozinho e os dados continuam.

## Testes

```bat
python -m pytest
```

São 83 testes: login, cadastro, nº de sócio e CPF sem repetição, documentos, QR, validação de comprovante, recibo, cobrança dos mutirantes, presença por nº e QR, faltas e mensalidades seguidas, avisos de WhatsApp, proteção dos formulários, área do associado (código de acesso, bloqueio, termo obrigatório, foto só com autorização, um associado não mexe nos dados de outro), usuários da equipe, importação por planilha, códigos em lote, app instalável, modo de produção, backup, exportação da lista, desligamento pela diretoria, indicadores, perfis da equipe e recebimento em dinheiro, fotos HEIC do celular e senha provisória da equipe.

## Estrutura

```
app/
  __init__.py      criação do app, login e proteção CSRF
  models.py        tabelas do banco (modelo de dados do projeto)
  auth.py          entrar e sair
  painel.py        painel inicial
  associados.py    cadastro, ficha, nº de sócio, documentos, família e QR
  mensalidades.py  mensalidades, comprovantes, validação, recibo e mutirantes
  assembleias.py   assembleias e presença (nº ou QR)
  avisos.py        mensagens prontas para o WhatsApp e histórico
  area_associado.py área do associado: acesso, termo, foto, carteirinha e comprovantes
  acessos.py       acessos ao app e códigos de primeiro acesso em lote
  importacao.py    importação de associados por planilha (com prévia)
  equipe.py        usuários da equipe e troca de senha
  seguranca.py     bloqueio de tentativas de acesso
  indicadores.py   indicadores de impacto (antes e depois)
  termo.py         texto do termo de uso dos dados e da imagem (com versão)
  regras.py        regras da associação (3 faltas / 3 mensalidades, 2º domingo)
  utils.py         CPF, datas e valores em reais
  templates/       telas (HTML)
  static/          estilo, logo, ícones do app, manifesto e service worker (sw.js)
tests/             testes automatizados
run.py             liga o sistema para testar no computador
wsgi.py            entrada para a hospedagem (produção)
backup.py          backup do banco, fotos e comprovantes
seed.py            cria o usuário admin, troca a senha do admin e cria dados de exemplo
```

## Publicar na internet

O sistema precisa de uma hospedagem com **https** (sem https, a câmera e o app instalável não funcionam no celular) e com **disco permanente**: o banco (SQLite), as fotos e os comprovantes ficam em arquivos na pasta `instance/`. Serviços que apagam os arquivos a cada reinício não servem.

1. Envie o código para a hospedagem (pelo GitHub). A pasta `instance/` não vai junto, e é assim que deve ser.
2. Instale as bibliotecas com `pip install -r requirements.txt`.
3. Configure as variáveis de ambiente: `VDA_PRODUCAO=1` e `SECRET_KEY` (uma chave longa e aleatória).
4. Aponte o servidor para `wsgi:app` (nunca use `python run.py` na internet).
5. Rode `python seed.py` uma vez para criar o admin e defina uma senha forte.
6. Agende `python backup.py` para rodar **todo dia** e, uma vez por semana, baixe o backup mais recente e guarde fora do servidor (ex.: Google Drive da associação).

### Passo a passo no PythonAnywhere (endereço gratuito, sem domínio próprio)

O endereço fica `https://NOME.pythonanywhere.com` (ex.: `viladasartes.pythonanywhere.com`), já com https. No plano gratuito: 1 site, 512 MB de espaço, sem tarefas agendadas e o site **precisa ser renovado uma vez por mês** (botão na aba *Web*). No plano pago (Developer) há 5 GB e tarefas agendadas.

1. Crie a conta em pythonanywhere.com com o e-mail oficial da associação (viladasartes.vda2022@gmail.com). O nome de usuário vira o endereço.
2. Abra um **Bash console** e rode:
   ```
   git clone https://github.com/USUARIO/sistema-vila-das-artes.git
   cd sistema-vila-das-artes
   mkvirtualenv vila --python=python3.11
   pip install -r requirements.txt
   python seed.py
   ```
3. Na aba **Web**: *Add a new web app* → *Manual configuration* → Python 3.11. Em *Virtualenv*, coloque `/home/NOME/.virtualenvs/vila`.
4. Clique no arquivo **WSGI configuration** e troque todo o conteúdo por:
   ```python
   import os, sys
   caminho = "/home/NOME/sistema-vila-das-artes"
   if caminho not in sys.path:
       sys.path.insert(0, caminho)
   os.environ["VDA_PRODUCAO"] = "1"
   from wsgi import app as application
   ```
5. Ainda na aba Web: em *Static files*, URL `/static/` → pasta `/home/NOME/sistema-vila-das-artes/app/static`; ligue **Force HTTPS**; clique em **Reload**.
6. Para atualizar o sistema depois: `git pull`, `pip install -r requirements.txt` e **Reload**. O banco se ajusta sozinho.
7. **Todo mês**: entre na aba Web e clique no botão de renovar ("Run until 1 month from today"). **Toda semana**: tela Equipe → *Baixar backup agora* e guarde no Google Drive.

### Restaurar um backup

Desligue o sistema, descompacte o `.zip` do backup dentro da pasta do sistema (ele recria `instance/` com o banco, as fotos e os comprovantes) e ligue de novo.

## Segurança e LGPD

- O banco de dados, a chave secreta, os **comprovantes** e as **fotos** ficam na pasta `instance/`, que **não vai para o GitHub** (veja `.gitignore`).
- Os comprovantes são salvos com nome aleatório e só abrem para quem está logado.
- Nunca publique dados reais de associados no repositório.
- Na lista, o CPF aparece mascarado (***.456.789-**).
- As senhas dos associados e da equipe são guardadas criptografadas (hash), nunca em texto.
- A foto só é guardada com a autorização de imagem e só aparece para o próprio associado e para a equipe logada.
- Cada pessoa da equipe tem usuário próprio; o sistema registra quem validou cada comprovante e quem marcou cada presença.
- Senhas erradas: 5 tentativas bloqueiam o acesso por 15 minutos (equipe e associados).
- No celular, só a carteirinha do próprio associado fica guardada para uso sem internet, e ela é apagada quando ele sai.
- O login (da equipe e do associado) expira em 8 horas. No computador da sede, clique em **Sair** ao terminar.
- O termo (versão 1.1) informa que os dados ficam num serviço de hospedagem fora do Brasil (LGPD, art. 33).
- Bibliotecas com versão fixa e sem vulnerabilidades conhecidas (verificado com `pip-audit`); código verificado com `bandit`.
- No PythonAnywhere, ative a verificação em duas etapas da conta e mapeie como arquivos estáticos **só** a pasta `app/static` (nunca a `instance`).
- O texto do termo fica em `app/termo.py`. O contato oficial (WhatsApp e e-mail) fica em `app/contato.py` e aparece no termo, na área do associado, no recibo e nas mensagens. Se a diretoria mudar o texto, aumente a `VERSAO` e todos os associados precisarão aceitar de novo.

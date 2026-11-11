"""Termo de consentimento para uso de dados pessoais e imagem (LGPD – Lei nº 13.709/2018).

Se o texto mudar, aumente VERSAO: o sistema pede um novo aceite a todos os associados.
Sugestão: peça para a diretoria revisar o texto antes de colocar o sistema em uso.
"""

from . import contato

VERSAO = "1.1"  # 1.1: incluída a seção "Onde os dados ficam guardados" (LGPD, art. 33)
TITULO = "Termo de consentimento para uso de dados pessoais e imagem"

SECOES = [
    ("Quem cuida dos seus dados",
     f"{contato.NOME}, CNPJ {contato.CNPJ}, {contato.ENDERECO}. A diretoria é a responsável pelo cadastro. "
     f"Contato: WhatsApp {contato.WHATSAPP} e e-mail {contato.EMAIL}."),
    ("Quais dados guardamos",
     "Os dados da sua ficha de inscrição (identificação, contato, família, trabalho, renda e moradia), as cópias dos "
     "documentos, os pagamentos das mensalidades, as presenças nas assembleias e a foto que você enviar."),
    ("Para que usamos",
     "Para manter o seu cadastro, controlar mensalidades e assembleias, organizar a sua participação nos programas "
     "habitacionais (como CDHU e Prefeitura de Embu das Artes), identificar você na carteirinha e na entrada das "
     "assembleias e enviar avisos pelo WhatsApp."),
    ("Sua foto",
     "A foto serve só para identificar você na sua ficha e na carteirinha digital. Ela não será publicada em redes "
     "sociais, cartazes ou qualquer divulgação sem uma nova autorização sua."),
    ("Com quem compartilhamos",
     "Somente com órgãos públicos de habitação, quando for necessário para o programa em que você está inscrito. "
     "Seus dados nunca serão vendidos ou cedidos para propaganda."),
    ("Onde os dados ficam guardados",
     "Num serviço de hospedagem na internet contratado pela associação (PythonAnywhere), em servidores fora do "
     "Brasil. O acesso é protegido por senha e a conexão é segura (https). Esse serviço apenas guarda os dados "
     "para a associação e não pode usá-los para nenhum outro fim. Ao aceitar este termo, você concorda com essa "
     "guarda fora do país."),
    ("Quem pode ver",
     "Apenas a equipe autorizada da associação, com usuário e senha. Você vê somente as suas próprias informações."),
    ("Por quanto tempo",
     "Enquanto você for associado. Depois do desligamento, guardamos só pelo tempo necessário para prestação de "
     "contas e obrigações legais; depois os dados são apagados."),
    ("Seus direitos",
     "Você pode ver, corrigir e pedir a exclusão dos seus dados e da sua foto, e pode cancelar esta autorização a "
     f"qualquer momento, na sede, pelo WhatsApp {contato.WHATSAPP} ou pelo e-mail {contato.EMAIL}. Cancelar a "
     "autorização da foto não cancela a sua associação."),
]

ACEITE_DADOS = "Li e aceito o uso dos meus dados pessoais pela Associação Vila das Artes, conforme este termo."
ACEITE_IMAGEM = "Autorizo o uso da minha foto apenas para identificação no cadastro e na carteirinha digital."

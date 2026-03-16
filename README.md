# 🎥 Nexus Scan IP Cam

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-05998b.svg)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/Status-Ativo-success.svg)]()

**Nexus Scan** é uma solução profissional para monitoramento, inventário e análise de saúde de frotas de câmeras IP. Permite que administradores saibam em tempo real quais dispositivos estão online, quais apresentam falhas, onde estão localizados e gerencie credenciais com segurança.

---

## 🚀 Como Instalar e Rodar

### 🪟 Windows — Zero configuração

1. Clique em **Code → Download ZIP** aqui no GitHub
2. Descompacte em qualquer pasta
3. Clique duas vezes em **`Iniciar_Nexus_Scan.bat`**

Pronto. Na primeira execução o sistema detecta o Python instalado (ou baixa automaticamente se não houver nenhum), instala todas as dependências e abre o navegador no endereço `http://localhost:8000`.

> **Requisitos:** Windows 10/11 · Internet na primeira execução · Python **não é obrigatório** — é baixado automaticamente se necessário.

**Quer um atalho na Área de Trabalho?**
Execute `Configurar_Atalhos.bat` uma única vez — cria um ícone para iniciar o sistema com duplo clique.

---

### 🐧 Linux (Ubuntu / Debian / Fedora)

Linux **não** é o foco principal do projeto, mas funciona. Você precisa ter `python3` e `python3-venv` instalados:

```bash
# Debian / Ubuntu
sudo apt install python3 python3-venv

# Fedora
sudo dnf install python3
```

Depois:

```bash
git clone https://github.com/Maia1111/nexus_scan_cam.git
cd nexus_scan_cam
bash nexus_core/run.sh
```

Na primeira execução o ambiente virtual é criado e os pacotes instalados automaticamente. Nas execuções seguintes inicia direto.

Acesse em: `http://localhost:8000`

---

## 📋 Primeiro Acesso

Ao abrir o sistema pela primeira vez você verá a tela de **Setup**. Crie o usuário e senha do administrador. Este passo ocorre apenas uma vez — os dados ficam no banco local.

---

## 📖 Funcionalidades

### Scanner de Rede

Vá em **Scanner** → informe o range de rede (ex: `192.168.1.0/24`) → clique em **Iniciar Varredura**. O sistema varre a rede em paralelo e identifica câmeras IP com múltiplas camadas de detecção:

- **OUI (MAC)** — identifica fabricante pela tabela de endereços MAC (Hikvision, Dahua, Intelbras, Axis, Hanwha, Uniview, Reolink, TP-Link e outros)
- **Porta conhecida** — portas 8000, 37777, 34567 indicam fabricantes específicos
- **ONVIF GetDeviceInformation** — consulta o protocolo ONVIF para obter fabricante e modelo exatos sem autenticação
- **Banner HTTP** — lê o cabeçalho `Server` e o HTML inicial para identificar a marca
- **WS-Discovery** — descobre câmeras ONVIF via multicast na rede

Cada câmera encontrada exibe IP, MAC, fabricante, modelo (quando detectado), portas abertas e score de confiança. Câmeras identificadas como NVR/DVR são marcadas automaticamente.

- **Adicionar individual:** clique em **Salvar** na câmera desejada
- **Adicionar em lote:** marque várias câmeras com os checkboxes → **Adicionar Selecionados**
- **Detecção de múltiplas redes:** usa `psutil` para identificar todas as interfaces de rede com máscara real

### Câmeras

Inventário completo de todas as câmeras cadastradas com filtro, busca e edição. Ações disponíveis:

- **Editar** dados, credenciais, grupo e localização
- **Excluir individual** ou **excluir em lote** (selecione com checkbox)
- **Ver rota na rede** (traceroute visual hop a hop)
- **Abrir interface web** da câmera diretamente

### Grupos e Setores

Crie grupos (ex: "Portaria", "Estoque", "TI") e associe câmeras para manter o inventário organizado por setor.

- **Barra de busca** — localize uma câmera por nome ou IP entre todos os grupos. Grupos sem câmera compatível são ocultados automaticamente durante a busca
- **Coordenadas GPS** — defina latitude e longitude para localizar o grupo no mapa
- **Relatório por grupo** — visualize ou exporte PDF do inventário de cada grupo separadamente

### NVR / Gravadores

Câmeras marcadas como Gravador (NVR/DVR) aparecem em uma página dedicada. Você pode vincular câmeras a um gravador para registrar qual equipamento está conectado a qual NVR.

### Saúde da Rede (Diagnósticos)

Análise completa em tempo real com ping ICMP (via `icmplib`) e fallback TCP sequencial. Cada câmera recebe um **score de qualidade de 0 a 100** calculado com base em três métricas:

| Métrica | Peso | Critério ideal |
|---|---|---|
| Latência | até 40 pts | < 20ms |
| Jitter | até 30 pts | < 10ms |
| Perda de pacotes | até 30 pts | 0% |

**Classificação de qualidade:**

| Label | Score | Significado |
|---|---|---|
| Ótimo | ≥ 90 | Rede excelente |
| Bom | ≥ 80 | Rede saudável |
| Regular | ≥ 50 | Atenção necessária |
| Ruim | < 50 | Problema sério |

Ao passar o mouse sobre a barra de qualidade de qualquer câmera, um **tooltip detalhado** exibe:
- Valores individuais de latência, jitter e perda com código de cor (verde/amarelo/vermelho)
- Dicas de diagnóstico por métrica
- Bloco **"Por que Regular?"** (quando aplicável) mostrando cada métrica que reduziu a nota, quantos pontos perdeu e a ação recomendada (ex: "Latência 95ms -25pts — Troque o cabo e teste outra porta no switch")

**Seções de diagnóstico:**

| Seção | O que detecta |
|---|---|
| Sem resposta | Câmeras offline — não responderam a nenhum ping |
| Crítico | Latência > 300ms, jitter > 100ms ou perda ≥ 50% |
| Atenção | Latência > 80ms, jitter > 40ms ou qualquer perda de pacotes |
| Normal | Câmeras com rede saudável |
| Problemas Críticos | Conflito IP/MAC, câmera marcada online mas sem resposta (possível travamento) |
| Credenciais não cadastradas | Câmeras sem usuário/senha no cofre — com botão de cadastro rápido |

**Verificações adicionais:**

- **Conflito IP/MAC** — detecta quando o IP de uma câmera passou a responder com um MAC diferente do cadastrado
- **IP dinâmico (DHCP)** — detecta quando o MAC da câmera aparece em um IP diferente do cadastrado na rede
- **NVR/DVR detectado** — identifica gravadores com múltiplas portas de gerência abertas
- **Interface de rede ausente** — alerta quando não há interface local configurada na mesma faixa das câmeras
- **MAC duplicado** — identifica MACs iguais em cadastros diferentes

Busca por nome ou IP disponível para filtrar câmeras dentro do diagnóstico.

### Cofre de Senhas

As credenciais das câmeras podem ser protegidas com criptografia forte (Fernet/PBKDF2 com 480.000 iterações):

1. Acesse **Administração → Cofre de Senhas**
2. Defina uma **senha mestra** separada da sua senha de login
3. As senhas das câmeras são criptografadas no banco de dados
4. Para visualizar uma senha, desbloqueie o cofre e clique no ícone de olho

> A senha mestra **não é recuperável**. Guarde-a com segurança.

### Gerenciamento de Usuários

- **Perfis:** Admin (acesso total) e Viewer (somente leitura)
- **Criar usuário** com confirmação de senha
- **Editar usuário** — alterar nome, senha, perfil e status ativo/inativo
- **Troca de senha** disponível no menu do usuário no rodapé da sidebar
- **Desativar usuário** sem excluir o cadastro

### Relatórios PDF

Gere relatórios profissionais em PDF diretamente pela interface:
- **Relatório geral** — todas as câmeras em ordem cronológica
- **Relatório por grupo** — inventário filtrado por setor/grupo

---

## 🎯 Resumo das Funcionalidades

| Recurso | Descrição |
|---|---|
| Scanner automático | Varre a rede e identifica câmeras por OUI, ONVIF, banner HTTP e portas |
| Detecção de modelo | Obtém fabricante e modelo exatos via ONVIF sem autenticação |
| Adição em lote | Salva múltiplas câmeras do scanner de uma vez |
| Monitoramento contínuo | Verifica status a cada 30 segundos com ICMP/TCP |
| Grupos e setores | Organização por localização/setor com coordenadas GPS |
| Busca nos grupos | Localiza qualquer câmera por nome ou IP entre todos os grupos |
| NVR / Gravadores | Gerenciamento de gravadores e câmeras vinculadas |
| Score de qualidade | Pontuação 0-100 por câmera com breakdown de latência, jitter e perda |
| Diagnóstico inteligente | Detecta 8+ tipos de problemas com severidade e ação recomendada |
| Tooltip de diagnóstico | Métricas detalhadas e sugestões de correção ao passar o mouse |
| Cofre de senhas | Credenciais criptografadas com senha mestra (Fernet/PBKDF2) |
| Exclusão em lote | Remove múltiplas câmeras de uma vez |
| Relatórios PDF | Exportação profissional por grupo ou geral |
| Controle de acesso | Perfis Admin e Viewer com login e gestão de usuários |
| Auto-instalação | Configura o ambiente automaticamente na primeira execução |

---

## 🛡️ Licença

Desenvolvido para fins profissionais de monitoramento. Verifique sempre as leis locais sobre privacidade e monitoramento de câmeras.

**Desenvolvido por Rogério Maia** 🚀🎥

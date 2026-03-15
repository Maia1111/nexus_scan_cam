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
Vá em **Scanner** → informe o range de rede (ex: `192.168.1.0/24`) → clique em **Iniciar Varredura**. O sistema varre a rede, identifica câmeras IP por porta e fabricante, e exibe IP, MAC e score de confiança.

- **Adicionar individual:** clique em **Salvar** na câmera desejada
- **Adicionar em lote:** marque várias câmeras com os checkboxes → **Adicionar Selecionados**

### Câmeras
Inventário completo de todas as câmeras cadastradas com filtro, busca e edição. Ações disponíveis:

- **Editar** dados, credenciais, grupo e localização
- **Excluir individual** ou **excluir em lote** (selecione com checkbox)
- **Ver rota na rede** (traceroute visual hop a hop)
- **Abrir interface web** da câmera diretamente

### Grupos e Setores
Crie grupos (ex: "Portaria", "Estoque", "TI") e associe câmeras para manter o inventário organizado por setor.

### NVR / Gravadores
Câmeras marcadas como Gravador (NVR/DVR) aparecem em uma página dedicada. Você pode vincular câmeras a um gravador para registrar qual equipamento está conectado a qual NVR.

### Saúde da Rede (Diagnósticos)
Análise completa em tempo real. Aponta:

| Categoria | O que detecta |
|---|---|
| **Sem resposta** | Câmeras offline ou sem ping |
| **Crítico** | Latência > 300ms, jitter grave, perda de pacotes ≥ 50% |
| **Atenção** | Latência alta, conexão instável, perda parcial de pacotes |
| **Normal** | Câmeras com rede saudável |
| **Problemas críticos** | Conflito IP/MAC, câmera travada |
| **Credenciais não cadastradas** | Câmeras sem usuário/senha no cofre |

Cada câmera na lista de atenção mostra os problemas diretamente na linha (badges de instabilidade). Câmeras sem credenciais têm um botão de cadastro rápido direto na tela de diagnóstico.

### Cofre de Senhas
As credenciais das câmeras podem ser protegidas com criptografia forte (Fernet/PBKDF2):

1. Acesse **Administração → Cofre de Senhas**
2. Defina uma **senha mestra** separada da sua senha de login
3. As senhas das câmeras são criptografadas no banco de dados
4. Para visualizar uma senha, desbloqueie o cofre e clique no ícone de olho

> A senha mestra **não é recuperável**. Guarde-a com segurança.

### Relatórios PDF
Gere relatórios profissionais em PDF diretamente pela interface — geral (cronológico) ou por grupos/setores.

---

## 🎯 Resumo das Funcionalidades

| Recurso | Descrição |
|---|---|
| Scanner automático | Varre a rede e identifica câmeras IP |
| Adição em lote | Salva múltiplas câmeras do scanner de uma vez |
| Monitoramento contínuo | Verifica status a cada 30 segundos |
| Grupos e setores | Organização por localização/setor |
| NVR / Gravadores | Gerenciamento de gravadores e câmeras vinculadas |
| Diagnóstico inteligente | Detecta problemas de rede com segmentação por severidade |
| Cofre de senhas | Credenciais criptografadas com senha mestra |
| Exclusão em lote | Remove múltiplas câmeras de uma vez |
| Relatórios PDF | Exportação profissional por grupo ou geral |
| Controle de acesso | Perfis Admin e Viewer com login |
| Auto-instalação | Configura o ambiente automaticamente na primeira execução |

---

## 🛡️ Licença

Desenvolvido para fins profissionais de monitoramento. Verifique sempre as leis locais sobre privacidade e monitoramento de câmeras.

**Desenvolvido por Rogério Maia** 🚀🎥

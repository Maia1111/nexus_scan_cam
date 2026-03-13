# 🎥 Nexus Scan IP Cam

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-05998b.svg)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/Status-Ativo-success.svg)]()

**Nexus Scan** é uma solução profissional para monitoramento, inventário e análise de saúde de frotas de câmeras IP. Permite que administradores saibam em tempo real quais dispositivos estão online, quais apresentam falhas e onde estão localizados.

---

## 🚀 Instalação e Uso

### 🪟 Para Windows — Modo Fácil (recomendado)

**Opção A — Baixar pacote pronto (sem precisar instalar nada além do Python):**

1. Vá em [Releases](../../releases) e baixe o arquivo `NexusScan_vX.X.zip`
2. Descompacte em qualquer pasta
3. Execute `Configurar_Nexus_Scan.ps1` **uma vez** (clique direito → Executar com PowerShell)
   - Cria um ícone de câmera na Área de Trabalho
4. A partir daí, basta clicar no ícone **Nexus Scan** na Área de Trabalho

> Na primeira execução o sistema instala as dependências automaticamente. As próximas execuções iniciam instantaneamente.

**Opção B — Clonar o repositório:**

```
git clone https://github.com/Maia1111/nexus_scan_cam.git
cd nexus_scan_cam
```

Depois clique duas vezes em `Iniciar_Nexus_Scan.bat` — o sistema configura tudo e abre no navegador.

---

### 🐧 Linux (Ubuntu / Debian / Fedora)

```bash
git clone https://github.com/Maia1111/nexus_scan_cam.git
cd nexus_scan_cam
bash nexus_core/run.sh
```

Na primeira execução o ambiente virtual é criado e as dependências instaladas automaticamente.

---

## 📋 Pré-requisitos

| Sistema | Requisito |
|---|---|
| Windows | Python 3.10+ ([python.org](https://www.python.org/downloads/)) — marque "Add to PATH" |
| Linux | `python3` + `python3-venv` (`sudo apt install python3 python3-venv`) |

---

## 📖 Como Usar

### 1. Primeiro Acesso — Criar Administrador
Ao abrir o sistema pela primeira vez, você verá a tela de **Setup**. Crie o usuário e senha do administrador. Este passo ocorre apenas uma vez.

### 2. Scanner de Rede
Vá em **Scanner** → informe o range de rede (ex: `192.168.1.0/24`) → clique em **Iniciar Scan**. O sistema varre a rede automaticamente e identifica câmeras IP, exibindo IP, fabricante e portas abertas. Clique em **Salvar** para adicionar ao inventário.

### 3. Cadastro Manual
Em **Câmeras** → **Nova Câmera**, cadastre câmeras manualmente informando IP, nome, localização e credenciais de acesso.

### 4. Organizar por Grupos
Crie **Grupos** (ex: "Portaria", "Estoque", "TI") e associe câmeras a eles para manter o inventário organizado por setor.

### 5. Diagnóstico de Rede
Em **Diagnósticos**, o sistema executa verificações automáticas e aponta problemas como:
- Câmeras offline
- Latência alta ou jitter
- Conflito de IP/MAC
- Câmeras com IP dinâmico (DHCP)
- Possíveis NVR/DVR detectados

### 6. Relatórios PDF
Gere relatórios profissionais em PDF diretamente pela interface — por câmera individual, por grupo ou geral.

---

## 🎯 Funcionalidades

| Recurso | Descrição |
|---|---|
| Scanner automático | Varre a rede e identifica câmeras IP |
| Monitoramento contínuo | Verifica status a cada 30 segundos |
| Grupos e setores | Organização por localização/setor |
| Diagnóstico inteligente | Detecta problemas de rede automaticamente |
| Relatórios PDF | Exportação profissional por grupo ou geral |
| Controle de acesso | Perfis Admin e Viewer com login |
| Detecção de porta livre | Inicia automaticamente na primeira porta disponível |

---

## 🛡️ Licença

Desenvolvido para fins profissionais de monitoramento. Verifique sempre as leis locais sobre privacidade e monitoramento de câmeras.

**Desenvolvido por Rogério Maia** 🚀🎥
